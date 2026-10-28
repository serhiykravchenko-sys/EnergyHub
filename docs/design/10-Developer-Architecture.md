# Developer architecture

Read [component responsibilities](05-System-Architecture.md),
[reserve](BATTERY_RESERVE_CURRENT.md), [charging](DECISION_ENGINE.md),
[native protection](PEAK_LOAD_CONTROL.md) and [HP1](SMART_HEATING_2.4.md).

The EH main loop constructs services and consumes bounded requests. The inverter
controller is the command boundary: durable transition uncertainty is recorded
before writes; Menu 01 uses QPIRI readback, Menu 16 has ACK only. Save failures
block further writes in-process. An unfinished persisted transition requires
attended verification rather than pretending startup reconstructed a safe mode.

`WeatherBufferDryRun`, `PanicDecisionEngine` and `PeakLoadGuardController` retain
historical names. Their current behavior is reserve recommendation, continuous
inverter support and HP1-only acknowledged climate management respectively.
They do not authorize retired multi-plug dispatch. Do not remove compatibility
identifiers merely because their names look obsolete.

Native HA overload/battery controllers keep their own saved original states and
coordinate recovery through shared helpers. Their command requests do not have
the same acknowledgement semantics as the HP1 executor. Restart and manual
intervention must be tested per path, not inferred from another controller.

Tests use disposable persistence, fake hardware/HA and mocked transports.
Run the suites inside `addon/`, `telegram-family-bot/` and `homeassistant/`:
`python -m unittest discover -s tests -q`. Public tests exclude private registry
cleanup/deployment-tool tests, retaining native-control assertions separately.
Required test dependencies include PyYAML and Jinja2 plus Family requirements.
Do not import app entry points against a live installation to run unit tests.
