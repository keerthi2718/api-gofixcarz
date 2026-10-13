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
