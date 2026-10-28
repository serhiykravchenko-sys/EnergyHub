# EnergyHub and Family Assistant 3.6.37 — final 3.x release

This release closes the 3.x development line. Startup/source synchronization are
verified on the reference installation. The owner reports several days of normal
observation and authorized final publication on October 28, 2026. Repository
validation passed 1,342 public-scope tests. This is not exhaustive hardware
certification; see the evidence boundary below. New development moves to 4.x.

The 3.x snapshot includes native HA plug overload/outage preservation, separate
EH first-floor climate management, reserve/night/outage charging, sensor/BMS
evidence and expanded messages/diagnostics. Current illustrated and technical
guides explain the monolithic product without implying the future Core split.

Final corrections qualify solar timestamps after HA reads finish, retain
event-time observations across delayed delivery, bound obsolete-notification
cleanup, remove retired multi-plug bridge health assumptions, distinguish log
observation from notification acknowledgement, enforce expiry, bound recurring
failure logs and isolate fresh/corrupt state defaults. Compatibility names are
retained deliberately. No new HA configuration changes belong to the final
3.6.37 corrective delta itself.

Native switch requests are not physical ACKs. Original saved ON intention is not
a universal later-manual-OFF cancellation. Fridge food/compressor commissioning,
rare failure paths and extended heating observations remain installation-specific.
No blanket hardware retry, exactly-once messaging or exhaustive bug-free claim.

See [validation](docs/validation/RELEASE_3.6.37.md),
[installation](docs/operations/INSTALLATION.md), and [diagrams](docs/Images/README.md).
