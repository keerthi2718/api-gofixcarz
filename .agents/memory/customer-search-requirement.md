---
name: Customer garage and service search
description: Customer search must connect the garage-owner service catalogue to the shared booking flow.
---

The user requires a customer search bar where searching by service name displays garages together with their matching services, and searching by garage name displays services present in the matching garages, with an option to book. They describe this as “the mediation between the garage app and the customer app.”

They also asked to get garages based on location, “with in 5km radius like that.”

The user explicitly requires distance to be shown alongside the service/garage search-to-booking flow, not only used internally to filter nearby garages.

The user reports having a GCP API key with location services and a distance API enabled. The exact enabled Google product, credential access and billing have not been verified; possession of a key is not approval for billable routing calls.

**Why:** The user explicitly requested this discovery-to-booking link after clarifying that the integration concerns customer and garage-owner bookings, not admin APIs.

**How to apply:** Treat garage/service discovery and location-radius filtering as explicitly requested scope for this feature, despite their exclusion from older customer-only approval documents. Carry real garage and service IDs into the existing shared booking flow; keep customer-facing discovery distinct from owner-only management and admin APIs.

Keep customer coordinates in request bodies rather than query strings, and keep distance explicitly geographic rather than implying road distance.

**Why:** Radius filtering does not establish road reachability; query-string locations can leak through infrastructure access logs even when application logs omit them.

**How to apply:** Preserve that privacy and distance distinction when extending discovery or adding a provider. Google road metrics need a separately agreed eligibility/ranking contract.
