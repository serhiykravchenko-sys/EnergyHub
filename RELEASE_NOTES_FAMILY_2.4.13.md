# Telegram Family Assistant 2.4.13 — private candidate

Prepared in the local repository on 2026-09-26. The app source was
synchronized to the Home Assistant local-app directory on 2026-09-26. The
homeowner subsequently reported the 2.4.13 startup banner and 08:00
scheduler initialization. Notification and next-morning behavior remain
under monitoring, not fully live-validated. No commit, push, or public release.

- Household messages consistently name ДТЕК. They distinguish confirmed
  below-reserve charging from ДТЕК, confirmed solar-only battery charging
  during Grid Hold, and the reserve-plus-10 return to solar priority. They
  describe inverter strategy, not an unmeasured instantaneous power mix.
- The 08:00 recap preserves the recorded reason for a confirmed reserve
  increase/decrease and the confirmed hold/release sequence. Actual generation
  versus forecast is shown as signed percentage difference only when the
  completed day is confirmed not to have reached 100% SOC and all values exist.
- A new official UHMC alert during the day includes level, warning-section
  date/conditions and stated impacts with a source link. An active warning at
  08:00 is a brief level/hazard/source line; overnight duplicate delivery and
  stale warning claims remain guarded.
- Core warnings/errors use the existing Home Assistant Core API error log.
  The previous `/supervisor/core/logs` and `/supervisor/supervisor/logs`
  requests returned HTTP 403 with this app's privileges. The candidate does
  not request the broad Supervisor-manager role. Supervisor is explicitly
  unmonitored. The Core log is current-session evidence filtered to at most
  24 hours, not proof that the entire preceding 24 hours are clean.

No control action is initiated by Family Assistant. The Xiaomi Miot
`result is undefined` warning is outside this app and remains a separate
third-party integration investigation. Live checks should cover one natural
reserve/hold/release sequence, an actual UHMC post, the next 08:00 report,
and Core log access without repeated HTTP 403 warnings.
