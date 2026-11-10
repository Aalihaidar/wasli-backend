# ADR 0002: Roles, permission codes and restaurant isolation

- Status: accepted
- Date: 2026-11-05

## Context

Many restaurants share one database. A restaurant must never see or change another's menu, orders or members, and a
cashier must not be able to do what only an administrator may. A check against a role name scatters the rules through
every view.

## Decision

- **Roles.** The platform team (superusers, Django admin), a restaurant `admin`, a restaurant `cashier` and customers.
  The restaurant's top role is `admin`, not `owner`, because "owner" means the owners of the project.
- **Permission codes.** `orders.view`, `orders.decide`, `menu.edit`, `members.manage`, `restaurant.settings` and
  `reports.view`. A view asks whether the member has a code, never which role they have (`core/permissions.py` maps
  roles to codes; `restaurants/permissions.py` is the DRF permission class). `admin` has all six, `cashier` has only the
  two order codes.
- **Guardrails.** A restaurant admin manages only that restaurant, cannot grant more than their own role, and the last
  active admin cannot be removed or demoted. Accounts are deactivated, never deleted, because orders refer to them.
- **Tenancy.** Every restaurant-owned table carries a `restaurant` key with `PROTECT` (`core/tenancy.py`). Views reach
  those rows only through `for_restaurant(...)`, and a child row takes its parent's restaurant or is refused. A membership
  is resolved per request; a user with several memberships must name the restaurant.
- **Tests.** One suite checks every tenant table (a new one fails until it is added), and every endpoint adds its own
  isolation test.

## Consequences

- Adding a role is a new row in the role map, not an edit of every view.
- A staff request from a superuser without a membership is refused: the Django admin is how the platform team works.
- PostgreSQL row-level security stays a possible later backstop.
