# Booking storage compatibility during Publish

Publish compares the actual development database structure with production.
Restoring older application code does not rewind production's schema or data.

The investigated diff required non-null booking-link slots and dropped three
scheduling columns because development no longer matched the previously
published storage contract. Production still had a booking link without a slot.
Its timestamps must not be guessed, and a synthetic slot is not a safe backfill.

Keep these storage definitions in both the SQLAlchemy metadata and development:

- `customer_app_booking_links.slot_id`: nullable UUID, retaining its foreign key.
- `bookings.scheduled_start`, `scheduled_end`, `owner_accepted_at`: nullable
  timestamps with time zone, without defaults or fabricated backfills.

The development Alembic revision `0017_preserve_booking_storage` follows the
existing revision and makes only additive/constraint-relaxing changes. Apply it
through the normal development-only Alembic flow. Never run it against managed
production, stamp production to a local revision, or attach it to build/startup.
Publish owns any production structural changes.

Before retrying Publish, inspect both schemas and recompute the Publish schema
diff. It should no longer require a slot or drop the scheduling fields. An older
production Alembic version is not proof its actual schema is missing migrations.

This correction preserves storage; it does not restore runtime booking features
removed by a source restore. In particular, code that dereferences a slot without
checking for null still needs separate runtime compatibility review for bookings
created by earlier workflows.
