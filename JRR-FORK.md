# JRR fork notes (0.9.3+jrr.1)

Patches on upstream [mac_messages_mcp](https://github.com/carterlasalle/mac_messages_mcp):

1. **SMS-first routing** — phone numbers without iMessage history skip iMessage AppleScript entirely.
2. **Post-send verification** — polls `chat.db` after send; results prefixed with `verified:`, `unverified:`, or `failed:`.
3. **`tool_preflight_send`** — one-call route + agent guidance before sending.

Configured in `~/.cursor/mcp.json`:

```json
"messages": {
  "command": "uv",
  "args": ["run", "--project", "/Users/josiah/Projects/mac-messages-mcp", "mac-messages-mcp"]
}
```

GitHub: https://github.com/jrrmarketing/mac-messages-mcp-jrr

Restart Cursor (or reload MCP) after pulling changes.

Agent rules: `~/.cursor/rules/messages-mcp.mdc`
