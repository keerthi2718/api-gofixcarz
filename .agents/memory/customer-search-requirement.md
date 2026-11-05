---
name: Customer garage and service search
description: Customer search must connect the garage-owner service catalogue to the shared booking flow.
---

The user requires a customer search bar where searching by service name displays garages together with their matching services, and searching by garage name displays services present in the matching garages, with an option to book. They describe this as “the mediation between the garage app and the customer app.”

The current requirement is garages within **200 KM**, not 5 KM, and only verified,
active garages. The user requires search to return all matching garages and
services because their frontend has no search-pagination controls.

**Why:** The user explicitly replaced the earlier five-kilometre behavior and
five-service preview with a 200 KM, verified-only, uncapped search.

**How to apply:** Do not restore five-kilometre defaults or truncate garage/service
search results. Nearby search needs the selected customer's coordinates; a city
filter can narrow geography but cannot replace a real garage map pin.

The user explicitly requires distance to be shown alongside the service/garage search-to-booking flow, not only used internally to filter nearby garages.

The user reports having a GCP API key with location services and a distance API enabled. The exact enabled Google product, credential access and billing have not been verified; possession of a key is not approval for billable routing calls.

**Why:** The user explicitly requested this discovery-to-booking link after clarifying that the integration concerns customer and garage-owner bookings, not admin APIs.

**How to apply:** Treat garage/service discovery and location-radius filtering as explicitly requested scope for this feature, despite their exclusion from older customer-only approval documents. Carry real garage and service IDs into the existing shared booking flow; keep customer-facing discovery distinct from owner-only management and admin APIs.

Keep customer coordinates in request bodies rather than query strings, and keep distance explicitly geographic rather than implying road distance.

**Why:** Radius filtering does not establish road reachability; query-string locations can leak through infrastructure access logs even when application logs omit them.

**How to apply:** Preserve that privacy and distance distinction when extending discovery or adding a provider. Google road metrics need a separately agreed eligibility/ranking contract.

The user previously requested discovery “by location or city” and prohibited
creating a separate garage/service store or guessing garage coordinates.
Their later explicit change request authorizes date-only direct booking instead
of the old slot/quote flow.

**Why:** Search must reuse the owner's actual catalogue; city membership is not a
confirmed map pin. The newer 200 KM location requirement takes precedence over
the earlier no-coordinate city fallback for the search endpoint.

**How to apply:** Reuse existing records and IDs; do not manufacture a pin to make a
radius search succeed. Garages missing coordinates need a real profile update.
