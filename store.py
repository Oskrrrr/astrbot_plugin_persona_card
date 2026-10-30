"""角色卡存储：卡片定义 + 会话绑定 + 会话记录。"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any


class CardStore:
    """一个 JSON 文件里存三类数据：cards / bindings / sessions。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.cards: list[dict[str, Any]] = []
        self.bindings: dict[str, str] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.dirty = False
        self.load()

    # ---------- io ----------

    def load(self) -> None:
        data: dict[str, Any] = {}
        try:
            if self.path.is_file():
                with self.path.open(encoding="utf-8") as fh:
                    data = json.load(fh)
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        cards = data.get("cards")
        self.cards = [c for c in cards if isinstance(c, dict)] if isinstance(cards, list) else []
        bindings = data.get("bindings")
        self.bindings = {str(k): str(v) for k, v in bindings.items()} if isinstance(bindings, dict) else {}
        sessions = data.get("sessions")
        self.sessions = {str(k): v for k, v in sessions.items() if isinstance(v, dict)} if isinstance(sessions, dict) else {}

    def save(self) -> None:
        with self._lock:
            payload = {
                "version": 1,
                "updated_at": int(time.time()),
                "cards": self.cards,
                "bindings": self.bindings,
                "sessions": self.sessions,
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
            self.dirty = False

    # ---------- cards ----------

    def get_card(self, card_id: str) -> dict[str, Any] | None:
        for card in self.cards:
            if card.get("id") == card_id:
                return card
        return None

    def upsert_card(self, card: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            now = int(time.time())
            existing = self.get_card(card["id"])
            if existing is None:
                card["created_at"] = now
                self.cards.append(card)
            else:
                existing.update(card)
                card = existing
            card["updated_at"] = now
            self.dirty = True
            return card

    def delete_card(self, card_id: str) -> bool:
        with self._lock:
            before = len(self.cards)
            self.cards = [c for c in self.cards if c.get("id") != card_id]
            for umo in [u for u, cid in self.bindings.items() if cid == card_id]:
                self.bindings.pop(umo, None)
            self.dirty = True
            return len(self.cards) < before

    def bind(self, umo: str, card_id: str) -> None:
        with self._lock:
            if card_id:
                self.bindings[umo] = card_id
            else:
                self.bindings.pop(umo, None)
            self.dirty = True

    # ---------- sessions ----------

    def touch_session(self, umo: str, kind: str, label: str, last_text: str = "") -> None:
        with self._lock:
            rec = self.sessions.get(umo) or {}
            rec["kind"] = kind or rec.get("kind") or ""
            rec["label"] = label or rec.get("label") or umo
            rec["last_seen"] = int(time.time())
            if last_text:
                rec["last_text"] = last_text[:60]
            self.sessions[umo] = rec
            self.dirty = True
