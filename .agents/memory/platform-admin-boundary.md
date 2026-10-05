---
name: Platform admin boundary
description: Scope and provisioning expectations for platform administrators.
---

The admin role is for a platform-wide dashboard spanning users, garages, jobs, bookings, analytics, billing issues, and audit history. Garage-owner APIs remain scoped to the owner's garage.

**Why:** The user asked for an admin role with access to the platform-wide API list, not for ordinary garage accounts to see every tenant.

**How to apply:** Keep admin authorization distinct from garage ownership, use the current account role for permission decisions, and do not auto-promote signups or silently grant administrative power to an existing account. Ask the user which account should be promoted before provisioning anyone.
