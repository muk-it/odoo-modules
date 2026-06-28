`1.0.39`
--------

- Refactor to an owned-action architecture: each schedule now provisions
  its own ``ir.actions.server`` (state ``ai_agent``) plus a dedicated
  ``ir.cron``, one cron per schedule.
- Drop the central ``Fire Due Schedules`` cron, the per-schedule Postgres
  advisory lock, and the savepoint-based dispatch loop.
- Delegate session dispatch, per-record fan-out, chaining, and chatter
  mirroring to the new ``muk_ai_automation`` dependency.
- Extend ``muk_ai``'s pending-session crons to wake due ``schedule``
  sessions instead of running a dedicated resume worker.

`1.0.0`
-------

- Initial Release
