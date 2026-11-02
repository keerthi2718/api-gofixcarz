---
name: Admin draft approval boundary
description: Conservative development defaults are approved; production policy and missing data-source boundaries remain separate.
---

The user initially selected “Existing-data APIs first (recommended)”, then
approved “Choose conservative development rules (recommended)” and asked to
work on all admin APIs. Choose and document conservative configurable
development policies rather than repeatedly requesting policy decisions.
This does not approve production changes.

**Why:** The user explicitly expanded the development scope. The supplied document calls its contracts proposed, and
missing payment, review, customer identity and transition sources cannot be
replaced by convenient existing contact or billing records.

**How to apply:** Preserve legacy money meanings. Never label stored job final amounts as captured
payments, garage contact records as customer accounts, or creation timestamps
as booking decision history. Document chosen lifecycle, MFA/scope, snapshot,
delay and privacy defaults. Require separate production rollout approval.
Missing providers or source integrations must remain explicit, not successful
placeholder responses.

The user later explicitly directed that all garage accounts be VERIFIED,
including existing records, and that future registrations default to VERIFIED.
This applies to development data; it does not authorize a production data
change. Admins may still make deliberate, audited verification changes.

**Why:** This is a subsequent explicit change to the prior conservative
verification default, not blanket approval of proposed admin policies or a
production rollout.

**How to apply:** Keep VERIFIED as the creation default and align development
records; do not update production records or publish without separate approval.
