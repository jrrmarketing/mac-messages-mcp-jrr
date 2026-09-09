from unittest.mock import patch

from mac_messages_mcp.messages import get_recent_messages


def test_email_history_uses_exact_handle_not_contact_name():
    with patch("mac_messages_mcp.messages.find_contact_by_name") as names, patch(
        "mac_messages_mcp.messages.query_messages_db", return_value=[]
    ) as query:
        result = get_recent_messages(contact="buyer+sales@example.com")
    names.assert_not_called()
    query.assert_called_once_with(
        "SELECT ROWID FROM handle WHERE id = ?", ("buyer+sales@example.com",)
    )
    assert result == "No message history found with 'buyer+sales@example.com'."


def test_email_history_database_failure_is_not_empty_history():
    with patch(
        "mac_messages_mcp.messages.query_messages_db",
        return_value=[{"error": "database access failed"}],
    ):
        result = get_recent_messages(contact="buyer@example.com")
    assert result.startswith("Error:")
