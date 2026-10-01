from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.home_assistant import HomeAssistantClient


class FakeResponse:
    def __init__(self, content=b"[]"):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.content


class HomeAssistantTests(unittest.TestCase):
    @patch(
        "app.home_assistant.urlopen",
        return_value=FakeResponse(b"2026-09-20 08:00:00 WARNING (MainThread) [test] warning"),
    )
    def test_error_log_uses_authenticated_core_endpoint(self, urlopen):
        client = HomeAssistantClient(
            base_url="http://supervisor/core/api",
            token="secret",
        )

        self.assertIn("WARNING", client.error_log())
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://supervisor/core/api/error_log",
        )
        self.assertEqual(request.headers["Authorization"], "Bearer secret")

    @patch("app.home_assistant.urlopen", return_value=FakeResponse())
    def test_publish_mqtt_uses_supervisor_api_and_retained_json(self, urlopen):
        client = HomeAssistantClient(
            base_url="http://supervisor/core/api",
            token="secret",
        )
        client.publish_mqtt(
            "energyhub/input/weather/uhmc",
            {"source_status": "fresh", "warnings": [{"summary": "ожеледиця"}]},
        )
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://supervisor/core/api/services/mqtt/publish",
        )
        self.assertEqual(request.headers["Authorization"], "Bearer secret")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["topic"], "energyhub/input/weather/uhmc")
        self.assertTrue(body["retain"])
        self.assertEqual(json.loads(body["payload"])["source_status"], "fresh")

    @patch("app.home_assistant.urlopen", return_value=FakeResponse(b"log"))
    def test_core_and_supervisor_logs_use_supervisor_endpoints(self, urlopen):
        client = HomeAssistantClient(token="secret", supervisor_url="http://supervisor")
        self.assertEqual("log", client.core_log())
        self.assertEqual("log", client.supervisor_log())
        self.assertEqual(
            ["http://supervisor/core/logs", "http://supervisor/supervisor/logs"],
            [call.args[0].full_url for call in urlopen.call_args_list],
        )


if __name__ == "__main__":
    unittest.main()
