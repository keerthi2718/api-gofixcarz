---
name: Customer auth approval
description: User-approved first-phase scope and the boundary on customer identity linking.
---

The user approved mobile-only OTP registration/login, no passwords, 5-minute OTP
expiry, 30-second resend cooldown, five verification attempts, 15-minute access
tokens and 30-day rotating refresh sessions.

**Why:** These choices were explicitly submitted in the customer API approval
form. A later approval expanded the development scope; see
customer-remaining-api-approval.md for the approved remaining rules and gateway.

**How to apply:** Preserve these approved rules unless the user changes them.
Do not infer approval of email/password login, automatic linking to pre-existing
garage contacts/vehicles, or production migration. Apply the later approved
development rules separately. The PDF's complete inventory must not be described
as implemented merely because authentication, sessions and profile work.
