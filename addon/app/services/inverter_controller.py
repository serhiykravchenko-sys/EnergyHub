import json
import time
from datetime import datetime

from app.utils.json_store import atomic_write_json
from app.utils.logger import log


MENU_01_COMMANDS = {
    "SUB": "POP01",
    "SBU": "POP02",
}

MENU_01_QPIRI_VALUES = {
    "SUB": "Solar Utility Battery",
    "SBU": "Solar Battery Utility",
}

MENU_16_COMMANDS = {
    "SNU": "PCP01",
    "OSO": "PCP02",
    "CSO": "PCP03",
}

WRITE_ATTEMPTS = 3
WRITE_RETRY_DELAY_SECONDS = 1

MENU_01_VERIFY_ATTEMPTS = 3
MENU_01_VERIFY_DELAY_SECONDS = 1

MODE_SETTLE_DELAY_SECONDS = 2

STATE_SCHEMA_VERSION = 2
DEFAULT_STATE_PATH = "/data/inverter_controller_state.json"

VALID_CONFIRMED_MODES = {
    "unknown",
    "solar",
    "hybrid_charging",
    "hybrid_grid_hold",
    "panic",
    "panic_grid_hold",
}

VALID_MENU_16_PRIORITIES = {
    "unknown",
    "SNU",
    "OSO",
    "CSO",
}


