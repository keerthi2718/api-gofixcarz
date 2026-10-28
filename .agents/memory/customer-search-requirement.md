---
name: Customer garage and service search
description: Customer search must connect the garage-owner service catalogue to the shared booking flow.
---

The user requires a customer search bar where searching by service name displays garages together with their matching services, and searching by garage name displays services present in the matching garages, with an option to book. They describe this as “the mediation between the garage app and the customer app.”

**Why:** The user explicitly requested this discovery-to-booking link after clarifying that the integration concerns customer and garage-owner bookings, not admin APIs.

**How to apply:** Treat garage/service discovery as explicitly requested scope for this feature, despite its exclusion from older customer-only approval documents. Carry real garage and service IDs into the existing shared booking flow; keep customer-facing discovery distinct from owner-only management and admin APIs.
