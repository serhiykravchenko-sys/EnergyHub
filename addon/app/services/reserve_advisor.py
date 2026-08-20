import json
from datetime import date, timedelta
from pathlib import Path

from app.utils.logger import log


RESERVE_ADVISOR_FILE = Path("/data/reserve_advisor.json")


class ReserveAdvisorService:
    """Recommend one AHM reserve step from completed morning evidence."""

    REQUIRED_DAYS = 3
    INCREASE_MARGIN_SOC = 5.0
    DECREASE_MARGIN_SOC = 20.0
    RETENTION_DAYS = 30
    NAMED_LEVELS = (20, 30, 40, 50)

    def __init__(self, path=None):
        self.path = Path(path) if path else RESERVE_ADVISOR_FILE
        self.observations = {}
        self.current = self._learning(0, None)
        self.load()

    def load(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.observations = dict(data.get("observations", {}))
            self.current = dict(data.get("current", self.current))
            log(
                "AHM reserve advisor loaded: "
                f"{len(self.observations)} completed mornings"
            )
        except (OSError, ValueError, TypeError) as exc:
            log(f"Failed to load AHM reserve advisor: {exc}")
            self.observations = {}
            self.current = self._learning(0, None)

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "observations": self.observations,
                        "current": self.current,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError as exc:
            log(f"Failed to save AHM reserve advisor: {exc}")

    def observe(self, payload):
        try:
            date_key = str(payload["date"])
            observed_date = date.fromisoformat(date_key)
            minimum_soc = float(payload["minimum_soc"])
            selected_soc = float(payload["selected_soc"])
        except (KeyError, TypeError, ValueError):
            return {
                "accepted": False,
                "reason": "invalid advisor observation",
            }

        if not 0 <= minimum_soc <= 100 or not 20 <= selected_soc <= 50:
            return {
                "accepted": False,
                "reason": "advisor observation outside SOC range",
            }

        self.observations[date_key] = {
            "date": date_key,
            "minimum_soc": round(minimum_soc, 1),
            "selected_soc": round(selected_soc, 1),
            "margin_soc": round(minimum_soc - selected_soc, 1),
        }
        self._prune(observed_date)
        self.current = self.evaluate(selected_soc)
        self.save()
        return {
            "accepted": True,
            "advisor": self.current,
        }

    def evaluate(self, selected_soc):
        selected_soc = round(float(selected_soc), 1)
        comparable = [
            observation
            for _, observation in sorted(
                self.observations.items(),
                reverse=True,
            )
            if float(observation["selected_soc"]) == selected_soc
        ][: self.REQUIRED_DAYS]

        count = len(comparable)
        if count < self.REQUIRED_DAYS:
            return self._learning(count, selected_soc)

        margins = [float(item["margin_soc"]) for item in comparable]
        low_days = sum(
            margin <= self.INCREASE_MARGIN_SOC for margin in margins
        )

        if low_days >= 2 and selected_soc < 50:
            suggested = self._next_level(selected_soc)
            action = "increase"
            reason = (
                f"{low_days}/3 completed mornings came within "
                f"{self.INCREASE_MARGIN_SOC:.0f} SOC points of the "
                f"selected {selected_soc:.0f}% reserve"
            )
        elif (
            all(
                margin >= self.DECREASE_MARGIN_SOC
                for margin in margins
            )
            and selected_soc > 20
        ):
            suggested = self._previous_level(selected_soc)
            action = "decrease"
            reason = (
                "3/3 completed mornings stayed at least "
                f"{self.DECREASE_MARGIN_SOC:.0f} SOC points above the "
                f"selected {selected_soc:.0f}% reserve"
            )
        else:
            suggested = selected_soc
            action = "keep"
            reason = (
                "three completed mornings do not justify a safer or "
                "more economical reserve step"
            )

        return {
            "status": action,
            "current_soc": selected_soc,
            "suggested_soc": suggested,
            "sample_count": count,
            "reason": reason,
            "margins_soc": margins,
        }

    def mqtt_values(self):
        return {
            "ahm_reserve_advice": self.current.get("status", "learning"),
            "ahm_reserve_advice_current_soc": self.current.get(
                "current_soc"
            ),
            "ahm_reserve_advice_suggested_soc": self.current.get(
                "suggested_soc"
            ),
            "ahm_reserve_advice_sample_count": self.current.get(
                "sample_count", 0
            ),
            "ahm_reserve_advice_reason": self.current.get("reason"),
        }

    def _learning(self, count, selected_soc):
        return {
            "status": "learning",
            "current_soc": selected_soc,
            "suggested_soc": selected_soc,
            "sample_count": count,
            "reason": (
                f"learning {count}/{self.REQUIRED_DAYS} completed mornings "
                "at the current reserve"
            ),
            "margins_soc": [],
        }

    def _next_level(self, selected_soc):
        for level in self.NAMED_LEVELS:
            if level > selected_soc:
                return level
        return 50

    def _previous_level(self, selected_soc):
        for level in reversed(self.NAMED_LEVELS):
            if level < selected_soc:
                return level
        return 20

    def _prune(self, today):
        cutoff = (today - timedelta(days=self.RETENTION_DAYS)).isoformat()
        self.observations = {
            date_key: observation
            for date_key, observation in self.observations.items()
            if date_key >= cutoff
        }
