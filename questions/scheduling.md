# Scheduling questions

- **OverTime after a schedule change.** When a booking moves, is cancelled or is assigned to another tester, should its planned OverTime be recomputed in place or superseded by a new record preserving the previous plan? (blocks US-HD04, US-HD12)
- **Calibration expires during a run.** If a run is already in progress when calibration validity ends, does it finish or pause for the Head of Department's assessment? New bookings are blocked, but the handling of a running measurement has not been decided. (blocks US-AD09, US-HD04)

- **Cancelling an attempt in a running shared run.** When one sample test is cancelled after its shared run starts, how is that attempt stopped or recorded while the other attempts continue? Cancelling it must not cancel the other sample tests or release their required reservations. (blocks US-HD09)

## Related documents

- [Testing work and scheduling](../docs/functional/laboratory_module/overview.md#testing-work-and-scheduling)
- [Head of department](../docs/functional/laboratory_module/features/head-of-department.md)
