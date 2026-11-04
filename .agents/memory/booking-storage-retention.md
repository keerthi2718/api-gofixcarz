---
name: Booking storage across code restores
description: Preserve earlier production booking storage independently of the currently selected runtime workflow.
---

Keep storage backward-compatible with previously published booking workflows even when current application requests create only slotted bookings.

**Why:** Restoring older source removed scheduling storage definitions and tightened slot nullability while production retained a slotless booking. Development had no booking-link rows, so the tightening appeared safe locally but failed Publish validation against production data.

**How to apply:** Inspect actual production structure and null counts read-only before tightening constraints or removing fields. Preserve historical storage rather than fabricating a slot or backfill to satisfy an older model. Apply compatible definitions through normal development migrations and let Publish synchronize managed production.

Preserving storage is not the same as restoring behavior.

**Why:** The restored runtime can still assume slots exist even after the schema correctly allows older records.

**How to apply:** Call out runtime compatibility separately; do not silently reintroduce an earlier booking workflow as part of a schema-only publishing repair.
