from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class HomeAssistantError(RuntimeError):
    pass


class HomeAssistantClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: int = 20,
                 supervisor_url: str | None = None):
        self.base_url = (base_url or os.environ.get("HA_API_URL") or "http://supervisor/core/api").rstrip("/")
        self.supervisor_url = (supervisor_url or os.environ.get("SUPERVISOR_API_URL")
                               or "http://supervisor").rstrip("/")
        self.token = token if token is not None else os.environ.get("SUPERVISOR_TOKEN", "")
        self.timeout = timeout

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST" if payload is not None else "GET",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                content = response.read().decode("utf-8")
                return json.loads(content) if content.strip() else None
        except HTTPError as exc:
            try:
                details = exc.read().decode("utf-8", errors="replace").strip()
            except OSError:
                details = ""
            suffix = f": {details[:500]}" if details else ""
            raise HomeAssistantError(f"Home Assistant returned HTTP {exc.code} for {path}{suffix}") from None
        except URLError as exc:
            raise HomeAssistantError(f"Home Assistant connection failed: {exc.reason}") from None

    def _request_text(self, path: str) -> str:
        return self._request_text_url(f"{self.base_url}{path}")

    def _request_text_url(self, url: str) -> str:
        request = Request(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raise HomeAssistantError(
                f"Home Assistant returned HTTP {exc.code} for {url}"
            ) from None
        except URLError as exc:
            raise HomeAssistantError(
                f"Home Assistant connection failed: {exc.reason}"
            ) from None

    def error_log(self) -> str:
        """Return the read-only Home Assistant Core error log."""
        return self._request_text("/error_log")

    def core_log(self) -> str:
        """Return Home Assistant Core logs through the Supervisor API."""
        return self._request_text_url(f"{self.supervisor_url}/core/logs")

    def supervisor_log(self) -> str:
        """Return Supervisor logs through the Supervisor API."""
        return self._request_text_url(f"{self.supervisor_url}/supervisor/logs")

    def states(self) -> list[dict[str, Any]]:
        return list(self._request("/states"))

    def state(self, entity_id: str) -> dict[str, Any] | None:
        if not entity_id:
            return None
        try:
            return dict(self._request(f"/states/{quote(entity_id, safe='')}"))
        except HomeAssistantError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise

    def forecast(self, entity_id: str, forecast_type: str = "hourly") -> list[dict[str, Any]]:
        result = self._request(
            "/services/weather/get_forecasts?return_response",
            {"entity_id": entity_id, "type": forecast_type},
        )
        service_response = result.get("service_response", result)
        entity_result = service_response.get(entity_id, {})
        return list(entity_result.get("forecast", []))

    def hourly_forecast(self, entity_id: str) -> list[dict[str, Any]]:
        return self.forecast(entity_id, "hourly")

    def publish_mqtt(
        self,
        topic: str,
        payload: dict[str, Any],
        retain: bool = True,
    ) -> None:
        self._request(
            "/services/mqtt/publish",
            {
                "topic": topic,
                "payload": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                "retain": retain,
            },
        )
