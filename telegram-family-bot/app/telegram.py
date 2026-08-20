from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, timeout: int = 20):
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.timeout = timeout

    def send_message(self, chat_id: str, message: str) -> int:
        body = urlencode({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        request = Request(f"{self.base_url}/sendMessage", data=body, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise TelegramError(f"Telegram returned HTTP {exc.code}") from None
        except URLError as exc:
            raise TelegramError(f"Telegram connection failed: {exc.reason}") from None
        if not result.get("ok"):
            raise TelegramError(result.get("description", "Telegram rejected the message"))
        return int(result["result"]["message_id"])
