---
name: Production probe limits
description: Interpret workspace network checks cautiously when debugging the API custom domain.
---

Workspace DNS can resolve a published replit.app hostname to a private internal proxy, whose TLS certificate is issued by an internal Replit CA. A successful request through that path does not independently establish public custom-domain TLS health.

**Why:** Custom-domain investigation observed a private proxy address and internal certificate for the generated deployment hostname while the custom hostname failed its TLS handshake.

**How to apply:** Report the exact hostname and result tested. Use deployment logs to corroborate application health and an independent external probe when available for public TLS. A failing external screenshot service is inconclusive, not proof of a specific certificate fault. Inspect Publishing's domain/certificate status before prescribing DNS or domain removal.
