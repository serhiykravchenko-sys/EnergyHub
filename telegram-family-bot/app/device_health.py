from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape
from statistics import median
from typing import Any


INVALID_STATES = {"", "unknown", "unavailable", "none", "null"}
CHECK_INTERVAL_SECONDS = 5 * 60
STATE_RETENTION_DAYS = 14
MAX_ACTIVE_REPORT_LINES = 15
MAX_RECOVERY_REPORT_LINES = 5


@dataclass(frozen=True)
class EnvironmentSensor:
    label: str
    temperature_entity: str
    humidity_entity: str
    group: str
    battery_entity: str = ""
    pressure_entity: str = ""

    @property
    def key(self) -> str:
        return self.temperature_entity.removeprefix("sensor.").removesuffix(
            "_temperature"
        )


def parse_environment_sensors(specification: str) -> tuple[EnvironmentSensor, ...]:
    sensors = []
    for raw_entry in str(specification or "").split(";"):
        entry = raw_entry.strip()
        if not entry:
            continue
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) not in {4, 5, 6}:
            raise ValueError(
                "Each environment sensor must use "
                "label|temperature_entity|humidity_entity|group"
                "[|battery_entity|pressure_entity]"
            )
        label, temperature, humidity, group = parts[:4]
        battery = parts[4] if len(parts) == 5 else ""
        if len(parts) == 6:
            battery = parts[4]
        pressure = parts[5] if len(parts) == 6 else ""
        if not label or not temperature or not humidity:
            raise ValueError("Environment sensor labels and entities cannot be empty")
        if group not in {"indoor", "basement"}:
            raise ValueError("Environment sensor group must be indoor or basement")
        sensors.append(
            EnvironmentSensor(
                label=label,
                temperature_entity=temperature,
                humidity_entity=humidity,
                group=group,
                battery_entity=battery,
                pressure_entity=pressure,
            )
        )
    return tuple(sensors)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _entity_number(entity: dict[str, Any] | None) -> float | None:
    if not entity:
        return None
    raw = str(entity.get("state") or "").strip().lower()
    return None if raw in INVALID_STATES else _number(raw)


def _age_hours(entity: dict[str, Any] | None, now: datetime) -> float | None:
    return _entity_age_hours(entity, now, "last_reported", "last_updated")


def _change_age_hours(
    entity: dict[str, Any] | None,
    now: datetime,
) -> float | None:
    return _entity_age_hours(entity, now, "last_changed", "last_updated")


def _entity_age_hours(
    entity: dict[str, Any] | None,
    now: datetime,
    *timestamp_fields: str,
) -> float | None:
    if not entity:
        return None
    updated = _timestamp(next(
        (entity.get(field) for field in timestamp_fields if entity.get(field)),
        None,
    ))
    if updated is None:
        return None
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=now.tzinfo)
    return max(0.0, (now - updated.astimezone(now.tzinfo)).total_seconds() / 3600)


def _previous_snapshot(state: dict[str, Any], now: datetime) -> dict[str, Any]:
    snapshots = state.setdefault("environment_hourly_snapshots", {})
    yesterday_hour = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H")
    return snapshots.get(yesterday_hour, {})


