---
name: Remaining customer API approval
description: Approved development scope and requested payment provider for the remaining customer APIs.
---

The user asked to complete the remaining customer APIs and provide a document
listing endpoints, payloads, headers and responses. They approved the recommended
development rules: customer-owned vehicles without automatic historical linking,
private image uploads up to 5 MB, cancellation only while a booking is pending,
reviews held for moderation, and conversations restricted to the customer's
booking or job. They selected Razorpay as the payment gateway.

**Why:** The user explicitly selected “Use recommended rules” and entered
“razorpay” in the implementation clarification form.

The user subsequently chose “Keep Razorpay; complete other APIs”, explicitly
leaving payment checkout integration pending rather than switching providers.

**How to apply:** Preserve mobile-only OTP and no-password authentication.
Treat this as development implementation approval, not production rollout
approval. Do not silently substitute a different payment provider or claim
live payment processing before its app connection is configured and verified.
Keep the pending checkout status visible in the reference document; financial
reads from trusted sources are not a claim that Razorpay processing is live.
