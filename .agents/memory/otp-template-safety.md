---
name: OTP template safety
description: Constraints for diagnosing and changing MSG91 OTP messages.
---

Do not replace the legacy SMS branding just because it differs from the app name without first confirming the approved DLT template.

**Why:** The user confirmed OTPs previously worked with the existing setup. Indian SMS template matching can reject modified message text, so a branding change is not a safe speculative fix.

**How to apply:** Check the provider's delivery report and approved sender/template before changing SMS content. MSG91 request IDs confirm submission acceptance only, not handset delivery; describe these outcomes separately.

MSG91's Webhook (New) delivery-report documentation says pending messages do
not trigger callbacks; only final operator reports do. Missing callbacks must
not be treated as proof of carrier failure.

**Why:** A pending diagnostic can also mean the webhook is not configured or
cannot reach the server, so it cannot identify the SMS failure by itself.

**How to apply:** Verify the report webhook configuration and inspect an actual
request-ID-matched provider report before claiming a delivery root cause.