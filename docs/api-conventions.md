# API conventions (defaults)

Short defaults for a project's HTTP API. They keep the contract (`openapi/schema.yaml`)
consistent from the first endpoint; a project may change any of them, but should decide once and
apply it everywhere. Rules that depend on the project (money and currency formats, identifiers,
authentication, domain naming) are **not** here: each project adds its own to this file.

## Versioning

Version in the path: `/api/v1/...`. A breaking change gets a new version (`/api/v2/...`) next to
the old one (see `docs/api-workflow.md`). The `SCHEMA_PATH_PREFIX` setting already keeps the
version out of operation ids and tags.

Paths have no trailing slash (`/api/v1/config`, `/api/v1/restaurants/{slug}`), as in the contract the two
teams agreed. A request with a trailing slash is a `404`.

## One error body

Every error raised inside a DRF view has the same body, so a client has a single error parser. The
template ships it with [drf-standardized-errors](https://github.com/ghazi-git/drf-standardized-errors)
(`EXCEPTION_HANDLER` and the schema class are already set by `scripts/init-django.sh`):

```json
{
  "type": "validation_error",
  "errors": [
    { "code": "required", "detail": "This field is required.", "attr": "price" }
  ]
}
```

- `type` is `validation_error` (invalid input), `client_error` (any other 4xx, including an unreadable body)
  or `server_error`.
- `errors` is a list. `code` is stable and meant for programs (`required`, `blank`, `not_found`,
  `permission_denied`, `throttled`, …); `detail` is human text; `attr` is the field the error belongs to
  (dotted for nested data) or `null` when it is about the request as a whole.
- This is **not** RFC 9457 problem details. The format is the package's own; what the contract
  gives a client is that it is documented and typed.

The set of error codes is open. Every feature that can fail in a new way adds a code, and the error responses share the
same lists, so each list (`ErrorCode<status>Enum` in the schema) is declared `x-extensible-enum`, not `enum`
(`config/openapi_hooks.py`): adding a code is not a breaking change, and the contract check does not fail on it. A client
treats a code it does not know as a generic failure of the HTTP status, and a generated client keeps the code as a string.
The description of each list still names every code. Other enums (a language, a channel, an order status) stay closed.
Removing or renaming a code is a breaking change as always. See [ADR 0012](adr/0012-error-codes-are-an-open-set.md).

What the contract documents: the 400, 401, 403, 404 and 429 responses of each operation that can return
them. The 400 body is one shared schema (`Error400Response`, from `config/api_errors.py`), because
the package's default, one schema per operation and field, grows a generated client by dozens of classes per
endpoint. Add a status code to `DRF_STANDARDIZED_ERRORS["ALLOWED_ERROR_STATUS_CODES"]` (and its enum to
`ENUM_NAME_OVERRIDES`) when a project wants it documented too.

Limits to know:

- Only errors raised inside DRF views are covered. Django's own responses (a disallowed host, a URL outside
  the API, a middleware rejection) keep their normal HTML or plain-text body; a client treats a non-JSON
  error as a generic failure.
- An unhandled exception returns a generic message, never the exception text.
- Errors raised straight from a view (`raise ValidationError(...)` with a custom code) keep that code at runtime;
  the shared 400 schema describes `code` as a string, so nothing needs registering.

## Pagination

Every list endpoint is paginated: the same class everywhere (`DEFAULT_PAGINATION_CLASS` and
`PAGE_SIZE` in `REST_FRAMEWORK`), the same response envelope, and a documented maximum page size.
Prefer cursor pagination for large or fast-changing lists, page-number pagination for small, stable ones.

The shared class is `core.pagination.StandardPagination`: page-number pagination (`?page=`, `?page_size=`)
with a default page size of 20 and a maximum of 100, and the envelope `count`, `next`, `previous`, `results`.

**Exception: the polling lists.** Three lists are read by the sites every few seconds and keep their own
shapes instead of the envelope: `GET /restaurants/nearby`, `GET /conversations/{id}/messages?after_seq=`
and `GET /staff/orders?since=`. They return everything newer than the cursor the client sends. Every other
list is paginated.

## Throttling

Every view is throttled by default: 60 requests a minute per client address when anonymous and 240 a minute
per account when signed in (`DEFAULT_THROTTLE_RATES`). A stricter limit for one endpoint (sending messages,
voice) is set on its view. Counts live in each worker's memory, so the limits are approximate. A throttled
request gets `429` with the code `throttled`.

## Timestamps

UTC, ISO 8601, with an explicit offset: `2026-01-31T14:05:09Z`. Keep `USE_TZ = True`; a client
converts to the user's time zone for display only. Dates without a time are `YYYY-MM-DD`.

## Also

- Field and query-parameter names are `snake_case`.
- Use HTTP status codes for the outcome (`201` created, `204` no content, `400` invalid, `401`/`403`
  not authenticated/allowed, `404` not found, `409` conflict) and keep them in the schema.
- An empty list is `200` with an empty `results`, never `404`.
- Never declare a nullable object reference. A value that may be missing is an optional
  property, absent from the response when it has no value (for example `nearest` on
  `GET /api/v1/restaurants/nearby`). Nullable scalars, such as `logo_url`, are allowed. The
  generated clients read an optional reference as a nullable field, but not a nullable `allOf`
  reference. Declare such a field without `help_text`, so the schema keeps a bare `$ref`, and put
  its explanation in the operation description.
