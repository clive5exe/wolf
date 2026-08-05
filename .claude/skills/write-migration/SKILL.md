---
name: write-migration
description: Add a numbered SQLite migration preserving append-only guarantees and replayability.
---

# Writing a storage migration

1. Migrations are numbered SQL files in `src/tradeos/storage/sql/`:
   `NNNN_short_name.sql`, applied in order by `storage/migrations.py`,
   recorded in the `migrations` ledger table.
2. Hard rules:
   - NEVER alter or drop the `events` table's existing columns or its
     append-only triggers. Additive only (new tables, new indexes, new
     nullable columns on non-event tables).
   - Event payload shape changes are NOT migrations. Bump the payload's
     `schema_version` and add an upcaster in `events/upcast.py` so old
     events still replay.
   - Derived-state tables may be dropped/rebuilt freely (they must be
     reconstructible from events. That's the test).
3. Every migration ships with: an idempotence guard (IF NOT EXISTS forms),
   a test in `tests/unit/test_migrations.py` applying from-empty and
   from-previous, and a replay test proving pre-migration event logs still
   reduce to identical derived state.
4. Update `storage/backup.py` retention notes if new tables need backup.
