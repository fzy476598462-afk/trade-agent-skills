# 接入 WhatsApp MCP

本技能让 Agent 调用已经连接的 MCP，不另起 WhatsApp 登录程序，也不需要另一套 API 密钥。已接入其他兼容 WhatsApp MCP 的用户，可按实际工具名称和返回格式适配。

## 没有连接时

可使用 [lharries/whatsapp-mcp](https://github.com/lharries/whatsapp-mcp)。按该项目说明运行本机桥接程序，由使用者本人扫码，再把 Python MCP 服务加入所用 Agent。示例路径都是占位符：

```json
{
  "mcpServers": {
    "whatsapp": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/whatsapp-mcp/whatsapp-mcp-server",
        "run",
        "main.py"
      ]
    }
  }
}
```

Windows 将目录换成自己的实际目录，例如 `C:/tools/whatsapp-mcp/whatsapp-mcp-server`。上面是 Claude/Cursor 常用结构；其他 Agent 在其 MCP 设置中填相同命令和参数，不必照搬配置文件格式。桥接程序需要保持运行，MCP 可读历史以本机实际同步为准。

连接后先查看实际工具列表；本技能需要读取对话、分页读取消息和下载附件。不要为了本技能导出登录凭证、客户数据库或整个聊天历史。

## 调用与收据

- `list_chats(query, limit, page, include_last_message)`：只查用户给出的线索，不批量扫描联系人。
- `get_chat(chat_jid, include_last_message)`：核对已选对话。
- `list_messages(after, before, chat_jid, limit, page, include_context)`：`page` 从 0 开始，双方消息，不做关键词过滤；持续读到明确空页。日期使用服务所显示的时区，不能猜不同服务的时间含义。
- `download_media(message_id, chat_jid)`：成功通常返回 `{"success": true, "file_path": "本地文件路径"}`。只拿窗口内真实媒体消息的标识下载；不要把名称或手机尾号当消息标识。

上游 `list_messages` 可能返回格式化文字而非消息数组。普通文字消息不一定带消息 ID；其来源用页码及原文引用，不伪造平台消息 ID。媒体文字形如 `[image - Message ID: ... - Chat JID: ...]`；附件必须与它的对话和消息对应。

收据可用原始返回，也可保留 MCP 的 `content` / `structuredContent` 外壳；工具错误不能改成空数组。分页最后必须有明确空页（空数组或上游的 `No messages to display.`），不是只读默认的 20 条。此确认仅针对请求窗口，不证明桥接程序同步了全部历史。

## 整理输入

仓库的 `examples/whatsapp-rfq.json` 是完整虚构示例。Agent 读取真实返回后生成同样结构，字段说明如下：

| 字段 | 内容 |
| --- | --- |
| `scope` | 已核对的 `chat_jid`、`after`、`before`、每页 `limit` |
| `pages` | 连续页码的 `list_messages` 收据，含原调用参数和原结果 |
| `downloads` | `download_media` 收据，含窗口内媒体消息标识、对话和原结果 |
| `items` | Agent 结合原文与附件整理的当前需求，状态必须明确 |
| `evidence` | 每项的原文片段列表：`page`、`quote`；保留来源但不加入对外表格 |
| `quantity_evidence` | 明确行的数量依据：`page`、`quote`；原文必须包含在实际返回中 |
| `photo_message_id` / `photo_verified` | 对应图片消息；`true` 仅表示 Agent 确实看过并核对了对应关系 |
| `missing` / `reason` | 待确认项缺什么，或撤回项为什么不再纳入 |

脚本检查范围、分页、引用存在、附件文件、数量格式和共享文字中的常见联系方式/金额。语义是否一致、数量是否为最后确认值、图片是否对应仍由 Agent 核对，不保证识别全部隐私。

输出：`private-evidence.json` 及 `pending.json` 留在本地；`media/` 保存下载附件的副本；有明确需求时输出 `supplier-rfq.json`。它不会将对话标识、消息标识、联系人或整段聊天添加进供应商表格。

本技能只读取对话和下载附件，不发送。收到文档可继续原表翻译；发票、报价和运费不能从聊天整理过程自动编造。
