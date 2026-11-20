# ADR 0004: No demo mode and no seed

- Status: accepted
- Date: 2026-11-07

## Context

An earlier plan had a demo mode: a seed command, a reset endpoint, a demo login and a banner. That meant code paths that
exist only for a presentation and a second set of data to keep in step with the real model.

## Decision

- There is no demo mode. Staging is what restaurant managers see; production is the final product. The word "demo" is not
  used as a mode in code or documents.
- There is no seed command. The platform team enters restaurants, menu images, items and staff accounts in
  the Django admin of each environment. The superuser is created with `createsuperuser`.
- `Restaurant.is_demo` stays as an informational flag for a test or fake restaurant (an admin column and filter). It
  changes no behaviour.
- A menu is never invented: the real restaurant's data is entered by the owner.

## Consequences

- Staging and production run the same code, and a restaurant on staging is entered the way it will be in production.
- The simulate buttons and the idle pause on the apps are decided with the frontend, because the API no longer reports a
  demo flag.
