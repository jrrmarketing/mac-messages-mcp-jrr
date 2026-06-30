"""
Tests for delivery routing and verification helpers.
"""

import unittest
from unittest.mock import patch

from mac_messages_mcp.delivery import (
    choose_delivery_route,
    finalize_send_result,
    format_delivery_plan,
    get_delivery_plan,
    verify_outbound_delivery,
)


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


if __name__ == "__main__":
    unittest.main()
