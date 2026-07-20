"""
Tests for delivery routing and verification helpers.
"""

import unittest
from unittest.mock import patch

from mac_messages_mcp.delivery import (
    MessagesDatabaseUnreadable,
    choose_delivery_route,
    db_access_error,
    finalize_send_result,
    format_delivery_plan,
    get_delivery_plan,
    verify_outbound_delivery,
)

DB_PERMISSION_ROW = [
    {
        "error": (
            "Cannot access Messages database. Please grant Full Disk Access "
            "permission to your terminal application."
        )
    }
]


class TestDeliveryRouting(unittest.TestCase):
    @patch("mac_messages_mcp.messages._check_imessage_availability", return_value=False)
    def test_choose_sms_for_phone_without_imessage(self, _mock_check):
        self.assertEqual(choose_delivery_route("+447888888779"), "sms")

    @patch("mac_messages_mcp.messages._check_imessage_availability", return_value=True)
    def test_choose_imessage_when_available(self, _mock_check):
        self.assertEqual(choose_delivery_route("+14155551234"), "imessage")

    def test_choose_email_route(self):
        self.assertEqual(
            choose_delivery_route("person@example.com"), "email_imessage"
        )


class TestDeliveryPlan(unittest.TestCase):
    @patch("mac_messages_mcp.delivery._handle_delivery_stats", return_value=[])
    @patch("mac_messages_mcp.messages._check_imessage_availability", return_value=False)
    def test_sms_plan_recommends_mcp_sms(self, _mock_check, _mock_stats):
        plan = get_delivery_plan("+447888888779")
        self.assertEqual(plan["route"], "sms")
        self.assertEqual(plan["recommendation"], "mcp_send_sms")
        self.assertIn("SMS-only", format_delivery_plan(plan))


class TestFinalizeSendResult(unittest.TestCase):
    @patch(
        "mac_messages_mcp.delivery.verify_outbound_delivery",
        return_value={"verified": True, "service": "SMS"},
    )
    def test_verified_prefix(self, _mock_verify):
        result = finalize_send_result(
            "+447888888779",
            "Hello",
            "SMS sent successfully",
            "123",
            "sms",
        )
        self.assertTrue(result.startswith("verified:SMS"))

    @patch(
        "mac_messages_mcp.delivery.verify_outbound_delivery",
        return_value={"verified": False, "reason": "wrong_service", "service": "iMessage"},
    )
    def test_wrong_route_failure(self, _mock_verify):
        result = finalize_send_result(
            "+447888888779",
            "Hello",
            "Message sent successfully",
            "123",
            "sms",
        )
        self.assertTrue(result.startswith("failed:wrong_route"))


class TestVerifyOutboundDelivery(unittest.TestCase):
    @patch("mac_messages_mcp.messages._get_phone_formats", return_value=["+447888888779"])
    @patch("mac_messages_mcp.messages.normalize_phone_number", return_value="447888888779")
    @patch(
        "mac_messages_mcp.messages._format_phone_for_messages",
        return_value="+447888888779",
    )
    @patch("mac_messages_mcp.messages.query_messages_db")
    def test_verifies_matching_outbound_sms(
        self, mock_query, _mock_format, _mock_norm, _mock_formats
    ):
        mock_query.return_value = [
            {
                "text": "Hey Miro, test",
                "service": "SMS",
                "error": 0,
                "is_from_me": 1,
                "date": 999,
            }
        ]
        result = verify_outbound_delivery(
            "+447888888779",
            "Hey Miro, test",
            "1",
            "sms",
            max_attempts=1,
            delay_seconds=0,
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["service"], "SMS")

    @patch("mac_messages_mcp.messages.query_messages_db", return_value=[])
    def test_not_in_db(self, _mock_query):
        result = verify_outbound_delivery(
            "+447888888779",
            "Hello",
            "1",
            "sms",
            max_attempts=1,
            delay_seconds=0,
        )
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "not_in_db")


class TestNoDatabaseAccess(unittest.TestCase):
    """A missing Full Disk Access grant must never look like a failed send."""

    def test_db_access_error_detects_permission_row(self):
        self.assertIsNotNone(db_access_error(DB_PERMISSION_ROW))

    def test_db_access_error_ignores_ordinary_rows(self):
        self.assertIsNone(db_access_error([{"text": "hi", "error": 0}]))
        self.assertIsNone(db_access_error([]))

    @patch(
        "mac_messages_mcp.delivery._handle_delivery_stats",
        side_effect=MessagesDatabaseUnreadable("Cannot access Messages database."),
    )
    @patch("mac_messages_mcp.messages._check_imessage_availability", return_value=False)
    def test_plan_reports_unknown_instead_of_confident_sms(self, _check, _stats):
        plan = get_delivery_plan("+447888888779")
        self.assertIs(plan["db_readable"], False)
        self.assertEqual(plan["confidence"], "unknown")
        self.assertIsNone(plan["imessage_available"])

        rendered = format_delivery_plan(plan)
        self.assertIn("unknown (no database access)", rendered)
        self.assertIn("unverified guess", rendered)
        # The old bug: claiming SMS-only with high confidence on zero evidence.
        self.assertNotIn("high confidence", rendered)

    @patch("mac_messages_mcp.messages.query_messages_db", return_value=DB_PERMISSION_ROW)
    def test_verify_returns_no_db_access_without_retrying(self, mock_query):
        result = verify_outbound_delivery(
            "+447888888779", "Hello", "123", "sms", max_attempts=6
        )
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "no_db_access")
        # Must bail immediately rather than burning six retries on a permission error.
        self.assertEqual(mock_query.call_count, 1)

    @patch(
        "mac_messages_mcp.delivery.verify_outbound_delivery",
        return_value={"verified": False, "reason": "no_db_access", "error": "denied"},
    )
    def test_send_result_says_permission_not_failure(self, _verify):
        result = finalize_send_result(
            "+447888888779", "Hello", "SMS sent successfully", "123", "sms"
        )
        self.assertTrue(result.startswith("unverified:no_db_access"))
        self.assertIn("not a failed send", result)
        self.assertIn("Full Disk Access", result)
        # Must not tell the agent to go hunting for a bubble colour as if it broke.
        self.assertNotIn("green or blue bubble", result)


if __name__ == "__main__":
    unittest.main()
