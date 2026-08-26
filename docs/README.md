# EnergyHub Documentation Map

The local Git repository is the durable source of truth for EnergyHub. Topic-specific Codex tasks may be kept separate, but verified facts, accepted decisions, implementation status, and remaining work must be recorded here before relying on them in another task.

## Documentation areas

- [`project/`](project/) — manifesto, public project definition, principles, and positioning.
- [`roadmap/`](roadmap/) — the public roadmap and version development plans.
- [`design/`](design/) — system architecture, decision engine, house model, and decision log.
- [`features/`](features/) — active and proposed feature specifications.
- [`operations/`](operations/) — installation, Home Assistant configuration, deployment, and recovery.
- [`incidents/`](incidents/) — observed failures, evidence, recovery, and follow-up actions.
- [`validation/`](validation/) — test plans, device validation, and supervised field results.
- [`hardware/`](hardware/) — hardware-specific setup and verified behavior.
- [`Images/`](Images/) — diagrams and infographics referenced by the documentation.

## Cross-task workflow

1. Start a focused task for one feature, incident, or operational topic.
2. In the private development repository, read the private project-state record and the relevant topic document before making changes.
3. Keep hypotheses separate from verified observations.
4. Record accepted decisions in [`design/09-Decision-Log.md`](design/09-Decision-Log.md).
5. Update the relevant feature, incident, validation, or operations document as work progresses.
6. Update the private project state, public roadmap, changelog, and release notes only when their status actually changes.

Household-specific project state, incident diaries, and detailed backlog items
are private development records and are deliberately not linked from the
public documentation map.

Chat history is useful working context, but it is not the project record. A new task should be able to continue safely from the repository alone.

## Product positioning

See [`project/POSITIONING.md`](project/POSITIONING.md) for the current public message, target users, evidence requirements, claim boundaries, and future positioning direction.
