"""
Delivery routing and post-send verification for macOS Messages.

JRR fork improvements:
- SMS-first when iMessage is not available for phone numbers
- Post-send chat.db verification so "success" means the message actually landed
- Preflight recommendations for agents
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

SMS_SERVICES = {"SMS", "RCS"}
IMESSAGE_SERVICES = {"iMessage", "iMessageLite"}


def _messages():
    from mac_messages_mcp import messages as messages_module

    return messages_module


def _recipient_handle_ids(recipient: str) -> List[int]:
    messages = _messages()

    if "@" in recipient:
        rows = messages.query_messages_db("SELECT ROWID FROM handle WHERE id = ?", (recipient,))
        if rows and "error" not in rows[0]:
            return [row["ROWID"] for row in rows]
        return []

    handles = messages.find_handles_by_phone(recipient)
    return handles or []


def _handle_delivery_stats(recipient: str) -> List[Dict[str, Any]]:
    messages = _messages()

    if "@" in recipient:
        params: tuple = (recipient,)
        placeholders = "?"
    else:
        normalized = messages.normalize_phone_number(recipient)
        if not normalized:
            return []
        params = tuple(messages._get_phone_formats(normalized))
        placeholders = ", ".join(["?" for _ in params])

    query = f"""
        SELECT
            h.service,
            COUNT(m.ROWID) AS text_count,
            COUNT(CASE WHEN m.error != 0 THEN 1 END) AS errors
        FROM handle h
        LEFT JOIN message m ON h.ROWID = m.handle_id
        WHERE h.id IN ({placeholders})
        GROUP BY h.service
    """
    rows = messages.query_messages_db(query, params)
    if not rows or "error" in rows[0]:
        return []
    return rows


def choose_delivery_route(recipient: str, group_chat: bool = False) -> str:
    """Return imessage, sms, or email_imessage."""
    messages = _messages()

    if group_chat:
        return "imessage"

    if "@" in recipient:
        return "email_imessage"

    if messages._looks_like_phone_input(recipient) or any(
        ch.isdigit() for ch in recipient
    ):
        return (
            "imessage"
            if messages._check_imessage_availability(recipient)
            else "sms"
        )

    return "imessage"


def get_delivery_plan(recipient: str, group_chat: bool = False) -> Dict[str, Any]:
    """Build a structured delivery plan for agents and preflight tooling."""
    recipient = str(recipient).strip()
    route = choose_delivery_route(recipient, group_chat=group_chat)
    stats = _handle_delivery_stats(recipient)

    imessage_ok = _messages()._check_imessage_availability(recipient)
    sms_history = any(
        row.get("service") in SMS_SERVICES
        and (row.get("errors") or 0) < (row.get("text_count") or 0)
        for row in stats
    )
    imessage_history = any(
        row.get("service") in IMESSAGE_SERVICES
        and (row.get("errors") or 0) < (row.get("text_count") or 0)
        for row in stats
    )
    failed_imessage = any(
        row.get("service") in IMESSAGE_SERVICES and (row.get("errors") or 0) > 0
        for row in stats
    )

    if group_chat:
        recommendation = "mcp_send"
        confidence = "high"
        summary = "Group chat — send via iMessage using the chat ID."
    elif route == "email_imessage":
        recommendation = "mcp_send" if imessage_ok else "manual_or_email"
        confidence = "medium" if imessage_ok else "low"
        summary = "Email handle — iMessage when available."
    elif route == "sms":
        recommendation = "mcp_send_sms"
        confidence = "high" if sms_history or not stats else "medium"
        summary = (
            "SMS-only phone — MCP will skip iMessage and verify in chat.db after send."
        )
        if failed_imessage:
            summary += " Prior iMessage attempts to this number failed."
    else:
        recommendation = "mcp_send"
        confidence = "high" if imessage_history else "medium"
        summary = "iMessage available — MCP will send via iMessage and verify after send."

    return {
        "recipient": recipient,
        "route": route,
        "imessage_available": imessage_ok,
        "sms_history": sms_history,
        "imessage_history": imessage_history,
        "failed_imessage_history": failed_imessage,
        "recommendation": recommendation,
        "confidence": confidence,
        "summary": summary,
        "stats": stats,
    }


def format_delivery_plan(plan: Dict[str, Any]) -> str:
    """Plain-text plan for MCP tools."""
    lines = [
        f"Recipient: {plan['recipient']}",
        f"Route: {plan['route']}",
        f"iMessage available: {'yes' if plan['imessage_available'] else 'no'}",
        f"Recommendation: {plan['recommendation']} ({plan['confidence']} confidence)",
        plan["summary"],
    ]
    if plan.get("stats"):
        lines.append("Handle history:")
        for row in plan["stats"]:
            lines.append(
                "  - {service}: {count} messages, {errors} errors".format(
                    service=row.get("service", "?"),
                    count=row.get("text_count", 0),
                    errors=row.get("errors", 0),
                )
            )
    return "\n".join(lines)


def verify_outbound_delivery(
    recipient: str,
    message: str,
    since_apple_ns: str,
    expected_route: str,
    max_attempts: int = 6,
    delay_seconds: float = 0.5,
) -> Dict[str, Any]:
    """
    Poll chat.db for a recent outbound message to the recipient.

    Returns verified=True when a matching outbound row exists with error=0.
    """
    messages = _messages()

    if "@" in recipient:
        params: tuple = (recipient,)
        placeholders = "?"
    else:
        formatted = messages._format_phone_for_messages(recipient) or recipient
        normalized = messages.normalize_phone_number(formatted)
        if not normalized:
            return {"verified": False, "reason": "invalid_phone"}
        params = tuple(messages._get_phone_formats(normalized))
        placeholders = ", ".join(["?" for _ in params])

    snippet = (message or "").strip()
    snippet = snippet[:120] if snippet else ""
    expected_sms = expected_route == "sms"

    query = f"""
        SELECT
            m.text,
            m.service,
            m.error,
            m.is_from_me,
            m.date
        FROM message m
        JOIN handle h ON m.handle_id = h.ROWID
        WHERE h.id IN ({placeholders})
          AND m.is_from_me = 1
          AND CAST(m.date AS TEXT) > ?
        ORDER BY m.date DESC
        LIMIT 15
    """

    for attempt in range(max_attempts):
        if attempt:
            time.sleep(delay_seconds)
        rows = messages.query_messages_db(query, params + (since_apple_ns,))
        if not rows:
            continue
        if isinstance(rows[0].get("error"), str):
            continue

        for row in rows:
            text = (row.get("text") or "").strip()
            service = row.get("service") or ""
            error = row.get("error") or 0

            if snippet and text and snippet not in text and text not in snippet:
                continue

            service_upper = service.upper()
            is_sms = service_upper in {s.upper() for s in SMS_SERVICES}
            is_imessage = service_upper in {s.upper() for s in IMESSAGE_SERVICES}

            if error:
                return {
                    "verified": False,
                    "reason": "delivery_error",
                    "service": service,
                    "error": error,
                }

            if expected_sms and is_imessage:
                return {
                    "verified": False,
                    "reason": "wrong_service",
                    "service": service,
                }

            if expected_sms and not is_sms:
                return {
                    "verified": False,
                    "reason": "wrong_service",
                    "service": service,
                }

            return {
                "verified": True,
                "service": service,
                "text": text,
            }

        # Accept the newest outbound row in-window if body matching is unavailable.
        if rows and not snippet:
            row = rows[0]
            if not (row.get("error") or 0):
                return {
                    "verified": True,
                    "service": row.get("service") or "",
                    "text": row.get("text") or "",
                }

    return {"verified": False, "reason": "not_in_db"}


def send_timestamp_ns() -> str:
    """Apple-ns timestamp a couple seconds before send for verification window."""
    since = datetime.now(timezone.utc) - timedelta(seconds=3)
    return str(_messages()._to_apple_ns(since))


def finalize_send_result(
    recipient: str,
    message: str,
    send_result: str,
    since_apple_ns: str,
    route: str,
    contact_name: Optional[str] = None,
) -> str:
    """Combine AppleScript result with chat.db verification."""
    display_name = contact_name or recipient

    if send_result.startswith("Error") or "error:" in send_result.lower():
        return send_result

    verification = verify_outbound_delivery(
        recipient=recipient,
        message=message,
        since_apple_ns=since_apple_ns,
        expected_route=route,
    )

    if verification.get("verified"):
        service = verification.get("service") or route.upper()
        return (
            f"verified:{service} Message sent and confirmed in Messages database "
            f"to {display_name}"
        )

    reason = verification.get("reason", "not_in_db")
    if reason == "wrong_service":
        service = verification.get("service", "iMessage")
        return (
            f"failed:wrong_route AppleScript accepted the send but chat.db shows "
            f"{service} instead of SMS for {display_name}. Open Messages and resend "
            f"manually as Text Message (green bubble)."
        )
    if reason == "delivery_error":
        return (
            f"failed:delivery_error Message row exists but Messages flagged a delivery "
            f"error for {display_name}. Check the thread in Messages."
        )

    return (
        f"unverified:{route} AppleScript reported success but the message was not "
        f"confirmed in chat.db for {display_name}. Check Messages for a green or blue "
        f"bubble before logging as sent."
    )
