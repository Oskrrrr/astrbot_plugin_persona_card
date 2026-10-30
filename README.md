# 角色卡（astrbot_plugin_persona_card）

把人格、音色、聊天模型、知识库、表情包绑成一张角色卡，一键应用到某个会话，随时切换。

## 功能

- 一张卡绑定：人格、TTS 音色、聊天模型、知识库、表情包（可多选）。
- 应用到会话：写入 AstrBot 原生的会话级偏好，立即生效，不需要重启。
- 解除绑定：清掉该会话的角色卡覆盖，回到全局默认。
- 从会话生成草稿：把当前会话已生效的人格/模型/知识库/表情包抄成一张新卡。
- 风格补充：把卡片里的 `prompt_append` 追加到该会话的系统提示词。
- 说说板块：给「QQ空间外挂」读取 `post_prompt` / `image_style` / `image_requirements` / `image_negative`。
- 会话记录：页面里可以直接选最近出现过的群/私聊，不用手填会话标识。

## 使用

1. 打开 WebUI 的「插件 → 角色卡」页面。
2. 新建卡片，选人格、音色、聊天模型、知识库、表情包，按需填风格补充和说说板块。
3. 在右侧会话列表选目标会话，点「应用」。
4. 想恢复默认，点「解绑」。

## 与 meme_manager 的关系

- 读取 `data/plugin_data/meme_manager/registry.json` 获取已安装表情包。
- 读写 `data/plugin_data/meme_manager/selection_rules.json` 里的会话级选包规则。
- [meme_manager](https://github.com/anka-afk/astrbot_plugin_meme_manager) 是 anka 的 MIT 项目；本插件没有复制其代码，只按它的运行数据格式做联动。meme_manager 升级若改变规则格式，联动可能需要同步适配；应用前会做基本的 ID 校验。

## 与 QQ空间外挂的关系

装了 `astrbot_plugin_qzone_ext` 时，说说外挂会通过本插件的 `qzone_profile()` 读取当前人格对应卡片的「说说」板块；没装时两边各自独立工作。

## 许可

MIT，见 [LICENSE](./LICENSE)。
