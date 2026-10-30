---
name: Customer garage and service search
description: Customer search must connect the garage-owner service catalogue to the shared booking flow.
---

The user requires a customer search bar where searching by service name displays garages together with their matching services, and searching by garage name displays services present in the matching garages, with an option to book. They describe this as “the mediation between the garage app and the customer app.”

They also asked to get garages based on location, “with in 5km radius like that.”

The user reports having a GCP API key with location services and a distance API enabled. They requested a comparison and plan, explicitly saying “Don't do any code modifications”; the exact enabled Google product, credential access and billing have not been verified.

**Why:** The user explicitly requested this discovery-to-booking link after clarifying that the integration concerns customer and garage-owner bookings, not admin APIs.

**How to apply:** Treat garage/service discovery and location-radius filtering as explicitly requested scope for this feature, despite their exclusion from older customer-only approval documents. Carry real garage and service IDs into the existing shared booking flow; keep customer-facing discovery distinct from owner-only management and admin APIs.
