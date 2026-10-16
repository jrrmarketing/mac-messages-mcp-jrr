import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mac_messages_mcp.messages import (
    _structured_attachment,
    _structured_attachments_for_message_ids,
    get_message_history_page,
    paginate_message_rows,
)


def message_row(row_id: int, text: str = "") -> dict:
    return {
        "ROWID": row_id,
        "date": 800_000_000_000_000_000 - row_id,
        "text": text,
        "attributedBody": None,
        "is_from_me": 0,
        "handle_id": 7,
        "handle": "+447700900123",
        "service": "SMS",
        "cache_roomnames": None,
    }


def attachment_row(
    path: Path,
    *,
    attachment_id: int = 42,
    message_id: int = 101,
    mime: str = "text/plain",
) -> dict:
    return {
        "id": attachment_id,
        "message_id": message_id,
        "filename": path.name,
        "path": str(path),
        "mime_type": mime,
        "uti": "public.plain-text",
        "size_bytes": path.stat().st_size,
        "exists": True,
    }


def test_later_page_attachment_is_bound_to_its_parent_before_coverage_completes(
    tmp_path,
):
    source = tmp_path / "instruction.txt"
    source.write_text("Please do not contact me again", encoding="utf-8")
    rows = [message_row(i, f"ordinary {i}") for i in range(1, 101)] + [message_row(101)]
    attachments = {101: [_structured_attachment(attachment_row(source))]}

    first = paginate_message_rows(
        rows,
        searched_identity="+447700900123",
        resolved_handles=["+447700900123"],
        attachments_by_message=attachments,
        limit=100,
    )
    second = paginate_message_rows(
        rows,
        searched_identity="+447700900123",
        resolved_handles=["+447700900123"],
        attachments_by_message=attachments,
        limit=100,
        cursor=first["next_cursor"],
        snapshot=first["snapshot"],
    )

    assert first["coverage_complete"] is False
    assert first["attachment_count"] == 1
    assert first["attachment_content_complete"] is True
    assert second["coverage_complete"] is True
    assert second["messages"][0]["attachments"][0]["message_id"] == "101"
    assert second["messages"][0]["attachments"][0]["content_state"] == "readable_text"
    assert (
        second["messages"][0]["attachments"][0]["content_text"]
        == "Please do not contact me again"
    )


@pytest.mark.parametrize(
    "mime,filename,state",
    [
        ("audio/mp4", "note.m4a", "review_required"),
        ("image/png", "note.jpg", "mime_mismatch"),
    ],
)
def test_unreadable_or_mismatched_media_stays_explicit(tmp_path, mime, filename, state):
    source = tmp_path / filename
    source.write_bytes(b"synthetic-media")

    evidence = _structured_attachment(attachment_row(source, mime=mime))

    assert evidence["content_state"] == state
    assert evidence["content_text"] is None
    assert evidence["content_sha256"] is not None


def test_missing_or_replaced_attachment_changes_the_snapshot(tmp_path):
    source = tmp_path / "instruction.txt"
    source.write_text("first", encoding="utf-8")
    first_attachment = _structured_attachment(attachment_row(source, message_id=1))
    first = paginate_message_rows(
        [message_row(1)],
        searched_identity="+447700900123",
        resolved_handles=["+447700900123"],
        attachments_by_message={1: [first_attachment]},
        limit=1,
    )

    source.write_text("replacement", encoding="utf-8")
    second_attachment = _structured_attachment(attachment_row(source, message_id=1))

    assert second_attachment["content_sha256"] != first_attachment["content_sha256"]
    assert (
        paginate_message_rows(
            [message_row(1)],
            searched_identity="+447700900123",
            resolved_handles=["+447700900123"],
            attachments_by_message={1: [second_attachment]},
            limit=1,
        )["snapshot"]
        != first["snapshot"]
    )


def test_duplicate_attachment_id_under_conflicting_parent_is_rejected(tmp_path):
    source = tmp_path / "instruction.txt"
    source.write_text("bounded fixture", encoding="utf-8")
    left = _structured_attachment(
        attachment_row(source, attachment_id=42, message_id=1)
    )
    right = _structured_attachment(
        attachment_row(source, attachment_id=42, message_id=2)
    )

    with pytest.raises(ValueError, match="MESSAGES_ATTACHMENT_IDENTITY_CONFLICT"):
        paginate_message_rows(
            [message_row(1), message_row(2)],
            searched_identity="+447700900123",
            resolved_handles=["+447700900123"],
            attachments_by_message={1: [left], 2: [right]},
        )


def test_attachment_database_failure_never_looks_like_no_attachments():
    with patch(
        "mac_messages_mcp.messages.query_messages_db",
        side_effect=[
            [{"ROWID": 7, "id": "buyer@example.test"}],
            [message_row(1)],
            [{"error": "attachment join unavailable"}],
        ],
    ):
        with pytest.raises(
            ValueError, match="MESSAGES_ATTACHMENT_DATABASE_UNAVAILABLE"
        ):
            get_message_history_page(contact="buyer@example.test")


def test_deleted_attachment_is_a_visible_incomplete_content_state(tmp_path):
    source = tmp_path / "gone.txt"
    source.write_text("temporary", encoding="utf-8")
    shaped = attachment_row(source)
    os.unlink(source)
    shaped.update({"exists": False, "size_bytes": 0})

    evidence = _structured_attachment(shaped)

    assert evidence["content_state"] == "missing"
    assert evidence["content_sha256"] is None
    assert evidence["content_text"] is None


def test_attachment_lookup_is_chunked_before_sqlite_bind_limits():
    with patch(
        "mac_messages_mcp.messages._attachments_for_message_ids",
        return_value={},
    ) as lookup:
        assert _structured_attachments_for_message_ids(list(range(1, 1_202))) == {}

    assert [len(call.args[0]) for call in lookup.call_args_list] == [500, 500, 201]
    assert all(call.kwargs == {"strict": True} for call in lookup.call_args_list)


def test_too_many_attachments_fails_closed(tmp_path):
    source = tmp_path / "instruction.txt"
    source.write_text("bounded", encoding="utf-8")
    rows = [
        attachment_row(source, attachment_id=index, message_id=1)
        for index in range(1, 1_002)
    ]
    with patch(
        "mac_messages_mcp.messages._attachments_for_message_ids",
        return_value={1: rows},
    ):
        with pytest.raises(ValueError, match="MESSAGES_ATTACHMENT_LIMIT_REACHED"):
            _structured_attachments_for_message_ids([1])
