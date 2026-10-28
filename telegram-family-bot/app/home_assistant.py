from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.parse import urlsplit, urlunsplit
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
        try:
            return self._request_text("/error_log")
        except HomeAssistantError as exc:
            if 'HTTP 404' not in str(exc):
                raise
            return json.dumps(self.system_log_entries())

    def system_log_entries(self) -> list[dict[str, Any]]:
        """Read HA's bounded warning/error buffer without Supervisor privileges."""
        result = self.websocket_read('system_log/list')
        if not isinstance(result, list):
            raise HomeAssistantError('HA system_log/list unavailable')
        return [row for row in result[:200] if isinstance(row, dict)]

    def websocket_read(self, command, *, parameters=None):
        if command not in {'system_log/list', 'config/entity_registry/list',
                           'config/device_registry/list', 'recorder/statistics_during_period'}:
            raise HomeAssistantError('Unsupported read-only HA command')
        if command == 'recorder/statistics_during_period':
            params = parameters or {}
            ids = params.get('statistic_ids')
            if (set(params) != {'start_time','end_time','statistic_ids','period','types','units'}
                    or params.get('period') != 'day' or params.get('types') != ['change']
                    or params.get('units') != {'energy':'kWh'}
                    or not isinstance(ids,list) or not 1 <= len(ids) <= 3
                    or any(not isinstance(e,str) or not e.startswith('sensor.') for e in ids)):
                raise HomeAssistantError('Unsupported daily energy statistics request')
            from datetime import datetime
            try:
                start = datetime.fromisoformat(params['start_time'])
                end = datetime.fromisoformat(params['end_time'])
                if start.tzinfo is None or end.tzinfo is None or not 23*3600 <= (end-start).total_seconds() <= 25*3600:
                    raise ValueError('Invalid day bounds')
            except (KeyError,ValueError,TypeError):
                raise HomeAssistantError('Invalid daily statistics interval') from None
        elif parameters:
            raise HomeAssistantError('Parameters are not supported for this read command')
        import websocket
        parsed = urlsplit(self.base_url)
        path = '/core/websocket' if parsed.path.rstrip('/') == '/core/api' else '/api/websocket'
        url = urlunsplit(('wss' if parsed.scheme == 'https' else 'ws', parsed.netloc, path, '', ''))
        connection = None
        def frame():
            result = json.loads(connection.recv())
            if not isinstance(result, dict):
                raise ValueError('Invalid response frame')
            return result
        try:
            connection = websocket.create_connection(url, timeout=self.timeout)
            if frame().get('type') != 'auth_required':
                raise HomeAssistantError('Unexpected HA WebSocket greeting')
            connection.send(json.dumps({'type': 'auth', 'access_token': self.token}))
            if frame().get('type') != 'auth_ok':
                raise HomeAssistantError('HA WebSocket authentication rejected')
            connection.send(json.dumps({'id': 1, 'type': command, **(parameters or {})}))
            result = frame()
            expected = dict if command == 'recorder/statistics_during_period' else list
            if result.get('id') != 1 or not result.get('success') or not isinstance(result.get('result'), expected):
                raise HomeAssistantError('HA read-only result unavailable')
            return result['result']
        except (OSError, ValueError, websocket.WebSocketException) as exc:
            # Do not include frames or credentials in diagnostic exception text.
            raise HomeAssistantError('HA system log connection failed') from None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except (OSError, websocket.WebSocketException):
                    pass

    def registry(self):
        return dict(entities=self.websocket_read('config/entity_registry/list'),
                    devices=self.websocket_read('config/device_registry/list'))

    def daily_energy_statistics(self, start, end, entities):
        """Same recorder daily change statistics used by the HP dashboard."""
        return self.websocket_read('recorder/statistics_during_period', parameters={
            'start_time':start.isoformat(), 'end_time':end.isoformat(),
            'statistic_ids':list(entities), 'period':'day', 'types':['change'],
            'units':{'energy':'kWh'}})

    def config_entries(self):
        result = self._request('/config/config_entries/entry?domain=tuya')
        if not isinstance(result, list):
            raise HomeAssistantError('HA config entry health unavailable')
        return result

    def reload_beacon_entry(self, entry_id):
        self._request('/services/homeassistant/reload_config_entry', {'entry_id': entry_id})

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

    def import_history(self, start, end, entities):
        """Read a bounded session interval; no writes or statistics backfill."""
        from urllib.parse import urlencode
        if not 0 <= (end-start).total_seconds() <= 48*3600:
            return None
        query = urlencode({'end_time': end.isoformat(),
                           'filter_entity_id': ','.join(entities)})
        result = self._request('/history/period/' + quote(start.isoformat(), safe='') + '?' + query)
        if not isinstance(result, list) or sum(len(rows) for rows in result if isinstance(rows, list)) > 20000:
            return None
        return result

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