def _compact(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


class DeviceHealthMonitor:
    def __init__(self, config):
        self.sensors = tuple(getattr(config, "environment_sensors", ()))
        self.stale_hours = float(getattr(config, "environment_stale_hours", 24))
        self.temperature_deviation = float(
            getattr(config, "environment_temperature_deviation_c", 5)
        )
        self.humidity_deviation = float(
            getattr(config, "environment_humidity_deviation_percent", 20)
        )
        self.persistence_minutes = int(
            getattr(config, "environment_persistence_minutes", 60)
        )
        self.low_battery_percent = float(
            getattr(config, "device_low_battery_percent", 10)
        )

    def observe(self, client, state: dict[str, Any], now: datetime, *, force=False) -> bool:
        last_check = _timestamp(state.get("environment_last_check"))
        if (
            not force
            and last_check is not None
            and (now - last_check.astimezone(now.tzinfo)).total_seconds()
            < CHECK_INTERVAL_SECONDS
        ):
            return False

        all_states = {
            item.get("entity_id"): item
            for item in client.states()
            if item.get("entity_id")
        }
        readings = {}
        for sensor in self.sensors:
            temperature_state = all_states.get(sensor.temperature_entity)
            humidity_state = all_states.get(sensor.humidity_entity)
            readings[sensor.key] = {
                "label": sensor.label,
                "temperature": _entity_number(temperature_state),
                "humidity": _entity_number(humidity_state),
                "temperature_age_hours": _age_hours(temperature_state, now),
                "humidity_age_hours": _age_hours(humidity_state, now),
                "temperature_change_age_hours": _change_age_hours(
                    temperature_state,
                    now,
                ),
                "humidity_change_age_hours": _change_age_hours(
                    humidity_state,
                    now,
                ),
                "battery": _entity_number(all_states.get(sensor.battery_entity)),
                "battery_age_hours": _age_hours(
                    all_states.get(sensor.battery_entity),
                    now,
                ),
                "pressure": _entity_number(
                    all_states.get(sensor.pressure_entity)
                ),
                "group": sensor.group,
            }

        indoor = [
            reading
            for reading in readings.values()
            if reading["group"] == "indoor"
        ]
        indoor_temperatures = [
            reading["temperature"]
            for reading in indoor
            if reading["temperature"] is not None
            and reading["temperature_age_hours"] is not None
            and reading["temperature_age_hours"] < self.stale_hours
        ]
        indoor_humidities = [
            reading["humidity"]
            for reading in indoor
            if reading["humidity"] is not None
            and reading["humidity_age_hours"] is not None
            and reading["humidity_age_hours"] < self.stale_hours
        ]
        peer_temperature = (
            median(indoor_temperatures) if len(indoor_temperatures) >= 3 else None
        )
        peer_humidity = (
            median(indoor_humidities) if len(indoor_humidities) >= 3 else None
        )
        previous = _previous_snapshot(state, now)

        conditions = {}
        for sensor in self.sensors:
            reading = readings[sensor.key]
            ages = [
                reading["temperature_age_hours"],
                reading["humidity_age_hours"],
            ]
            if reading["temperature"] is None or reading["humidity"] is None:
                conditions[f"{sensor.key}:availability"] = {
                    "kind": "unavailable",
                    "label": sensor.label,
                    "immediate": True,
                }
                continue
            if any(age is None or age >= self.stale_hours for age in ages):
                known_ages = [age for age in ages if age is not None]
                conditions[f"{sensor.key}:availability"] = {
                    "kind": "stale",
                    "label": sensor.label,
                    "age_hours": max(known_ages) if known_ages else None,
                    "temperature": reading["temperature"],
                    "humidity": reading["humidity"],
                    "immediate": True,
                }
                continue
            change_ages = [
                reading["temperature_change_age_hours"],
                reading["humidity_change_age_hours"],
            ]
            if all(
                age is not None and age >= self.stale_hours
                for age in change_ages
            ):
                conditions[f"{sensor.key}:availability"] = {
                    "kind": "unchanged",
                    "label": sensor.label,
                    "age_hours": min(change_ages),
                    "temperature": reading["temperature"],
                    "humidity": reading["humidity"],
                    "immediate": True,
                }
                continue

            previous_reading = previous.get(sensor.key, {})
            comparisons = (
                (
                    "temperature",
                    reading["temperature"],
                    peer_temperature if sensor.group == "indoor" else None,
                    _number(previous_reading.get("temperature")),
                    self.temperature_deviation,
                ),
                (
                    "humidity",
                    reading["humidity"],
                    peer_humidity if sensor.group == "indoor" else None,
                    _number(previous_reading.get("humidity")),
                    self.humidity_deviation,
                ),
            )
            for metric, value, peer, yesterday, threshold in comparisons:
                peer_deviation = None if peer is None else value - peer
                yesterday_deviation = (
                    None if yesterday is None else value - yesterday
                )
                if not (
                    peer_deviation is not None
                    and abs(peer_deviation) >= threshold
                    or yesterday_deviation is not None
                    and abs(yesterday_deviation) >= threshold
                ):
                    continue
                conditions[f"{sensor.key}:{metric}"] = {
                    "kind": "outlier",
                    "label": sensor.label,
                    "metric": metric,
                    "value": value,
                    "peer": peer,
                    "yesterday": yesterday,
                    "peer_deviation": peer_deviation,
                    "yesterday_deviation": yesterday_deviation,
                    "immediate": False,
                }

            battery = reading["battery"]
            battery_age = reading["battery_age_hours"]
            if (
                sensor.battery_entity
                and battery is not None
                and battery <= self.low_battery_percent
                and battery_age is not None
                and battery_age < self.stale_hours
            ):
                conditions[f"{sensor.key}:battery"] = {
                    "kind": "low_battery",
                    "label": sensor.label,
                    "battery": battery,
                    "immediate": True,
                }

        self._reconcile(state, conditions, now)
        state["environment_last_check"] = now.isoformat()
        self._capture_hourly_snapshot(state, readings, now)
        self._clean(state, now)
        return True

    def _reconcile(self, state, conditions, now):
        candidates = state.setdefault("environment_candidates", {})
        active = state.setdefault("environment_active", {})
        recoveries = state.setdefault("environment_recoveries", [])
        changed = False

        for key, condition in conditions.items():
            candidate = candidates.get(key)
            if candidate is None:
                candidate = {"since": now.isoformat()}
                candidates[key] = candidate
                changed = True
            since = _timestamp(candidate.get("since")) or now
            duration_minutes = max(0, int((now - since.astimezone(now.tzinfo)).total_seconds() / 60))
            if condition["immediate"] or duration_minutes >= self.persistence_minutes:
                issue = dict(condition)
                issue["since"] = since.isoformat()
                issue["duration_minutes"] = duration_minutes
                if active.get(key) != issue:
                    active[key] = issue
                    changed = True

        for key in list(candidates):
            if key in conditions:
                continue
            candidates.pop(key, None)
            issue = active.pop(key, None)
            if issue:
                recoveries.append(
                    {
                        "label": issue.get("label", key),
                        "kind": issue.get("kind", "issue"),
                        "issue_key": key,
                        "metric": issue.get("metric"),
                        "recovered_at": now.isoformat(),
                    }
                )
            changed = True
        return changed

    def _capture_hourly_snapshot(self, state, readings, now):
        snapshots = state.setdefault("environment_hourly_snapshots", {})
        snapshots.setdefault(
            now.strftime("%Y-%m-%dT%H"),
            {
                key: {
                    "temperature": value["temperature"],
                    "humidity": value["humidity"],
                    "pressure": value["pressure"],
                }
                for key, value in readings.items()
                if value["temperature"] is not None
                and value["humidity"] is not None
            },
        )

    def _clean(self, state, now):
        cutoff = (now - timedelta(days=STATE_RETENTION_DAYS)).strftime(
            "%Y-%m-%dT%H"
        )
        snapshots = state.setdefault("environment_hourly_snapshots", {})
        for hour in list(snapshots):
            if hour < cutoff:
                snapshots.pop(hour, None)
        state["environment_recoveries"] = state.setdefault(
            "environment_recoveries", []
        )[-50:]


def environment_report_lines(state: dict[str, Any], now: datetime) -> list[str]:
    lines = []
    active_issues = list(state.get("environment_active", {}).values())
    active_issues.sort(
        key=lambda issue: (
            0
            if issue.get("kind") in {
                "unavailable",
                "stale",
                "unchanged",
                "low_battery",
            }
            else 1,
            str(issue.get("label") or ""),
        )
    )
    for issue in active_issues[:MAX_ACTIVE_REPORT_LINES]:
        label = escape(str(issue.get("label") or "Датчик"))
        kind = issue.get("kind")
        if kind == "unavailable":
            lines.append(f"⚠️ {label}: дані температури або вологості недоступні.")
        elif kind == "stale":
            age = issue.get("age_hours")
            age_text = "невідомо скільки" if age is None else f"{_compact(age)} год"
            lines.append(f"⚠️ {label}: дані не оновлювалися {age_text}.")
        elif kind == "unchanged":
            age = issue.get("age_hours")
            age_text = "невідомо скільки" if age is None else f"{_compact(age)} год"
            lines.append(
                f"⚠️ {label}: температура й вологість не змінювалися "
                f"{age_text}; можливий офлайн."
            )
        elif kind == "low_battery":
            lines.append(f"🔋 {label}: батарея {_compact(issue['battery'])}%.")
        elif kind == "outlier":
            metric = issue.get("metric")
            unit = "°C" if metric == "temperature" else "%"
            name = "температура" if metric == "temperature" else "вологість"
            comparisons = []
            if issue.get("peer") is not None:
                comparisons.append(f"медіана в будинку {_compact(issue['peer'])}{unit}")
            if issue.get("yesterday") is not None:
                comparisons.append(f"учора {_compact(issue['yesterday'])}{unit}")
            suffix = "; " + ", ".join(comparisons) if comparisons else ""
            lines.append(
                f"⚠️ {label}: {name} {_compact(issue['value'])}{unit}{suffix}; "
                f"відхилення триває {issue.get('duration_minutes', 0)} хв."
            )
    omitted = len(active_issues) - MAX_ACTIVE_REPORT_LINES
    if omitted > 0:
        lines.append(f"⚠️ Ще активних проблем із датчиками: {omitted}.")

    grouped_recoveries: dict[str, list[str]] = {}
    for recovery in state.get("environment_recoveries", []):
        label = str(recovery.get("label") or "Датчик")
        details = grouped_recoveries.pop(label, [])
        kind = recovery.get("kind")
        metric = recovery.get("metric")
        if kind in {"unavailable", "stale"}:
            detail = "зв’язок і свіжість даних"
        elif kind == "unchanged":
            detail = "зміни температури та вологості"
        elif kind == "low_battery":
            detail = "заряд вище порога"
        elif metric == "temperature":
            detail = "відхилення температури"
        elif metric == "humidity":
            detail = "відхилення вологості"
        else:
            detail = "попереднє відхилення"
        if detail not in details:
            details.append(detail)
        grouped_recoveries[label] = details

    for label, details in list(grouped_recoveries.items())[
        -MAX_RECOVERY_REPORT_LINES:
    ]:
        lines.append(
            f"✅ {escape(label)}: відновлено — {', '.join(details)}."
        )
    return lines


def doorbell_report_line(config, client, now: datetime) -> str | None:
    entity_id = str(getattr(config, "doorbell_battery_entity", "") or "").strip()
    if not entity_id:
        return None
    entity = client.state(entity_id)
    value = _entity_number(entity)
    age = _age_hours(entity, now)
    stale_hours = float(getattr(config, "environment_stale_hours", 24))
    if value is None:
        return "⚠️ Батарея дверного дзвінка: дані недоступні."
    if age is None or age >= stale_hours:
        return "⚠️ Батарея дверного дзвінка: дані застаріли."
    threshold = float(getattr(config, "device_low_battery_percent", 10))
    if value <= threshold:
        return f"🔋 Дверний дзвінок: батарея {_compact(value)}%."
    return None


def acknowledge_health_report(state: dict[str, Any]) -> None:
    state["environment_recoveries"] = []