class InverterController:
    def __init__(self, inverter, state_path=DEFAULT_STATE_PATH):
        self.inverter = inverter
        self.state_path = state_path

        # Runtime mode is deliberately unknown until Menu 01 is read from
        # the inverter and reconciled with the persisted Menu 16/context.
        self.mode = "unknown"
        self.confirmed_mode = "unknown"
        self.known_charger_priority = "unknown"
        self.panic_target_soc = None
        self.hybrid_target_soc = None
        self.ahm_debt_date = None
        self.ahm_debt_target_soc = None
        self.last_error = None

        self._load_state()

    def mqtt_values(self):
        return {
            "operating_mode": self.mode,
            "operating_mode_reason": self._mode_reason(),
        }

    def _mode_reason(self):
        reasons = {
            "unknown": (
                "Current inverter strategy is not confirmed"
            ),
            "inconsistent": (
                self.last_error
                or "Inverter settings do not match persisted strategy context"
            ),
            "transitioning": (
                "Inverter settings are being changed"
            ),
            "solar": (
                "Solar strategy: Menu 01=SBU, Menu 16=OSO"
            ),
            "hybrid_charging": (
                "Night grid charging: "
                "Menu 01=SUB, Menu 16=SNU"
            ),
            "hybrid_grid_hold": (
                "Battery charged; house remains on night grid: "
                "Menu 01=SUB, Menu 16=OSO"
            ),
            "panic": (
                "Emergency grid charging: "
                "Menu 01=SUB, Menu 16=SNU"
            ),
            "panic_grid_hold": (
                "Emergency reserve is held on available grid: "
                "Menu 01=SUB, Menu 16=OSO"
            ),
            "transition_failed": (
                self.last_error
                or "Inverter transition failed"
            ),
        }

        return reasons.get(
            self.mode,
            "Unknown operating mode",
        )

    def _load_state(self):
        if not self.state_path:
            return

        try:
            with open(self.state_path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError:
            log("No persisted inverter controller state found")
            return
        except Exception as exc:
            log(
                "ERROR: Failed to load inverter controller state: "
                f"{exc}"
            )
            return

        stored_schema_version = data.get("schema_version", 1)
        if stored_schema_version not in {1, STATE_SCHEMA_VERSION}:
            log(
                "Ignore unsupported inverter controller state schema: "
                f"{data.get('schema_version')}"
            )
            return

        confirmed_mode = data.get("confirmed_mode", "unknown")
        if confirmed_mode not in VALID_CONFIRMED_MODES:
            confirmed_mode = "unknown"

        charger_priority = data.get(
            "known_charger_priority",
            "unknown",
        )
        if charger_priority not in VALID_MENU_16_PRIORITIES:
            charger_priority = "unknown"

        panic_target_soc = data.get("panic_target_soc")
        if panic_target_soc is not None:
            try:
                panic_target_soc = round(float(panic_target_soc), 2)
            except (TypeError, ValueError):
                panic_target_soc = None

            if not 1 <= panic_target_soc <= 100:
                panic_target_soc = None

        hybrid_target_soc = data.get("hybrid_target_soc")
        if hybrid_target_soc is not None:
            try:
                hybrid_target_soc = float(hybrid_target_soc)
            except (TypeError, ValueError):
                hybrid_target_soc = None

            if not 1 <= hybrid_target_soc <= 100:
                hybrid_target_soc = None

        ahm_debt_date = data.get("ahm_debt_date")
        if not isinstance(ahm_debt_date, str):
            ahm_debt_date = None

        ahm_debt_target_soc = data.get("ahm_debt_target_soc")
        if ahm_debt_target_soc is not None:
            try:
                ahm_debt_target_soc = float(ahm_debt_target_soc)
            except (TypeError, ValueError):
                ahm_debt_target_soc = None

            if not 1 <= ahm_debt_target_soc <= 100:
                ahm_debt_target_soc = None

        self.confirmed_mode = confirmed_mode
        self.known_charger_priority = charger_priority
        self.panic_target_soc = panic_target_soc
        self.hybrid_target_soc = hybrid_target_soc
        self.ahm_debt_date = ahm_debt_date
        self.ahm_debt_target_soc = ahm_debt_target_soc

        log(
            "Inverter controller state loaded: "
            f"mode={self.confirmed_mode}, "
            f"Menu 16={self.known_charger_priority}, "
            f"panic_target={self.panic_target_soc}, "
            f"hybrid_target={self.hybrid_target_soc}, "
            f"ahm_debt={self.ahm_debt_target_soc} "
            f"for {self.ahm_debt_date}"
        )

    def _persist_state(self):
        if not self.state_path:
            return True

        payload = {
            "schema_version": STATE_SCHEMA_VERSION,
            "confirmed_mode": self.confirmed_mode,
            "known_charger_priority": self.known_charger_priority,
            "panic_target_soc": self.panic_target_soc,
            "hybrid_target_soc": self.hybrid_target_soc,
            "ahm_debt_date": self.ahm_debt_date,
            "ahm_debt_target_soc": self.ahm_debt_target_soc,
            "updated_at": datetime.now().astimezone().isoformat(),
        }

        try:
            atomic_write_json(
                self.state_path,
                payload,
                indent=2,
                sort_keys=True,
            )
            return True

        except Exception as exc:
            log(
                "ERROR: Failed to persist inverter controller state: "
                f"{exc}"
            )
            return False

    def _confirm_mode(self, mode):
        self.mode = mode
        self.confirmed_mode = mode
        self.last_error = None

        if mode not in {"panic", "panic_grid_hold"}:
            self.panic_target_soc = None

        self._persist_state()

    def set_panic_target_soc(self, target_soc):
        try:
            target_soc = round(float(target_soc), 2)
        except (TypeError, ValueError):
            log(f"Ignore invalid Panic target SOC: {target_soc}")
            return False

        if not 1 <= target_soc <= 100:
            log(f"Ignore invalid Panic target SOC: {target_soc}")
            return False

        self.panic_target_soc = target_soc
        self._persist_state()
        return True

    def set_hybrid_target_soc(self, target_soc):
        try:
            target_soc = float(target_soc)
        except (TypeError, ValueError):
            log(f"Ignore invalid Hybrid target SOC: {target_soc}")
            return False

        if not 1 <= target_soc <= 100:
            log(f"Ignore invalid Hybrid target SOC: {target_soc}")
            return False

        self.hybrid_target_soc = round(target_soc, 2)
        self._persist_state()
        return True

    def clear_panic_target_soc(self):
        self.panic_target_soc = None
        self._persist_state()

    def set_ahm_debt(self, debt_date, target_soc=None):
        if target_soc is not None:
            try:
                target_soc = float(target_soc)
            except (TypeError, ValueError):
                return False

            if not 1 <= target_soc <= 100:
                return False

            target_soc = round(target_soc, 2)

        self.ahm_debt_date = str(debt_date)
        self.ahm_debt_target_soc = target_soc
        self._persist_state()
        return True

    def reconstruct_mode(self, actual_menu_01):
        """Reconstruct the strategy without writing to the inverter.

        Menu 01 is read from QPIRI. Menu 16 cannot be read on this inverter,
        so the last successfully ACK-confirmed value is loaded from persisted
        state. SUB+SNU still needs persisted strategy context to distinguish
        Hybrid Charging from Panic.
        """

        remembered_menu_16 = self.known_charger_priority
        previous_context = self.confirmed_mode

        reconstructed_mode = None

        if actual_menu_01 == "SBU" and remembered_menu_16 == "OSO":
            reconstructed_mode = "solar"

        elif actual_menu_01 == "SUB" and remembered_menu_16 == "OSO":
            # SUB+OSO is a valid Grid Hold state only when persisted context
            # shows that EnergyHub was already holding the grid or was in the
            # process of moving from Hybrid Charging to Grid Hold. The same
            # physical combination with Solar/Panic context can be a partial
            # interrupted transition and must not be guessed.
            if previous_context in {
                "hybrid_charging",
                "hybrid_grid_hold",
            }:
                reconstructed_mode = "hybrid_grid_hold"

            elif (
                previous_context in {"panic", "panic_grid_hold"}
                and self.panic_target_soc is not None
            ):
                reconstructed_mode = "panic_grid_hold"

        elif actual_menu_01 == "SUB" and remembered_menu_16 == "SNU":
            # A persisted Panic target is written before entering Panic, so it
            # also allows recovery from a crash after the hardware transition
            # completed but before the final mode confirmation was persisted.
            if self.panic_target_soc is not None:
                reconstructed_mode = "panic"

            elif previous_context == "hybrid_charging":
                reconstructed_mode = "hybrid_charging"

        if reconstructed_mode is None:
            self.mode = "inconsistent"
            self.last_error = (
                "Startup reconstruction is incomplete: "
                f"Menu 01={actual_menu_01}, "
                f"remembered Menu 16={remembered_menu_16}, "
                f"persisted mode={previous_context}, "
                f"panic target={self.panic_target_soc}"
            )

            log(self.last_error)
            return False

        # A physical, confidently reconstructed combination becomes the new
        # confirmed context. This also completes an interrupted persistence
        # update after a successful hardware command.
        self._confirm_mode(reconstructed_mode)

        log(
            "Startup strategy reconstructed: "
            f"mode={self.mode}, "
            f"Menu 01={actual_menu_01}, "
            f"Menu 16={remembered_menu_16}, "
            f"panic target={self.panic_target_soc}"
        )
        return True

    def _settle(self):
        log(
            "Waiting for inverter to settle: "
            f"{MODE_SETTLE_DELAY_SECONDS} sec"
        )

        time.sleep(MODE_SETTLE_DELAY_SECONDS)

    def _write_menu_01(self, command, priority):
        for attempt in range(1, WRITE_ATTEMPTS + 1):
            if attempt > 1:
                time.sleep(WRITE_RETRY_DELAY_SECONDS)

            try:
                acknowledged = (
                    self.inverter
                    .set_output_source_priority(command)
                )
            except Exception as exc:
                log(
                    "Menu 01 write failed: "
                    f"attempt={attempt}/{WRITE_ATTEMPTS}, "
                    f"value={priority}, "
                    f"command={command}, "
                    f"error={exc}"
                )
                continue

            if acknowledged:
                log(
                    "Menu 01 command accepted: "
                    f"{priority} on attempt {attempt}"
                )
                return True

            log(
                "Menu 01 command not acknowledged: "
                f"attempt={attempt}/{WRITE_ATTEMPTS}, "
                f"value={priority}, "
                f"command={command}"
            )

        self.last_error = (
            f"Menu 01 command {command} was not acknowledged "
            f"after {WRITE_ATTEMPTS} attempts"
        )
        log(self.last_error)
        return False

    def _write_menu_16(self, command, priority):
        for attempt in range(1, WRITE_ATTEMPTS + 1):
            if attempt > 1:
                time.sleep(WRITE_RETRY_DELAY_SECONDS)

            try:
                acknowledged = (
                    self.inverter
                    .set_charger_source_priority(command)
                )
            except Exception as exc:
                log(
                    "Menu 16 write failed: "
                    f"attempt={attempt}/{WRITE_ATTEMPTS}, "
                    f"value={priority}, "
                    f"command={command}, "
                    f"error={exc}"
                )
                continue

            if acknowledged:
                self.known_charger_priority = priority
                self.last_error = None

                # Menu 16 cannot be queried on this inverter. Persist the last
                # successfully ACK-confirmed value immediately, even before a
                # multi-command strategy transition is fully complete.
                self._persist_state()

                log(
                    "Menu 16 command accepted: "
                    f"{priority} on attempt {attempt}"
                )
                return True

            log(
                "Menu 16 command not acknowledged: "
                f"attempt={attempt}/{WRITE_ATTEMPTS}, "
                f"value={priority}, "
                f"command={command}"
            )

        self.last_error = (
            f"Menu 16 command {command} was not acknowledged "
            f"after {WRITE_ATTEMPTS} attempts"
        )
        log(self.last_error)
        return False

    def set_output_priority(self, priority):
        command = MENU_01_COMMANDS.get(priority)

        if command is None:
            self.last_error = (
                f"Unsupported Menu 01 value: {priority}"
            )
            log(self.last_error)
            return False

        log(
            f"Setting Menu 01: {priority} using {command}"
        )

        if not self._write_menu_01(command, priority):
            return False

        expected_raw = MENU_01_QPIRI_VALUES[priority]
        last_actual = None
        last_exception = None

        for attempt in range(
            1,
            MENU_01_VERIFY_ATTEMPTS + 1,
        ):
            if attempt > 1:
                time.sleep(
                    MENU_01_VERIFY_DELAY_SECONDS
                )

            try:
                settings = self.inverter.read_settings()

                last_actual = settings.get(
                    "output_source_priority"
                )

                last_exception = None

            except Exception as exc:
                last_exception = exc

                log(
                    "Menu 01 verification read failed: "
                    f"attempt={attempt}/"
                    f"{MENU_01_VERIFY_ATTEMPTS}, "
                    f"error={exc}"
                )

                continue

            if last_actual == expected_raw:
                self.last_error = None

                log(
                    f"Menu 01 verified: {priority} "
                    f"on attempt {attempt}"
                )

                return True

            log(
                "Menu 01 verification mismatch: "
                f"attempt={attempt}/"
                f"{MENU_01_VERIFY_ATTEMPTS}, "
                f"expected={priority}, "
                f"raw={last_actual}"
            )

        if last_exception is not None:
            self.last_error = (
                "Menu 01 verification failed for "
                f"{priority}: {last_exception}"
            )
        else:
            self.last_error = (
                "Menu 01 verification failed: "
                f"expected={priority}, "
                f"raw={last_actual}"
            )

        log(self.last_error)
        return False

    def set_charger_priority(self, priority):
        command = MENU_16_COMMANDS.get(priority)

        if command is None:
            self.last_error = (
                f"Unsupported Menu 16 value: {priority}"
            )
            log(self.last_error)
            return False

        log(
            f"Setting Menu 16: {priority} using {command}"
        )

        return self._write_menu_16(
            command,
            priority,
        )

    def enter_hybrid(self):
        self.mode = "transitioning"

        log(
            "Starting transition to Hybrid: "
            "Menu 01=SUB, Menu 16=SNU"
        )

        if not self.set_output_priority("SUB"):
            self.mode = "transition_failed"
            return False

        if not self.set_charger_priority("SNU"):
            log(
                "Hybrid transition partially failed. "
                "Attempting Solar recovery."
            )

            recovered = self.restore_solar()

            if not recovered:
                self.mode = "transition_failed"

            return False

        self._confirm_mode("hybrid_charging")

        log(
            "Hybrid Charging active: "
            "Menu 01=SUB, Menu 16=SNU"
        )

        self._settle()
        return True

    def enter_hybrid_grid_hold(
        self,
        confirmed_mode="hybrid_grid_hold",
        strategy_name="Hybrid Grid Hold",
    ):
        self.mode = "transitioning"

        log(
            f"Starting {strategy_name}: "
            "Menu 01=SUB, Menu 16=OSO"
        )

        if not self.set_output_priority("SUB"):
            hold_error = (
                self.last_error
                or "Menu 01 could not be confirmed as SUB"
            )

            log(
                f"{strategy_name} transition failed: "
                f"{hold_error}. Attempting Solar recovery."
            )

            recovered = self.restore_solar()

            if recovered:
                log(
                    f"{strategy_name} was not activated. "
                    "Solar recovery succeeded."
                )
            else:
                recovery_error = (
                    self.last_error
                    or "Solar recovery did not complete"
                )

                self.mode = "transition_failed"
                self.last_error = (
                    f"{strategy_name} failed: "
                    f"{hold_error}; Solar recovery failed: "
                    f"{recovery_error}"
                )
                log(self.last_error)

            return False

        if not self.set_charger_priority("OSO"):
            hold_error = (
                self.last_error
                or "Menu 16 OSO command was not acknowledged"
            )

            log(
                f"{strategy_name} transition partially failed: "
                f"{hold_error}. Attempting Solar recovery."
            )

            recovered = self.restore_solar()

            if recovered:
                log(
                    f"{strategy_name} was not activated. "
                    "Solar recovery succeeded."
                )
            else:
                recovery_error = (
                    self.last_error
                    or "Solar recovery did not complete"
                )

                self.mode = "transition_failed"
                self.last_error = (
                    f"{strategy_name} failed: "
                    f"{hold_error}; Solar recovery failed: "
                    f"{recovery_error}"
                )
                log(self.last_error)

            return False

        self._confirm_mode(confirmed_mode)

        log(
            f"{strategy_name} active: "
            "Menu 01=SUB, Menu 16=OSO"
        )

        self._settle()
        return True

    def enter_panic_grid_hold(self):
        if self.panic_target_soc is None:
            self.set_panic_target_soc(95)

        return self.enter_hybrid_grid_hold(
            confirmed_mode="panic_grid_hold",
            strategy_name="Panic Grid Hold",
        )

    def enter_panic(self):
        self.mode = "transitioning"

        if self.panic_target_soc is None:
            self.set_panic_target_soc(95)

        log(
            "Starting transition to Panic: "
            "Menu 01=SUB, Menu 16=SNU"
        )

        if not self.set_output_priority("SUB"):
            self.mode = "transition_failed"
            return False

        if not self.set_charger_priority("SNU"):
            log(
                "Panic transition partially failed. "
                "Attempting Solar recovery."
            )

            recovered = self.restore_solar()

            if not recovered:
                self.mode = "transition_failed"

            return False

        self._confirm_mode("panic")

        log(
            "Panic active: "
            "Menu 01=SUB, Menu 16=SNU"
        )

        self._settle()
        return True

    def restore_solar(self):
        self.mode = "transitioning"

        log(
            "Starting transition to Solar: "
            "Menu 01=SBU, Menu 16=OSO"
        )

        menu_16_ok = self.set_charger_priority("OSO")
        menu_16_error = None if menu_16_ok else self.last_error

        menu_01_ok = self.set_output_priority("SBU")
        menu_01_error = None if menu_01_ok else self.last_error

        if menu_16_ok and menu_01_ok:
            self._confirm_mode("solar")

            log(
                "Solar active: "
                "Menu 01=SBU, Menu 16=OSO"
            )

            self._settle()
            return True

        errors = []

        if menu_16_error:
            errors.append(f"Menu 16: {menu_16_error}")

        if menu_01_error:
            errors.append(f"Menu 01: {menu_01_error}")

        self.mode = "transition_failed"
        self.last_error = (
            "Solar recovery incomplete: "
            + (
                "; ".join(errors)
                if errors
                else (
                    f"menu_01_ok={menu_01_ok}, "
                    f"menu_16_ok={menu_16_ok}"
                )
            )
        )

        log(self.last_error)
        return False
