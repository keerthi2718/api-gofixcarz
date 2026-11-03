---
name: Customer appointment policy
description: Customer bookings need not select slots; owner acceptance and scheduled confirmation are separate.
---

Customers must be able to quote and book selected garage services without an
appointment slot. Do not fabricate slots, quote IDs, or prices.

Slotless bookings remain PENDING until the garage assigns a real appointment
time. The garage can accept the request first, then assign or update the
schedule. This separates the owner's agreement from the confirmed appointment.
Existing selected-slot bookings retain their established behavior.

**Why:** The user explicitly required optional slots, acceptance before schedule
assignment, and PENDING status until a time is assigned.

**How to apply:** Customer and garage-owner integrations must not require a slot
or treat an unscheduled owner acceptance as a confirmed appointment. Preserve
null scheduling fields until the garage assigns the actual time.
