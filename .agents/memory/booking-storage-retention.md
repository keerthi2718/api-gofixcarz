---
name: Booking storage across code restores
description: Preserve earlier production booking storage independently of the currently selected runtime workflow.
---

Keep storage backward-compatible with previously published booking workflows,
including both slotted and slotless records.

**Why:** Restoring older source removed scheduling storage definitions and tightened slot nullability while production retained a slotless booking. Development had no booking-link rows, so the tightening appeared safe locally but failed Publish validation against production data.

**How to apply:** Inspect actual production structure and null counts read-only before tightening constraints or removing fields. Preserve historical storage rather than fabricating a slot or backfill to satisfy an older model. Apply compatible definitions through normal development migrations and let Publish synchronize managed production.

Preserving storage is not the same as restoring behavior.

**Why:** The restored runtime can still assume slots exist even after the schema correctly allows older records.

**How to apply:** Call out runtime compatibility separately; do not silently reintroduce an earlier booking workflow as part of a schema-only publishing repair.

New customer bookings must accept a selected date directly, with no frontend
`slot_id` or `quote_id` requirement. The user explicitly asked to remove both.

**Why:** The customer app should not select time slots or manage quote identifiers
to submit a booking. Removing those inputs does not authorize destruction of
historical booking snapshots or slot records.

**How to apply:** Keep legacy reads and acceptance/expiry guards compatible.
Internal immutable price snapshots may retain their historical storage links;
do not expose those links as a prerequisite for the frontend.
