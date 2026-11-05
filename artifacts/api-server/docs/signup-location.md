# Garage signup coordinates

## Release status

This change must be published before production accepts coordinates at signup.
The production OpenAPI URL is https://api.gofixcarz.com/api/openapi.json.
At implementation verification, production still lacked these signup fields;
the running development OpenAPI included them.
No database schema migration is needed: both numeric columns already exist.

## Partner API contract

`POST /api/v1/auth/sign-up` accepts these additional fields:

```json
{
  "latitude": 17.4356741,
  "longitude": 78.3605197
}
```

Include these at the top level alongside the existing signup fields.
Send JSON numbers, not strings, booleans, or empty strings.
Latitude is inclusive [-90, 90]; longitude is inclusive [-180, 180].
Non-finite numbers and partial coordinate pairs return HTTP 422.
Both may be omitted or null for compatibility with older clients, but such
garages cannot appear in radius search until a confirmed pin is saved.
There is no address geocoding or invented fallback location.

The HTTP 201 response retains existing fields and adds `data.garage`, containing
the saved GarageResponse including ID, statuses, latitude and longitude.
`GET /api/v1/garage` returns the same saved values after owner authentication.
Coordinates in GarageResponse remain decimal strings (for example
`"17.4356741"`), preserving the existing response contract.
The database stores numeric values to seven decimal places.

The generated development OpenAPI exposes SignUpRequest and SignUpResult.
Once published, fetch the production OpenAPI again rather than relying on a
cached schema or the unchanged application version number.

## Tests and overwrite behavior

The real development PostgreSQL integration journey calls signup, verifies the
owner OTP, retrieves the garage, performs an unrelated profile update, signs in
a customer, and searches within 200 KM with empty q. Only SMS submission is
mocked; authentication and database access are real. Test rows roll back.

The targeted signup/discovery suite passes 23 tests, including range boundaries,
non-numeric inputs, incomplete pairs, nearby inclusion and discovery regressions.
The test garage has no services and is discoverable when ACTIVE and VERIFIED;
booking eligibility is separate from discovery.

There is no automatic coordinate reset on sign-in, OTP verification, customer
search, or GET garage. Owner PUT /api/v1/garage updates only supplied fields:
omitting latitude/longitude preserves them; supplying a new coordinate changes
it, and explicitly supplying null can clear it. Existing profile-update
semantics are unchanged. The partner app must not send null coordinate fields
for an unrelated profile edit.

Existing garages with missing coordinates are not backfilled by this change.
