import math
import time

from app.adapters.powmr import (
    ModbusCrcError,
    ModbusExceptionResponseError,
    ModbusInvalidValueError,
    ModbusMalformedResponseError,
    ModbusTimeoutError,
    ModbusUnsupportedError,
)


TOTAL_PV_MAX_ALIGNMENT_SECONDS = 15
MINIMUM_STALE_AFTER_SECONDS = 60
PV1_STALE_AFTER_SECONDS = 60


class PV2TelemetryService:
    def __init__(self, enabled, poll_interval, clock=None):
        self.enabled = bool(enabled)
        self.poll_interval = max(10, int(poll_interval))
        self.stale_after = max(
            MINIMUM_STALE_AFTER_SECONDS,
            self.poll_interval * 2 + 10,
        )
        self.clock = clock or time.monotonic

        self.last_attempt_time = None
        self.next_attempt_time = None
        self.last_valid_time = None
        self.last_voltage = None
        self.last_power = None
        self.last_total_power = None
        self.total_sample_time = None
        self.total_pv1_sample_time = None
        self.consecutive_failures = 0

        self.status = (
            "awaiting_sample" if self.enabled else "disabled"
        )
        self.freshness = "stale"

    def due(self, now=None):
        if not self.enabled:
            return False

        now = self.clock() if now is None else now

        return self.next_attempt_time is None or now >= self.next_attempt_time

    def poll(self, inverter, pv1_power, pv1_sample_time):
        if not self.enabled:
            return False

        self.last_attempt_time = self.clock()

        try:
            values = inverter.read_pv2_telemetry()
            sample_time = self.clock()

            self.last_voltage = values["pv2_input_voltage"]
            self.last_power = values["pv2_charging_power"]
            self.last_valid_time = sample_time
            self.status = "fresh"
            self.freshness = "fresh"
            self.consecutive_failures = 0
            self.next_attempt_time = sample_time + self.poll_interval

            self.last_total_power = None
            self.total_sample_time = None
            self.total_pv1_sample_time = None

            try:
                pv1_power_value = float(pv1_power)
            except (TypeError, ValueError):
                pv1_power_value = None

            if (
                pv1_power_value is not None
                and math.isfinite(pv1_power_value)
                and 0 <= pv1_power_value <= 12000
                and pv1_sample_time is not None
                and abs(sample_time - pv1_sample_time)
                <= TOTAL_PV_MAX_ALIGNMENT_SECONDS
            ):
                self.last_total_power = round(
                    pv1_power_value + self.last_power,
                    1,
                )
                self.total_sample_time = sample_time
                self.total_pv1_sample_time = pv1_sample_time

            return True

        except ModbusTimeoutError:
            self._failure("timeout")
        except ModbusCrcError:
            self._failure("crc_error")
        except ModbusMalformedResponseError:
            self._failure("malformed_response")
        except ModbusInvalidValueError:
            self._failure("invalid_value")
        except ModbusUnsupportedError:
            self._failure("unsupported")
        except ModbusExceptionResponseError:
            self._failure("modbus_exception")
        except Exception:
            self._failure("error")

        return False

    def _failure(self, status):
        self.status = status
        self.freshness = "stale"
        self.consecutive_failures += 1

        if status == "unsupported":
            # Unsupported firmware will not become compatible during the
            # current process lifetime. Avoid repeatedly delaying PI30MAX.
            self.next_attempt_time = float("inf")
            return

        retry_delay = max(
            self.poll_interval,
            min(300, 60 * (2 ** (self.consecutive_failures - 1))),
        )
        self.next_attempt_time = self.clock() + retry_delay

    def refresh(self, now=None):
        if not self.enabled:
            self.status = "disabled"
            self.freshness = "stale"
            return

        now = self.clock() if now is None else now

        if self.last_valid_time is None:
            return

        if (
            now - self.last_valid_time >= self.stale_after
            and self.freshness == "fresh"
        ):
            self.status = "stale"
            self.freshness = "stale"

    def pv2_is_fresh(self, now=None):
        self.refresh(now)
        return self.freshness == "fresh"

    def total_is_fresh(self, now=None):
        now = self.clock() if now is None else now

        return (
            self.pv2_is_fresh(now)
            and self.last_total_power is not None
            and self.total_sample_time is not None
            and self.total_pv1_sample_time is not None
            and now - self.total_sample_time < self.stale_after
            and now - self.total_pv1_sample_time
            < PV1_STALE_AFTER_SECONDS
        )

    def mqtt_values(self, now=None):
        now = self.clock() if now is None else now
        self.refresh(now)

        if self.last_valid_time is None:
            sample_age = "unknown"
        else:
            sample_age = max(0, int(now - self.last_valid_time))

        return {
            "pv2_telemetry_status": self.status,
            "pv2_telemetry_freshness": self.freshness,
            "pv2_sample_age_seconds": sample_age,
        }
