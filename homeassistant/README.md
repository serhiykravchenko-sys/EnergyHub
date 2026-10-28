# Home Assistant integration examples

These YAML, dashboard and helper-storage files are a **reference**, not a drop-in
complete home. Generic device aliases must be mapped consistently across helpers,
automations, tests, dashboards and optional Family settings. Initialization guards
and historical IDs are dependencies, not proof they should be deleted.

Native HA owns overload and outage plug execution, while EH retains HP1 policy
and inverter charging. See [architecture](../docs/design/05-System-Architecture.md)
and [protection](../docs/design/PEAK_LOAD_CONTROL.md). Native saved-ON intention
does not track every later manual OFF as cancellation. Messages state commands
sent, not physical confirmation. The HP1 command path has separate ACK/context
requirements; its relay is metering-only for the retired power-cycle path.

Merge the required configuration and packages after backup. Review all appliance
roles, thresholds, schedules and initialization before enabling actions. The
included network integration can expose connection information and perform
administrator-only supported endpoint changes; it is not a generic authorized
device repair service. Optional dashboard cards must be installed separately.
Do not add real registry files, secrets or cloud session caches to this tree.

App-only updates do not require Core stop/start. YAML changes require check and
appropriate reload/restart. Stop Core before editing `.storage`. Validate the
selected mappings and physical actions locally; repository tests use fixtures.

Five private registry-cleanup/deployment-tool tests are outside this public
scope. Their three native configuration/control assertions are retained in
`tests/test_native_initialization_public.py`; no runtime assertion is relaxed.
See [installation](../docs/operations/INSTALLATION.md) and
[validation](../docs/validation/RELEASE_3.6.37.md).
