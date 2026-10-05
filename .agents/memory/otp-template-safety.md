---
name: OTP template safety
description: Constraints for diagnosing and changing MSG91 OTP messages.
---

Do not change SMS branding speculatively; use the exact provider-approved template supplied by the user.

**Why:** The user confirmed OTPs previously worked with the existing setup and, on 2026-10-05, confirmed receipt of a direct test SMS after restoring the requested legacy SMS endpoint and Skill Wallet message. That confirms this sender/template combination delivered in the test, not that the published sign-in journey was verified. Indian SMS template matching can reject modified message text, so a branding change is not a safe speculative fix.

**How to apply:** On 2026-10-05, the user explicitly requested switching back to the legacy SMS endpoint and Skill Wallet template instead of GoFixAuto SendOTP. Do not reverse that choice speculatively. MSG91 OTP template IDs and numeric DLT template IDs are different identifiers and cannot be substituted into the same API parameter. Preserve the application's generated OTP and local verification. MSG91 request IDs confirm submission acceptance only, not handset delivery; describe these outcomes separately.

MSG91 has a dedicated OTP → Webhook → On Report Received setup for SendOTP.
Its official report guide documents the same flat requestId, status 1/2, and
custom-header support as SMS Webhook (New). Match the report product to the
current sending API: SMS for legacy sendhttp, OTP for SendOTP. Missing callbacks must
not be treated as proof of carrier failure.

**Why:** A pending diagnostic can also mean the webhook is not configured or
cannot reach the server, so it cannot identify the SMS failure by itself.

**How to apply:** Verify the appropriate report webhook configuration and inspect an actual
request-ID-matched provider report before claiming a delivery root cause.

Use one identical MSG91 auth key for direct testing and the published login sender.

**Why:** The user explicitly required using only the same key in both environments.

**How to apply:** Store it through Secrets, never in code or memory. Verify the production secret setup separately; secret existence alone does not prove equal values or that a running deployment loaded the latest value.