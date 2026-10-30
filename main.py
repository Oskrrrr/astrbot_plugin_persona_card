"""角色卡（persona card）——把人格、音色、聊天模型、知识库、表情包绑成一张卡，
一键应用到某个会话，随时切换。

设计要点：
- 不复制框架能力，只做"绑定"：写入的落地位置全部是 AstrBot 原生的会话级偏好
  （session_service_config.persona_id / provider_perf_* / kb_config），
  以及 meme_manager 的 selection_rules.json（会话级规则）。
- 因此切换立即生效，不需要重启，也不需要改动其它插件。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from astrbot.api import logger, sp
from astrbot.api.event import filter
from astrbot.api.provider import ProviderType
from astrbot.api.star import Context, Star
from astrbot.core import AstrBotConfig

from .store import CardStore

PLUGIN_NAME = "astrbot_plugin_persona_card"
PLUGIN_TITLE = "角色卡"

try:  # quart 在 AstrBot 运行时可用；不可用时退化为返回普通 dict
    from quart import jsonify as _jsonify
    from quart import request as _request
except Exception:  # pragma: no cover
    _jsonify = None
    _request = None


def _plugin_data_dir() -> Path:
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

        root = Path(get_astrbot_plugin_data_path())
    except Exception:
        root = Path("/AstrBot/data/plugin_data")
    return root / PLUGIN_NAME


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            with path.open(encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        return default
    return default


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _clean_id(value: Any) -> str:
    raw = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{1,40}", raw):
        return raw
    return ""


class PersonaCardPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config
        try:
            self._record_sessions = bool(config.get("record_sessions", True))
        except Exception:
            self._record_sessions = True
        try:
            self._flush_interval = max(15, int(config.get("flush_interval", 60) or 60))
        except Exception:
            self._flush_interval = 60

        self.store = CardStore(_plugin_data_dir() / "cards.json")
        self._flush_task: asyncio.Task | None = None
        self._prompt_logged: set[str] = set()

        self._register_web_apis()

    # ------------------------------------------------------------------ 生命周期

    async def initialize(self) -> None:
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("[persona_card] 已加载，%s 张角色卡", len(self.store.cards))

    async def terminate(self) -> None:
        task = self._flush_task
        self._flush_task = None
        if task is not None:
            task.cancel()
        try:
            self.store.save()
        except Exception:
            logger.debug("[persona_card] 保存失败", exc_info=True)

    async def _flush_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._flush_interval)
                if self.store.dirty:
                    self.store.save()
        except asyncio.CancelledError:
            return

    # ------------------------------------------------------------------ 会话记录

    @filter.on_llm_request(priority=100)
    async def inject_card_prompt(self, event, req):
        """把会话绑定卡片的「风格补充」追加到系统提示词末尾。

        只对绑定了卡片的会话生效，不改其它插件代码，也不影响别的人格。
        """
        try:
            umo = str(getattr(event, "unified_msg_origin", "") or "")
            if not umo:
                return
            card_id = str(self.store.bindings.get(umo) or "")
            card = self.store.get_card(card_id) if card_id else None
            extra = str((card or {}).get("prompt_append") or "").strip()
            if not extra:
                return
            header = f"【角色卡·{(card or {}).get('name') or '补充设定'}】"
            base = str(getattr(req, "system_prompt", "") or "")
            req.system_prompt = (
                base.rstrip() + "\n\n" + header + "\n" + extra
                if base.strip()
                else header + "\n" + extra
            )
            if umo not in self._prompt_logged:
                self._prompt_logged.add(umo)
                logger.info(
                    "[persona_card] 已为 %s 注入角色卡风格补充（%s 字）", umo, len(extra)
                )
        except Exception:
            logger.debug("[persona_card] 注入卡片提示词失败", exc_info=True)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=1000)
    async def record_session(self, event):
        """记录出现过的会话，供页面选择应用目标。只做内存更新，定时落盘。"""
        if not self._record_sessions:
            return
        try:
            umo = str(getattr(event, "unified_msg_origin", "") or "")
            if not umo:
                return
            low = umo.lower()
            if "groupmessage" in low or ":group:" in low:
                kind = "group"
            elif "friend" in low or "private" in low:
                kind = "private"
            else:
                kind = "other"
            ident = umo.rsplit(":", 1)[-1]
            if kind == "group":
                label = f"群 {ident}"
            elif kind == "private":
                label = f"私聊 {ident}"
            else:
                label = umo
            text = ""
            try:
                text = str(event.message_str or "").strip()
            except Exception:
                text = ""
            if not text:
                try:
                    text = str(getattr(event.message_obj, "message_str", "") or "").strip()
                except Exception:
                    text = ""
            self.store.touch_session(umo, kind, label, text)
        except Exception:
            logger.debug("[persona_card] 会话记录失败", exc_info=True)

    # ------------------------------------------------------------------ Web API

    def _register_web_apis(self) -> None:
        routes = (
            ("state", self.api_state, ["GET"], "角色卡：读取全部状态"),
            ("save", self.api_save, ["POST"], "角色卡：保存卡片"),
            ("delete", self.api_delete, ["POST"], "角色卡：删除卡片"),
            ("apply", self.api_apply, ["POST"], "角色卡：应用到会话"),
            ("unbind", self.api_unbind, ["POST"], "角色卡：解除会话绑定"),
            ("draft", self.api_draft, ["POST"], "角色卡：从会话生成草稿"),
        )
        for endpoint, handler, methods, desc in routes:
            self.context.register_web_api(
                f"/{PLUGIN_NAME}/{endpoint}", handler, methods, desc
            )

    @staticmethod
    async def _json(payload: dict, status: int = 200):
        if _jsonify is None:
            return payload
        response = _jsonify(payload)
        try:
            response.status_code = status
        except Exception:
            pass
        return response

    async def _ok(self, data: Any):
        return await self._json({"ok": True, "data": data})

    async def _err(self, message: str, status: int = 200):
        """统一返回 200 + ok=false：页面桥接对非 2xx 只会给出 axios 的通用错误文案，
        拿不到我们自己的提示。"""
        return await self._json(
            {"ok": False, "error": {"message": message}}, status=status
        )

    async def _body(self) -> dict:
        if _request is None:
            return {}
        try:
            data = await _request.get_json(silent=True)
        except TypeError:
            data = await _request.get_json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    async def api_state(self):
        try:
            return await self._ok(await self._build_state())
        except Exception as exc:
            logger.exception("[persona_card] 读取状态失败")
            return await self._err(str(exc) or "读取状态失败")

    async def api_save(self):
        body = await self._body()
        card = body.get("card")
        if not isinstance(card, dict):
            return await self._err("缺少卡片数据")
        try:
            normalized = await self._normalize_card(card)
        except ValueError as exc:
            return await self._err(str(exc))
        saved = self.store.upsert_card(normalized)
        self.store.save()
        return await self._ok({"card": saved})

    async def api_delete(self):
        body = await self._body()
        card_id = _clean_id(body.get("id"))
        if not card_id:
            return await self._err("缺少卡片 id")
        removed = self.store.delete_card(card_id)
        self.store.save()
        return await self._ok({"removed": removed})

    async def api_apply(self):
        body = await self._body()
        umo = str(body.get("umo") or "").strip()
        card_id = _clean_id(body.get("card_id"))
        if not umo or ":" not in umo:
            return await self._err("会话标识不合法")
        card = self.store.get_card(card_id) if card_id else None
        if card is None:
            return await self._err("卡片不存在")
        try:
            result = await self._apply_card(umo, card)
        except Exception as exc:
            logger.exception("[persona_card] 应用卡片失败")
            return await self._err(str(exc) or "应用失败")
        self.store.bind(umo, card_id)
        self.store.save()
        return await self._ok(
            {
                "umo": umo,
                "card": card,
                "effective": result["effective"],
                "warnings": result["warnings"],
            }
        )

    async def api_unbind(self):
        body = await self._body()
        umo = str(body.get("umo") or "").strip()
        if not umo or ":" not in umo:
            return await self._err("会话标识不合法")
        try:
            await self._clear_session(umo)
        except Exception as exc:
            logger.exception("[persona_card] 解除绑定失败")
            return await self._err(str(exc) or "解除绑定失败")
        self.store.bind(umo, "")
        self.store.save()
        return await self._ok({"umo": umo})

    async def api_draft(self):
        body = await self._body()
        umo = str(body.get("umo") or "").strip()
        if not umo or ":" not in umo:
            return await self._err("会话标识不合法")
        try:
            draft = await self._draft_from_session(umo)
        except Exception as exc:
            logger.exception("[persona_card] 生成草稿失败")
            return await self._err(str(exc) or "生成草稿失败")
        return await self._ok({"card": draft, "umo": umo})

    # ------------------------------------------------------------------ 对外读取

    def qzone_profile(self, name: str = "") -> dict | None:
        """给其它插件（说说外挂）读的「说说」板块。

        按角色卡名称或人格名匹配；该卡没写任何说说内容时返回 None。
        """
        wanted = str(name or "").strip()
        if not wanted:
            return None
        fields = ("post_prompt", "image_style", "image_requirements", "image_negative")
        for card in self.store.cards:
            if wanted not in (
                str(card.get("name") or ""),
                str(card.get("persona_id") or ""),
            ):
                continue
            data = card.get("qzone")
            if not isinstance(data, dict):
                continue
            values = {key: str(data.get(key) or "").strip() for key in fields}
            if not any(values.values()):
                continue
            values["card_name"] = str(card.get("name") or "")
            return values
        return None

    # ------------------------------------------------------------------ 状态组装

    async def _build_state(self) -> dict:
        self._merge_known_sessions()
        options = await self._options()
        return {
            "cards": sorted(
                self.store.cards,
                key=lambda c: (str(c.get("name") or ""), str(c.get("id") or "")),
            ),
            "bindings": dict(self.store.bindings),
            "sessions": self._session_rows(),
            "options": options,
        }

    def _merge_known_sessions(self) -> None:
        """补齐只在绑定里出现过的会话；清掉没有任何信息的空壳记录。"""
        changed = False
        for umo in list(self.store.bindings):
            if umo and umo not in self.store.sessions:
                self.store.sessions[umo] = {
                    "label": umo,
                    "kind": "group" if "groupmessage" in umo.lower() else "private",
                    "last_seen": 0,
                }
                changed = True
        for umo, rec in list(self.store.sessions.items()):
            if (
                int(rec.get("last_seen") or 0) <= 0
                and not rec.get("last_text")
                and umo not in self.store.bindings
            ):
                self.store.sessions.pop(umo, None)
                changed = True
        if changed:
            self.store.dirty = True

    def _session_rows(self) -> list[dict]:
        rows: list[dict] = []
        for umo, rec in self.store.sessions.items():
            card_id = str(self.store.bindings.get(umo) or "")
            card = self.store.get_card(card_id) if card_id else None
            rows.append(
                {
                    "umo": umo,
                    "label": str(rec.get("label") or umo),
                    "kind": str(rec.get("kind") or "other"),
                    "last_seen": int(rec.get("last_seen") or 0),
                    "last_text": str(rec.get("last_text") or ""),
                    "card_id": card_id if card else "",
                    "card_name": str((card or {}).get("name") or ""),
                }
            )
        rows.sort(key=lambda r: (-r["last_seen"], r["label"]))
        return rows

    # ------------------------------------------------------------------ 选项

    async def _options(self) -> dict:
        return {
            "personas": self._persona_options(),
            "tts": self._provider_options("tts_provider_insts"),
            "chat": self._provider_options("provider_insts"),
            "kbs": await self._kb_options(),
            "packs": self._pack_options(),
        }

    def _persona_options(self) -> list[dict]:
        out: list[dict] = []
        manager = getattr(self.context, "persona_manager", None)
        for persona in getattr(manager, "personas_v3", []) or []:
            if not isinstance(persona, dict):
                continue
            name = str(persona.get("name") or "").strip()
            if not name:
                continue
            prompt = str(persona.get("prompt") or "").replace("\n", " ").strip()
            out.append({"id": name, "name": name, "prompt_head": prompt[:60]})
        return out

    def _provider_options(self, attr: str) -> list[dict]:
        out: list[dict] = []
        manager = getattr(self.context, "provider_manager", None)
        for inst in getattr(manager, attr, []) or []:
            try:
                meta = inst.meta()
            except Exception:
                continue
            out.append(
                {
                    "id": str(getattr(meta, "id", "") or ""),
                    "model": str(getattr(meta, "model", "") or ""),
                    "type": str(getattr(meta, "type", "") or ""),
                }
            )
        return out

    async def _kb_options(self) -> list[dict]:
        out: list[dict] = []
        manager = getattr(self.context, "kb_manager", None)
        if manager is None:
            return out
        try:
            kbs = await manager.list_kbs()
        except Exception:
            return out
        for kb in kbs:
            out.append(
                {
                    "id": str(getattr(kb, "kb_id", "") or ""),
                    "name": str(getattr(kb, "kb_name", "") or ""),
                    "docs": int(getattr(kb, "doc_count", 0) or 0),
                }
            )
        return out

    def _meme_dir(self) -> Path:
        return _plugin_data_dir().parent / "meme_manager"

    def _pack_options(self) -> list[dict]:
        registry = _read_json(self._meme_dir() / "registry.json", {})
        installed = registry.get("installed_packs") if isinstance(registry, dict) else None
        options: list[dict] = []
        for pack in installed or []:
            if not isinstance(pack, dict):
                continue
            pack_id = str(pack.get("id") or "").strip()
            if not pack_id:
                continue
            options.append(
                {
                    "id": pack_id,
                    "name": str(pack.get("name") or pack_id),
                    "enabled": bool(pack.get("enabled", True)),
                }
            )
        return options

    def _valid_pack_ids(self) -> set[str]:
        """meme_manager 只认「目录存在 + registry 里启用」的包。"""
        root = self._meme_dir() / "packs"
        valid = {
            item["id"]
            for item in self._pack_options()
            if item["enabled"] and (root / item["id"]).is_dir()
        }
        if (root / "builtin-default").is_dir():
            valid.add("builtin-default")
        return valid

    # ------------------------------------------------------------------ 卡片校验

    async def _normalize_card(self, raw: dict) -> dict:
        card_id = _clean_id(raw.get("id")) or f"c_{uuid.uuid4().hex[:8]}"
        name = str(raw.get("name") or "").strip()[:40] or "未命名角色卡"
        emoji = (str(raw.get("emoji") or "").strip() or "🐟")[:4]
        notes = str(raw.get("notes") or "").strip()[:300]

        persona_ids = {p["id"] for p in self._persona_options()}
        persona_id = str(raw.get("persona_id") or "").strip()
        if persona_id and persona_id not in persona_ids:
            raise ValueError("人格不存在")

        tts_ids = {p["id"] for p in self._provider_options("tts_provider_insts")}
        tts_provider_id = str(raw.get("tts_provider_id") or "").strip()
        if tts_provider_id and tts_provider_id not in tts_ids:
            raise ValueError("音色提供方不存在")

        chat_ids = {p["id"] for p in self._provider_options("provider_insts")}
        chat_provider_id = str(raw.get("chat_provider_id") or "").strip()
        if chat_provider_id and chat_provider_id not in chat_ids:
            raise ValueError("聊天模型不存在")

        valid_kb_ids = {kb["id"] for kb in await self._kb_options()}
        kb_ids: list[str] = []
        for kb_id in raw.get("kb_ids") or []:
            kb_id = str(kb_id or "").strip()
            if kb_id and kb_id in valid_kb_ids and kb_id not in kb_ids:
                kb_ids.append(kb_id)

        valid_packs = {p["id"] for p in self._pack_options()}
        raw_packs = raw.get("meme_pack_ids")
        if raw_packs is None:
            raw_packs = [raw.get("meme_pack_id")] if raw.get("meme_pack_id") else []
        meme_pack_ids: list[str] = []
        for pack_id in raw_packs or []:
            pack_id = str(pack_id or "").strip()
            if not pack_id:
                continue
            if pack_id not in valid_packs:
                raise ValueError(f"表情包「{pack_id}」不存在")
            if pack_id not in meme_pack_ids:
                meme_pack_ids.append(pack_id)
        if len(meme_pack_ids) > 5:
            raise ValueError("表情包最多选 5 个")

        prompt_append = str(raw.get("prompt_append") or "").strip()[:1500]

        qzone_raw = raw.get("qzone") if isinstance(raw.get("qzone"), dict) else {}
        qzone = {
            "post_prompt": str(qzone_raw.get("post_prompt") or "").strip()[:2000],
            "image_style": str(qzone_raw.get("image_style") or "").strip()[:600],
            "image_requirements": str(qzone_raw.get("image_requirements") or "").strip()[:600],
            "image_negative": str(qzone_raw.get("image_negative") or "").strip()[:500],
        }

        return {
            "id": card_id,
            "name": name,
            "emoji": emoji,
            "persona_id": persona_id,
            "tts_provider_id": tts_provider_id,
            "chat_provider_id": chat_provider_id,
            "kb_ids": kb_ids,
            "meme_pack_ids": meme_pack_ids,
            "prompt_append": prompt_append,
            "qzone": qzone,
            "notes": notes,
        }

    # ------------------------------------------------------------------ 应用 / 解除

    async def _apply_card(self, umo: str, card: dict) -> dict:
        warnings: list[str] = []

        # 1) 人格（会话级强制人格）
        persona_id = str(card.get("persona_id") or "")
        if persona_id and persona_id not in {p["id"] for p in self._persona_options()}:
            warnings.append(f"人格「{persona_id}」已不存在，已跳过人格绑定")
            persona_id = ""
        session_config = await sp.session_get(umo, "session_service_config", {}) or {}
        if not isinstance(session_config, dict):
            session_config = {}
        if persona_id:
            session_config["persona_id"] = persona_id
        else:
            session_config.pop("persona_id", None)
        await self._save_session_config(umo, session_config)

        # 2) 音色 / 3) 聊天模型（会话级 provider 覆盖）
        tts_id = str(card.get("tts_provider_id") or "")
        if tts_id and tts_id not in {p["id"] for p in self._provider_options("tts_provider_insts")}:
            warnings.append(f"音色「{tts_id}」的提供方已不存在，已跳过")
            tts_id = ""
        await self._set_session_provider(umo, ProviderType.TEXT_TO_SPEECH, tts_id)

        chat_id = str(card.get("chat_provider_id") or "")
        if chat_id and chat_id not in {p["id"] for p in self._provider_options("provider_insts")}:
            warnings.append(f"聊天模型「{chat_id}」已不存在，已跳过")
            chat_id = ""
        await self._set_session_provider(umo, ProviderType.CHAT_COMPLETION, chat_id)

        # 4) 知识库
        kb_ids = [str(x) for x in (card.get("kb_ids") or []) if str(x).strip()]
        if kb_ids:
            await sp.session_put(umo, "kb_config", {"kb_ids": kb_ids})
        else:
            await self._session_remove(umo, "kb_config")

        # 5) 表情包（meme_manager 会话级选包规则，支持多选）
        valid_packs = self._valid_pack_ids()
        pack_ids: list[str] = []
        for pack_id in card.get("meme_pack_ids") or []:
            pack_id = str(pack_id or "").strip()
            if not pack_id:
                continue
            if pack_id not in valid_packs:
                warnings.append(
                    f"表情包「{pack_id}」未启用或不存在，已跳过（请先在表情包管理器启用）"
                )
                continue
            pack_ids.append(pack_id)
        self._set_pack_rule(umo, pack_ids)

        return {"effective": await self._effective(umo), "warnings": warnings}

    async def _clear_session(self, umo: str) -> None:
        session_config = await sp.session_get(umo, "session_service_config", {}) or {}
        if isinstance(session_config, dict) and "persona_id" in session_config:
            session_config.pop("persona_id", None)
            await self._save_session_config(umo, session_config)
        for ptype in (ProviderType.TEXT_TO_SPEECH, ProviderType.CHAT_COMPLETION):
            await self._session_remove(umo, f"provider_perf_{ptype.value}")
        await self._session_remove(umo, "kb_config")
        self._set_pack_rule(umo, [])

    async def _save_session_config(self, umo: str, session_config: dict) -> None:
        """空配置就不要留一条空记录。"""
        if session_config:
            await sp.session_put(umo, "session_service_config", session_config)
        else:
            await self._session_remove(umo, "session_service_config")

    async def _set_session_provider(
        self, umo: str, ptype: ProviderType, provider_id: str
    ) -> None:
        key = f"provider_perf_{ptype.value}"
        if provider_id:
            await sp.session_put(umo, key, provider_id)
        else:
            await self._session_remove(umo, key)

    async def _session_remove(self, umo: str, key: str) -> None:
        try:
            await sp.session_remove(umo, key)
        except Exception:
            logger.debug("[persona_card] 移除会话偏好 %s/%s 失败", umo, key, exc_info=True)

    @staticmethod
    def _rule_targets(umo: str) -> list[str]:
        """meme_manager 在不同调用点拿到的 session_id 可能是完整 umo，
        也可能只是最后一段（群号/QQ 号），两种都写上最稳。"""
        targets = [umo]
        plain = umo.rsplit(":", 1)[-1]
        if plain and plain != umo:
            targets.append(plain)
        return targets

    def _set_pack_rule(self, umo: str, pack_ids: list[str]) -> None:
        path = self._meme_dir() / "selection_rules.json"
        data = _read_json(path, None)
        if not isinstance(data, dict):
            data = {"schema_version": 1, "rules": []}
        rules = data.get("rules")
        if not isinstance(rules, list):
            rules = []
        targets = self._rule_targets(umo)
        rules = [
            r
            for r in rules
            if not (
                isinstance(r, dict)
                and str(r.get("scope") or "").lower() == "session"
                and str(r.get("target") or "") in targets
            )
        ]
        if pack_ids:
            for target in targets:
                rules.append(
                    {
                        "id": f"persona-card-{uuid.uuid4().hex[:8]}",
                        "scope": "session",
                        "target": target,
                        "pack_ids": list(pack_ids),
                    }
                )
        data["rules"] = rules
        _write_json_atomic(path, data)

    # ------------------------------------------------------------------ 读当前生效

    async def _effective(self, umo: str) -> dict:
        persona_id = ""
        try:
            session_config = (
                await sp.session_get(umo, "session_service_config", {}) or {}
            )
            if isinstance(session_config, dict):
                persona_id = str(session_config.get("persona_id") or "")
        except Exception:
            persona_id = ""

        tts = await self._current_provider_id(ProviderType.TEXT_TO_SPEECH, umo)
        chat = await self._current_provider_id(ProviderType.CHAT_COMPLETION, umo)
        kb_ids = await self._current_kb_ids(umo)
        pack_ids = self._current_pack_ids(umo, persona_id)
        return {
            "persona_id": persona_id,
            "tts_provider_id": tts,
            "chat_provider_id": chat,
            "kb_ids": kb_ids,
            "meme_pack_ids": pack_ids,
        }

    async def _current_provider_id(
        self, ptype: ProviderType, umo: str
    ) -> str:
        manager = getattr(self.context, "provider_manager", None)
        if manager is None:
            return ""
        try:
            provider = await manager.get_using_provider_async(ptype, umo)
        except Exception:
            return ""
        if provider is None:
            return ""
        try:
            return str(provider.meta().id or "")
        except Exception:
            return ""

    async def _current_kb_ids(self, umo: str) -> list[str]:
        try:
            cfg = await sp.session_get(umo, "kb_config", {}) or {}
        except Exception:
            cfg = {}
        if isinstance(cfg, dict) and cfg.get("kb_ids"):
            return [str(x) for x in cfg["kb_ids"]]
        names: list[str] = []
        try:
            names = list((self.context.get_config(umo=umo) or {}).get("kb_names") or [])
        except Exception:
            names = []
        if not names:
            return []
        by_name = {kb["name"]: kb["id"] for kb in await self._kb_options()}
        return [by_name[n] for n in names if n in by_name]

    def _pack_rules(self) -> list[dict]:
        data = _read_json(self._meme_dir() / "selection_rules.json", {})
        rules = data.get("rules") if isinstance(data, dict) else None
        return [r for r in rules if isinstance(r, dict)] if isinstance(rules, list) else []

    def _current_pack_ids(self, umo: str, persona_id: str) -> list[str]:
        targets = self._rule_targets(umo)
        valid = self._valid_pack_ids()
        default_ids: list[str] = []
        for rule in self._pack_rules():
            scope = str(rule.get("scope") or "").lower()
            target = str(rule.get("target") or "")
            raw = rule.get("pack_ids")
            if not isinstance(raw, list):
                raw = [rule.get("pack_id")] if rule.get("pack_id") else []
            candidates = [str(x) for x in raw if str(x or "").strip() and str(x) in valid]
            if not candidates:
                continue
            if scope == "session" and target in targets:
                return candidates
            if scope == "persona" and persona_id and target == persona_id:
                return candidates
            if scope == "default":
                default_ids = candidates
        return default_ids

    async def _draft_from_session(self, umo: str) -> dict:
        effective = await self._effective(umo)
        persona_id = effective["persona_id"]
        if not persona_id:
            try:
                resolved, _persona, _force, _webchat = (
                    await self.context.persona_manager.resolve_selected_persona(
                        umo=umo,
                        conversation_persona_id=None,
                        platform_name=self._platform_of(umo),
                    )
                )
                persona_id = str(resolved or "")
            except Exception:
                persona_id = ""

        name = persona_id or "新角色卡"
        return {
            "id": f"c_{uuid.uuid4().hex[:8]}",
            "name": name[:40],
            "emoji": "🐟",
            "persona_id": persona_id,
            "tts_provider_id": effective["tts_provider_id"],
            "chat_provider_id": effective["chat_provider_id"],
            "kb_ids": effective["kb_ids"],
            "meme_pack_ids": effective["meme_pack_ids"],
            "prompt_append": "",
            "notes": f"从会话 {umo} 生成于 {time.strftime('%Y-%m-%d %H:%M')}",
        }

    @staticmethod
    def _platform_of(umo: str) -> str:
        parts = umo.split(":")
        return parts[0] if parts else ""
