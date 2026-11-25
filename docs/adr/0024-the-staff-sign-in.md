# ADR 0024: The staff sign-in, one token per account, and the member's own profile

- Status: accepted
- Date: 2026-11-25

## Context

The restaurant app signs a staff member in, reads who they are and asks for a new password when the platform team gave them a
temporary one. The shapes were agreed with the restaurant app in the API request #94 (its Rounds 2 to 4). Staff use DRF's
`TokenAuthentication` (`Authorization: Token <token>`), the default authentication class of the API; customers have their own
scheme ([ADR 0011](0011-customer-accounts-flow.md)) and the two never open each other's endpoints.

## Decision

- **Endpoints.** `POST /auth/login` (public, `username` and `password`, answers `{token}`), `POST /auth/logout` (`204`),
  `POST /auth/password` (`current_password` and `new_password`, `204`) and `GET /staff/me`. The code is in
  `restaurants/staff_auth.py` (the flows), `staff_serializers.py`, `staff_views.py` and `staff_urls.py`.
- **A token is issued only to an active member of an active restaurant.** A customer, the platform team without a membership, a
  deactivated member, a member of a deactivated restaurant and an inactive account get the same `401 authentication_failed` as a
  wrong password, and no token row is created, so the endpoint never says which accounts exist. An account with memberships in
  two restaurants is refused too: a staff request has no way to say which restaurant it means yet (`resolve_membership` returns
  nothing for an ambiguous account). This is a limit of the first version, lifted when a restaurant picker exists.
- **One token per account, shared by every device** (DRF `authtoken`): a second sign-in returns the same token and a sign-out ends
  it everywhere. Per-device tokens and an expiry are pilot work (`docs/steps.md`, section 14).
- **Two kinds of refusal after sign-in.** An unknown token is `401`. A valid token whose account stopped being an active member
  (deactivated after signing in) is `403 permission_denied` on `GET /staff/me` and `POST /auth/password` (`IsStaffMember`), and
  never on `POST /auth/logout`, so a member is never stuck signed in. `GET /staff/me` and the password change need only the
  membership; the order endpoints will add `orders.view` and `orders.decide` by permission code, never by role name.
- **Limits.** Ten sign-ins a minute per address (`staff_login`, the throttle scope) and ten wrong tries per username in 15 minutes
  whatever the address (`core/limits.py`, shared with the customer sign-in; the count is by the lowercase username, so the way it
  is written changes nothing, and a good sign-in clears it). The password change is ten tries an hour per account
  (`staff_password`), because its current password can be guessed with a stolen token. Counters live in the process cache, so each
  Gunicorn worker counts for itself.
- **The temporary password.** `must_change_password` (set in the admin) is shown by `GET /staff/me`. `POST /auth/password` checks
  the current password, refuses an unchanged one (`password_unchanged`), applies the admin's strength rules
  (`users/passwords.py`: `password_too_short`, `password_too_common`, `password_entirely_numeric`, `password_too_similar`),
  clears the flag and keeps the token. Nothing else is blocked while the flag is true; the app decides how firmly to ask.
- **Shapes.** `role` and the permission codes are extensible lists (`StaffRoleEnum`, `StaffPermissionEnum`, `x-extensible-enum`),
  so a new role or permission is not a breaking change. The restaurant inside `GET /staff/me` is a bare reference and its
  `service_radius_m` is an optional property, absent when the restaurant sets none (the rule of `docs/api-conventions.md`).
  `name_ar` falls back to the English name ([ADR 0014](0014-optional-arabic-names.md)).
- **Shared code moved.** The cache counters moved from `customers/limits.py` to `core/limits.py` and the password strength check
  from `customers/accounts.py` to `users/passwords.py`, so staff and customers use one copy.

## Consequences

- A member who loses the membership keeps a valid token that opens nothing but sign-out; deleting the token is only done by
  sign-out, a password reset by the platform team does not revoke it (per-device tokens and expiry fix this before the pilot).
- A shared tablet and a phone share one token: a sign-out on one signs out the other. The restaurant app accepted this for staging.
- Staff accounts are created in the Django admin; nothing lets a member create or invite another one yet (restaurant-admin API,
  before the pilot).