- A value list that grows with features (error codes, `order_type`) is a string declared with
  `x-extensible-enum`, never a closed `enum` (ADR 0012).

## Project rules

Decisions specific to this project, on top of the defaults above.

### Identifiers

- Public ids are UUIDs. A restaurant also has a unique `slug`, used in URLs and QR codes (`/r/<slug>`).
- Every message a client sends in a conversation carries a `client_message_id` (UUID). Retrying the same message reuses the id, and the server returns the earlier result instead of processing it twice.

### Money

- Amounts are integers in minor units (fils, 100 per AED) in fields named `*_minor`, with the currency alongside (`AED`). The API never carries formatted amounts or floats.
- A client never sends a price. The server checks every item against the restaurant's menu and computes the totals.

### Languages

- Arabic (`ar`) and English (`en`) only. Text shown to customers comes as a pair of fields (`name_en`, `name_ar`, `description_en`, `description_ar`); the API returns both and the client picks one. The Arabic side is optional in the data (an English-only restaurant leaves it empty) but never empty in the API: where there is no Arabic text, the English text is returned in the `_ar` field, so a client never receives an empty name ([ADR 0014](adr/0014-optional-arabic-names.md)).
- Chat messages are written by the server in the conversation's `locale`. A client renders them and never builds message text.

### Roles and permissions

- Four kinds of people use the API or the admin. The **platform team** (the project owners) are superusers who manage everything in the Django admin. A **restaurant admin** (`StaffMembership.role = admin`) manages only their own restaurant: menu, prices, availability, members, settings, reports and orders. A **cashier** (`role = cashier`) sees orders and accepts, rejects or marks them ready, and cannot change the menu, prices, members or settings. A **customer** chats and orders from the car and sees only their own conversations and orders.
- Access is decided by permission codes, never by role name: `orders.view`, `orders.decide`, `menu.edit`, `members.manage`, `restaurant.settings` and `reports.view`. An admin has all six, a cashier only `orders.view` and `orders.decide`.
- A restaurant admin manages only their own restaurant's members and cannot grant more than their own role. The last admin of a restaurant cannot be deactivated or demoted. Only the platform team creates or deletes restaurants and creates a restaurant's first admin.
- Accounts are deactivated, never deleted, because past orders point at the person who handled them. A restaurant admin can reactivate a deactivated member.
- A request that is authenticated but not allowed gets `403` with `permission_denied`. Another restaurant's resource is a `404`, so a response never confirms that it exists.

### Authentication

- Everyone with an account (`users.User`) signs in with one identifier plus a password. The login field is named `username` and accepts a username, an email address or a phone number: a value with `@` is an email, a valid phone number (UAE numbers without a country code are accepted) is a phone, anything else is a username. Matching ignores case, spaces and phone formatting. A username has 3 to 30 characters (letters, digits, `.`, `_`, `-`), starts with a letter and has no `@`.
- Restaurant staff (admin and cashier) always have a username and sign in with it (`POST /api/v1/auth/login`), then send `Authorization: Token <token>`. The platform team signs in to the Django admin with email.
- Customers sign up with a full name, an email address or a phone number, and a password. A six-digit code sent to that email or phone proves it; verifying it issues the customer token, sent as `Authorization: Customer <token>`. An unverified account cannot sign in or order. A customer who signed up with an email must also verify a phone number before the first order (decided 2026-11-12; it comes with the pilot, and its error code is agreed in an API request first). Codes expire after 10 minutes, allow five attempts and have a resend limit. From the account settings a customer can add the contact they did not give at sign-up (an email or a phone number); it is confirmed with a code sent to it and saved on the account only after that. Changing a contact that is already on the account is not offered. There is no anonymous customer session. The endpoint shapes are agreed in an API request before they are built.
- Every restaurant-owned resource is scoped to the caller's restaurant. Staff of one restaurant can never read or change another restaurant's data.

### Media

- Images (logo, cover, menu images, item photos) are uploaded by the platform team in the admin and stored in object storage. The API returns absolute URLs, never storage paths.

### Errors

- The error codes a client acts on are stable: `order_invalid_transition`, `item_unavailable`, `invalid_location`, `ai_unavailable`, `transcription_failed`, `conversation_expired`, `invalid_action_for_state`, `audio_too_long`, and for customer accounts `account_exists`, `code_invalid`, `code_expired`, `too_many_attempts`, `account_not_verified`.
- A missing or invalid answer inside the chat (for example a car colour) is not an HTTP error: the server asks the question again in the conversation.

### Location

- Latitude is within [-90, 90], longitude within [-180, 180] and the accuracy in metres is zero or more; anything else is `invalid_location`.
- Location is personal data: it is exposed only to the staff of the restaurant that received the order and to the customer who placed it, and it is never written to logs.

### Orders

- Statuses: `placed`, `accepted`, `rejected`, `cancelled`, `ready`, `delivered`, `not_found`, `no_show`. Any other transition is `409` with `order_invalid_transition`.
- Rejection reasons: `item_unavailable`, `too_busy`, `closing_soon`, `too_far`, `location_unclear`, `other`. A note is required for `other` and optional otherwise.
