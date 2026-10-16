from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from mac_messages_mcp.messages import get_message_history_page, paginate_message_rows


def row(row_id: int, text: str, handle: str = "+447700900123") -> dict:
    return {
        "ROWID": row_id,
        "date": 800_000_000_000_000_000 - row_id,
        "text": text,
        "attributedBody": None,
        "is_from_me": 0,
        "handle_id": 7,
        "handle": handle,
        "service": "SMS",
        "cache_roomnames": None,
    }


def test_structured_history_pages_past_the_old_newest_100_boundary():
    rows = [row(i, f"ordinary reply {i}") for i in range(1, 101)]
    rows.append(row(101, "STOP"))

    first = paginate_message_rows(
        rows,
        searched_identity="+447700900123",
        resolved_handles=["+447700900123"],
        limit=100,
        checked_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
    )

    assert first["schema"] == "jrr-messages-history-v1"
    assert first["page_complete"] is True
    assert first["coverage_complete"] is False
    assert first["returned_count"] == 100
    assert first["message_count"] == 101
    assert first["next_cursor"]

    second = paginate_message_rows(
        rows,
        searched_identity="+447700900123",
        resolved_handles=["+447700900123"],
        limit=100,
        cursor=first["next_cursor"],
        snapshot=first["snapshot"],
        checked_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
    )

    assert second["coverage_complete"] is True
    assert second["next_cursor"] is None
    assert [message["text"] for message in second["messages"]] == ["STOP"]
    assert second["messages"][0]["handle"] == "+447700900123"
    assert second["messages"][0]["direction"] == "inbound"


def test_structured_history_cursor_is_snapshot_bound_and_rejects_changed_source():
    rows = [row(i, f"message {i}") for i in range(1, 4)]
    first = paginate_message_rows(
        rows,
        searched_identity="+447700900123",
        resolved_handles=["+447700900123"],
        limit=2,
    )

    changed = [*rows]
    changed[2] = {**changed[2], "text": "changed while paging"}
    with pytest.raises(ValueError, match="MESSAGES_HISTORY_CHANGED_RESTART"):
        paginate_message_rows(
            changed,
            searched_identity="+447700900123",
            resolved_handles=["+447700900123"],
            limit=2,
            cursor=first["next_cursor"],
            snapshot=first["snapshot"],
        )


@pytest.mark.parametrize(
    "cursor,snapshot,error",
    [
        ("not-a-cursor", "0" * 64, "MESSAGES_CURSOR_INVALID"),
        (None, "0" * 64, "MESSAGES_SNAPSHOT_WITHOUT_CURSOR"),
    ],
)
def test_structured_history_rejects_stale_or_malformed_continuations(
    cursor, snapshot, error
):
    with pytest.raises(ValueError, match=error):
        paginate_message_rows(
            [row(1, "hello")],
            searched_identity="+447700900123",
            resolved_handles=["+447700900123"],
            limit=1,
            cursor=cursor,
            snapshot=snapshot,
        )


def test_structured_history_preserves_empty_complete_coverage():
    result = paginate_message_rows(
        [],
        searched_identity="buyer@example.test",
        resolved_handles=["buyer@example.test"],
        limit=100,
    )
    assert result["coverage_complete"] is True
    assert result["message_count"] == 0
    assert result["messages"] == []


def test_exact_email_history_returns_structured_rows_without_fuzzy_contact_resolution():
    source_rows = [row(1, "Please do not contact me again", "buyer@example.test")]

    with (
        patch(
            "mac_messages_mcp.messages.query_messages_db",
            side_effect=[[{"ROWID": 7, "id": "buyer@example.test"}], source_rows],
        ) as query,
        patch("mac_messages_mcp.messages.find_contact_by_name") as names,
    ):
        result = get_message_history_page(
            hours=24,
            contact="buyer@example.test",
            limit=100,
        )

    names.assert_not_called()
    assert query.call_count == 2
    assert result["resolved_handles"] == ["buyer@example.test"]
    assert result["coverage_complete"] is True
    assert result["messages"][0]["text"] == "Please do not contact me again"


def test_structured_history_propagates_database_failure_instead_of_reporting_empty_coverage():
    with patch(
        "mac_messages_mcp.messages.query_messages_db",
        return_value=[{"error": "database access denied"}],
    ):
        with pytest.raises(ValueError, match="MESSAGES_DATABASE_UNAVAILABLE"):
            get_message_history_page(contact="buyer@example.test")


def test_phone_history_propagates_database_failure_instead_of_reporting_empty_coverage():
    with patch(
        "mac_messages_mcp.messages.query_messages_db",
        return_value=[{"error": "database access denied"}],
    ):
        with pytest.raises(ValueError, match="MESSAGES_DATABASE_UNAVAILABLE"):
            get_message_history_page(contact="+447700900123")


def test_exact_phone_history_queries_all_supported_handle_formats():
    with patch(
        "mac_messages_mcp.messages.query_messages_db",
        return_value=[],
    ) as query:
        result = get_message_history_page(contact="+44 7700 900123")

    assert query.call_count == 1
    assert query.call_args.args[1] == ("447700900123", "+447700900123")
    assert result["coverage_complete"] is True
    assert result["message_count"] == 0
