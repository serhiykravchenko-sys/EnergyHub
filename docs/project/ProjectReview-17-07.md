# EnergyHub 1.0 Project Review — Resolution Report

Original review date: 2026-07-17.

Resolution status updated: 2026-07-19.

## Executive result

The review found no single critical issue, but it identified a set of High-priority correctness and state-truth problems. All functional High-priority items selected for 1.0 were corrected. The most useful Medium items were also completed. Broad refactoring and release engineering remain intentionally separate.

## Finding resolution

| ID | Finding | Resolution |
|---|---|---|
| F-01 | Panic used stale forecast | Fixed: live Today/Tomorrow forecast topics and separate decision inputs |
| F-02 | System Health ignored Communication Health | Fixed |
| F-03 | restart recovery used clock time | Fixed: physical Menu 01 + persisted Menu 16/context reconstruction |
| F-04 | failed Grid Hold could leave unsafe partial state | Fixed: one bounded Solar recovery attempt |
| F-05 | safe Solar request could be overwritten | Fixed: lock-protected priority queue semantics |
| F-06 | Daily Summary updated non-atomically | Fixed: one atomic JSON snapshot |
| F-07 | remembered and real mode not reconciled | Fixed through startup reconstruction |
| F-08 | Away Mode active in 1.0 | Fixed: runtime implementation removed |
| F-09 | SOC anomalies may affect accounting | Deferred to 1.1 general telemetry robustness |
| F-10 | stable load caused false freshness warning | Fixed: unchanged load is informational only |
| F-11 | activation notification preceded success | Fixed: events published after transition result |
| F-12 | Daily Summary missed final daily Grid Import minutes | Fixed and midnight-validated |
| C-01 | `main.py` lifecycle complexity | Deferred until tests exist |
| C-02 | duplicated policy constants | Deferred to configurable 1.2 |
| C-03 | Menu 16 not independently verified | Accepted hardware limitation; terminology corrected |
| C-04 | persistence not atomic | Fixed with shared atomic writer |
| C-05 | no automated tests | Open release blocker |
| C-06 | dependencies unpinned | Open release blocker |
| C-07 | weak default MQTT credentials | Open release blocker |
| E-01 | confusing Grid Import `_2` entity | Fixed by stable IDs and HA registry rename |
| E-02 | stale retained topic risk | Current Discovery IDs and the HA registry were inspected; no stale entity evidence was found, so no broad deletion was performed |
| E-03 | shared availability hid diagnostics | Fixed with separate process/telemetry availability |
| D-01 | Away documentation contradicted runtime | Fixed in current documentation |
| D-02 | roadmap missed 1.4 and 1.5 | Fixed |
| D-03 | stale repository structure | Fixed |
| D-04 | restart wording overstated truth | Fixed: Menu 16 described as ACK-confirmed |
| D-05 | documentation duplication and contradictions | Reduced through full audit |
| D-06 | external operations documentation incomplete | Partly improved; full install guide remains release work |

## Validation evidence

### Restart

Observed:

```text
Inverter controller state loaded: mode=solar, Menu 16=OSO
Inverter settings updated: Menu 01=SBU, Menu 16=OSO
Startup strategy reconstructed: mode=solar
Startup reconstruction accepted without inverter writes
```

### Telemetry freshness

Observed:

```text
Telemetry Freshness: fresh
Telemetry Freshness Reason: ok
```

### Persistence

Observed:

- expected JSON files present;
- no temporary files left behind;
- raw snapshot changed about once per minute;
- Grid Import file remained unchanged in Solar.

### 23:50

Dashboard changed from `NOT EVALUATED` to a valid Solar night plan.

### Midnight

Observed:

```text
Grid import day completed
Grid import queued Daily Summary finalization
Daily summary Grid Import already finalized
Grid import day finalization handled
```

The unchanged result demonstrated idempotence.

## Medium decisions

Implemented:

- freshness correction;
- transition-confirmed notifications;
- visible manual Panic rejection;
- atomic/throttled persistence;
- combined validation.

Deferred:

- daytime SUB estimator refinement;
- broad `main.py` refactor;
- constant centralization;
- internal 07:00 fallback;
- dependency pinning until exact tested versions are captured.

## Dashboard outcome

The original mixed dashboard was redesigned into:

- three consistent charts;
- Modes & Controls;
- Status;
- Decision Logic;
- three floor comfort sections.

A family logic infographic and a technical architecture infographic were added.

## Remaining release risks

1. No executable automated tests.
2. Unpinned dependencies.
3. Weak example/default MQTT credentials.
4. Incomplete fresh-install and upgrade guide.
5. Daytime Panic Grid Import accuracy not externally measured.
6. HA dependency for 07:00 restoration.
7. General SOC anomaly quarantine not implemented.

## Conclusion

The audit achieved its main goal: EnergyHub now has coherent state truth, safer transitions, restart reconstruction, accurate notification timing, durable persistence, stable entities, and documentation aligned with current code.

The project should now move to release preparation rather than another broad functional redesign.
