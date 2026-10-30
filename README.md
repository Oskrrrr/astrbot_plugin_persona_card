<div align="center">

# 🎭 角色卡

[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.16-27a7d8)](https://github.com/AstrBotDevs/AstrBot)
[![Release](https://img.shields.io/github/v/release/Oskrrrr/astrbot_plugin_persona_card?color=27a7d8&label=Release)](https://github.com/Oskrrrr/astrbot_plugin_persona_card/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)

**把人格、音色、聊天模型、知识库、表情包绑成一张卡，一键应用到会话，随时切换。**

</div>

## ✨ 特色

| 你想做什么 | 角色卡怎么帮你 |
|---|---|
| 一个会话一套设定 | 一张卡绑定人格、TTS 音色、聊天模型、知识库、表情包 |
| 一键切换 | 在页面选会话点「应用」，写 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 原生会话偏好，立即生效，不用重启 |
| 多表情包 | 一张卡最多绑 5 个表情包，写入 [meme_manager](https://github.com/anka-afk/astrbot_plugin_meme_manager) 的会话选包规则 |
| 随时恢复 | 「解绑」清掉该会话覆盖，回到全局默认 |
| 从现有会话抄作业 | 「存为卡」把当前会话的人格/模型/知识库/表情包生成一张新卡 |
| 风格补充 | 卡片里的 `prompt_append` 追加到该会话系统提示词 |
| 和说说外挂联动 | 给 [qzone_ext](https://github.com/Oskrrrr/astrbot_plugin_qzone_ext) 提供说说提示词、画风、画面要求/负面词 |

## 🚀 快速开始

1. 把目录放进 `AstrBot/data/plugins/astrbot_plugin_persona_card`。
2. 重启 AstrBot，或重载插件。
3. 打开 WebUI 的「插件 → 角色卡」页面。
4. 新建卡片，选人格、音色、聊天模型、知识库、表情包，按需填风格补充和说说板块。
5. 在右侧会话列表选目标会话，点「应用」。

想恢复默认，点「解绑」。

## 🧠 一张卡里有什么

| 字段 | 作用 |
|---|---|
| 人格 | 会话级强制人格；留空则沿用全局默认 |
| 音色 | 会话级 TTS provider；留空则沿用全局默认 |
| 聊天模型 | 会话级 CHAT provider；留空则沿用全局默认 |
| 知识库 | 会话级 `kb_config.kb_ids`；可多选 |
| 表情包 | 会话级选包规则；最多 5 个，需在 [meme_manager](https://github.com/anka-afk/astrbot_plugin_meme_manager) 里已启用 |
| 风格补充 | 追加到该会话系统提示词的稳定文本 |
| 说说板块 | 给 [QQ空间外挂](https://github.com/Oskrrrr/astrbot_plugin_qzone_ext) 读取的 `post_prompt` / `image_style` / `image_requirements` / `image_negative` |

「应用」写入的是 AstrBot 原生的会话级偏好（`session_service_config` / `provider_perf_*` / `kb_config`），所以切换立即生效，也不需要改别人插件的代码。

## 🖼️ 表情包多选

- 页面会列出 [meme_manager](https://github.com/anka-afk/astrbot_plugin_meme_manager) 里已安装、已启用的包。
- 一张卡最多选 5 个；应用时写会话级 `selection_rules.json` 规则。
- 如果某个包后来被禁用/删除，应用时会跳过并给出警告。
- 没装 [meme_manager](https://github.com/anka-afk/astrbot_plugin_meme_manager) 时，表情包板块自动留空，不影响其它字段。

## 🌌 与 [QQ空间外挂](https://github.com/Oskrrrr/astrbot_plugin_qzone_ext)

装了 [astrbot_plugin_qzone_ext](https://github.com/Oskrrrr/astrbot_plugin_qzone_ext) 时，说说外挂会通过本插件的 `qzone_profile()` 读取当前人格对应卡片的「说说」板块：

- 说说写作要求
- 配图画风
- 画面要求 / 负面词

没装说说外挂时，这些字段只是存着，不影响聊天。

## 🧩 与 [meme_manager](https://github.com/anka-afk/astrbot_plugin_meme_manager)

- 读取 `data/plugin_data/meme_manager/registry.json` 获取已安装表情包。
- 读写 `data/plugin_data/meme_manager/selection_rules.json` 里的会话级选包规则。
- [meme_manager](https://github.com/anka-afk/astrbot_plugin_meme_manager) 是 anka 的 MIT 项目；本插件没有复制其代码，只按它的运行数据格式做联动。meme_manager 升级若改变规则格式，联动可能需要同步适配；应用前会做基本的 ID 校验。

## 📄 许可

MIT，见 [LICENSE](./LICENSE)。
