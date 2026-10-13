---
name: Platform admin boundary
description: Scope and provisioning expectations for platform administrators.
---

The admin role is for a platform-wide dashboard spanning users, garages, jobs, bookings, analytics, billing issues, and audit history. Garage-owner APIs remain scoped to the owner's garage.

**Why:** The user asked for an admin role with access to the platform-wide API list, not for ordinary garage accounts to see every tenant.

**How to apply:** Keep admin authorization distinct from garage ownership, use the current account role for permission decisions, and do not auto-promote signups or silently grant administrative power to an existing account. Ask the user which account should be promoted before provisioning anyone.

Do not expose the admin sign-in URL in shared API lists or handoffs, and handle
passwords through the secure secret flow rather than chat. Keep dedicated
administrator provisioning separate from garage-owner registration.

**Why:** The user explicitly requested a separate admin account store, secure
credential handling, and no exposed admin sign-in URL. Requiring an owner signup
would unnecessarily require a garage and trigger SMS.

**How to apply:** Omit private admin authentication from shared documentation;
keep credentials out of chat, files, and logs. This privacy requirement does not
replace JWT validation and server-side authorization. The current requested
account provisioning must not be treated as permission to mutate production.

Treat admin signup as operator-controlled initial credential provisioning, not
open public platform registration.

**Why:** The user requested a signup API because they need initial admin
credentials for production testing. An unrestricted signup would let arbitrary
visitors gain platform-wide access.

**How to apply:** Preserve deliberate operator authorization and the separation
from garage-owner signup. Building or publishing this API does not authorize
creating an account on the user's behalf or exposing credentials in handoffs.

Admin sign-in currently allows password-only sessions by default; authenticator
MFA is opt-in at the platform policy level.

**Why:** The user explicitly chose to make admin MFA optional so they can proceed
without entering an authenticator code.

**How to apply:** Keep `ADMIN_MFA_REQUIRED` defaulted to false unless the user
changes this policy. Never weaken password verification, rate limits, JWT
validation, or authorization as part of bypassing TOTP.
