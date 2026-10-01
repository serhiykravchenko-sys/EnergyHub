# Telegram Family Assistant 2.4.14 — private corrective candidate

Prepared as a repository candidate. The homeowner subsequently supplied a
2.4.14 startup banner on 2026-09-27 and reported about 24 hours of normal
operation, including the morning message. Exact source/deployed hashes and
the corrective failure cases are not verified here.

- Drop obsolete reserve-relative notifications under load-controller schema 5,
  including messages queued before restart. The current controller owns fixed
  outage-battery warnings and confirmed action messages.
- Announce first-floor Quiet status with a short Ukrainian message.
