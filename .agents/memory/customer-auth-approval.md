---
name: Customer auth approval
description: User-approved first-phase scope and the boundary on customer identity linking.
---

The user approved mobile-only OTP registration/login, no passwords, 5-minute OTP
expiry, 30-second resend cooldown, five verification attempts, 15-minute access
tokens and 30-day rotating refresh sessions.

**Why:** These choices were explicitly submitted in the customer API approval
form. The broader customer PDF's remaining product decisions were not approved
by that submission.

**How to apply:** Preserve these approved rules unless the user changes them.
Do not infer approval of email/password login, automatic linking to pre-existing
garage contacts/vehicles, payment or booking policy, or production migration.
First-phase work is authentication, sessions and profile; the PDF's complete
inventory must not be described as implemented merely because this phase works.
