# JRR fork notes (0.9.3+jrr.1)

Patches on upstream [mac_messages_mcp](https://github.com/carterlasalle/mac_messages_mcp):

1. **SMS-first routing** — phone numbers without iMessage history skip iMessage AppleScript entirely.
2. **Post-send verification** — polls `chat.db` after send; results prefixed with `verified:`, `unverified:`, or `failed:`.
3. **`tool_preflight_send`** — one-call route + agent guidance before sending.
4. **Exact email history** — email addresses query Messages handles directly instead of fuzzy contact-name lookup. A database error remains an error, never empty history.

Validate local releases with `uv sync --frozen --extra dev` and `uv run --frozen --extra dev pytest -q`. This fork has no PR CI or cloud deployment; require the local suite before merging. Deploy the exact merged source as a runtime snapshot and verify an authenticated read through the configured MCP launcher. Preserve dirty development checkouts when installing a runtime snapshot.

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
