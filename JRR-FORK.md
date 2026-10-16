# JRR fork notes (0.9.3+jrr.3)

Patches on upstream [mac_messages_mcp](https://github.com/carterlasalle/mac_messages_mcp):

1. **SMS-first routing** — phone numbers without iMessage history skip iMessage AppleScript entirely.
2. **Post-send verification** — polls `chat.db` after send; results prefixed with `verified:`, `unverified:`, or `failed:`.
3. **`tool_preflight_send`** — one-call route + agent guidance before sending.
4. **Exact email history** — email addresses query Messages handles directly instead of fuzzy contact-name lookup. A database error remains an error, never empty history.
5. **Structured complete history** — `tool_get_message_history_page` returns exact-identity, snapshot-bound pages with explicit completion, stable cursors, matched-handle provenance, and source-change rejection.
6. **Attachment-aware history** — structured pages bind attachment evidence to the parent message. Bounded UTF-8 text is readable; media and unresolved files stay explicit review blockers with content hashes and limits.

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
