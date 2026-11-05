---
name: Partner map signup integration
description: Partner app map capture and compatibility expectations for garage signup.
---

The user states that the garage partner app captures latitude and longitude
when the owner selects a map location.

**Why:** Registration without the captured pin leaves a garage undiscoverable in
the customer's location-radius search even when its statuses permit discovery.

**How to apply:** Carry the map selection through the existing shared garage
record; do not invent coordinates from an address. Signup coordinates remain
optional as a pair for backward compatibility with existing partner clients,
not because missing pins are eligible for nearby discovery.
