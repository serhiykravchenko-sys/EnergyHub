# Release 3.6.37 evidence and limits

## Public-copy checks — October 28

All 1,342 public-scope tests passed: 367 EH, 760 Family and 215 HA. The scope
difference from private 1,347 is the five excluded private-maintenance tests,
not removal of controller/ownership assertions. Three native-control assertions
from the private cleanup module are retained separately. An initial missing
dashboard resource example was corrected and the complete HA suite rerun.

The prepared 414-file tree passes Python 3.11 AST/compile (267 files), YAML
parsing (12), JSON parsing (6), SVG parsing (8), local links (93 Markdown files),
reviewed identifier/credential-pattern checks and whitespace checks. Public
Python provenance matches the reviewed alias/test-scope transformations.
Eleven PNGs match reviewed source exactly; seven SVGs match after newline
normalization. The evidence diagram alone has a status-neutral acceptance footer
and a rerendered, visually checked PNG. Pattern checks are heuristic, not
exhaustive security assurance.

## Source and supplied live evidence

Private 3.6.37 source passed 367 EH, 760 Family and 220 HA tests. Private Threat
Monitor and BMS-tool tests are separate and not EnergyHub public scope. Public
copy suites passed after the reviewed alias/default/documentation changes.
Five private registry-cleanup/deployment-tool tests are excluded; three native
configuration/control assertions are retained verbatim in a public test module.

Owner-supplied October 28 startup logs show both apps at 3.6.37, MQTT discovery,
PV1/PV2, online health and reconstruction without startup inverter writes.
Family notification transport is active; a five-minute solar window is ready
and today's primary schedule accepted. An unconfirmed backup/tomorrow schedule
is not acceptance of either. Source/rollback hashes were verified privately.

On October 28, 2026, the owner reported several days of normal observation and
accepted public source promotion. The owner described the latest changes as
dashboard/chart cosmetics and audited log cleanup. The exact observation interval
and individual natural-event/report cases were not independently measured or
revalidated in this promotion task. This supersedes the earlier pending owner
monitoring-acceptance gate, not installation-specific negative-case limits.

No continuous remote HA monitoring is claimed. Repository tests use fixtures;
they do not prove physical switching, every failure case or cross-home
compatibility. The owner subsequently authorized tag `v3.6.37` and its GitHub
Release as the final 3.x publication. Documentation-only release finalization
does not change the tested runtime, HA examples or reviewed device mappings.

Public transforms use generic example device aliases consistently in source,
HA examples and tests. Optional monitoring lists are empty; optional Xiaomi
cloud observation, household monitoring and isolated Tuya reload are disabled
in the public manifest. Installed upgrades may retain earlier options; review
them explicitly. No private registry/session cache or Threat Monitor is included.

Read-only PV2, BMS evidence, numeric validity, controller persistence, ownership
and log/message coverage have independent limits. Unknown evidence must not
be converted into successful recovery or zero consumption. Cold-weather and
installation-specific negative-case tests remain necessary.
