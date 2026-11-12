# ADR 0013: How the Django admin looks: built-in polish now, a theme later

- Status: accepted
- Date: 2026-11-11

## Short answer, for when it is asked again

The Django admin does not have a fixed look. Wasli now has its own branding and small built-in polish (section "Decision").
A third-party theme such as django-unfold gives a more modern look (a sidebar, a dashboard, nicer forms) at the price of a
dependency and a rework of the admin classes (section "Option 2"). It is not needed now and was deliberately postponed; the
section "When to reconsider" says when to take it up again.

## Context

The Django admin is the platform team's tool: the owner and their brother enter restaurants, menus, images and staff accounts
in it, and read the verification codes on staging. Restaurant owners and managers never see it; they use the restaurant site
(Flutter). The plan says "Django admin first, custom screens only if needed". The default look (a blue-teal header, an
alphabetical list of sections) works, but it is plain, and the data entry that is about to start (the real restaurant and its
menu) benefits from a few things the default lacks.

## Decision: built-in polish (option 1)

No new dependency. Everything is Django's own mechanism, in `config/admin.py`, `config/dashboard.py`, `core/admin_display.py`,
`templates/admin/` and `static/admin/css/wasli.css`:

- **Branding:** "Wasli administration" instead of "Django administration", and a stylesheet that recolours Django's own colour
  variables for the light and the dark theme. The colours and the font (Rubik, two small files served from the site) follow
  `docs/design.md`, the Ink & Mustard design the owner chose on 2026-11-11; `--wasli-brand` holds the primary colour.
- **The environment in the header:** a small `LOCAL`, `STAGING` or `PRODUCTION` label next to the title, so staging is never
  taken for production.
- **Sections in working order** instead of alphabetical: Restaurants, Menu, Orders, Customers, Conversations, Messaging,
  Assistant, then the technical ones (Users, Groups and permissions, API tokens, Scheduled tasks); the models inside a section
  have a fixed order too.
- **Counters on the first page:** active restaurants (and how many are online), orders waiting, orders today, customers with a
  verified contact, assistant calls in 24 hours. Counts only, never a name, contact, car or position.
- **Easier data entry:** thumbnails of logos, covers, menu images and item photos (a preview next to each upload field), the
  items of a category edited on the category's own page with prices typed in AED, a "site online" marker and a subscription
  label on restaurants, and coloured labels for order statuses and assistant outcomes.
- **No inline styles** anywhere (CSS classes only), so the pages keep working when the Content Security Policy is enforced; the
  production policy also allows the media bucket for images (`config/storage.py`, `public_media_sources`).

## Option 2: a third-party theme (not adopted now)

What exists, checked on PyPI on 2026-11-11 (versions and dates move; check again before deciding):

| Package | Version, uploaded | Django versions it declares | What it is | Documentation |
| --- | --- | --- | --- | --- |
| django-unfold | 0.110.1, 2026-11-01 | 5.2, 6.0, 6.1 | "Modern Django Admin" (MIT) | <https://unfoldadmin.com/docs/> |
| django-baton | 5.10.0, 2026-11-06 | 5.1, 5.2, 6.0, 6.1 | "A cool, modern and responsive django admin application" (MIT) | <https://django-baton.readthedocs.io/en/latest/> |
| django-jazzmin | 3.0.5, 2026-06-25 | 5.0, 5.1, 5.2, 6.0 | A drop-in theme using AdminLTE 3 and Bootstrap 5 (MIT) | <https://django-jazzmin.readthedocs.io> |
| django-admin-interface | 0.32.0, 2025-12-19 | 5.0, 5.1, 5.2, 6.0 | The default admin with customizable themes and modals instead of popups (MIT) | <https://github.com/fabiocaccamo/django-admin-interface#readme> |
| django-grappelli | 5.0.1, 2026-10-16 | 5.2, 6.0, 6.1 | "A jazzy skin for the Django Admin-Interface" (BSD) | <http://django-grappelli.readthedocs.org> |

Not candidates: django-jet-reboot (last release 2024, AGPL, no Django version declared), django-material-admin (2021, Django
3.2) and django-adminlte3 (2020).

### Which one, if it is ever done

django-unfold. It is the most modern of the maintained ones, it declares Django 6, and it
had a release within the last two weeks. django-admin-interface is the lightest (it keeps the default admin and adds themes),
and would be the choice if only colours and logo were wanted.

### What it would cost in this project

- A new dependency that must keep up with Django (this project is on Django 6.0), plus the quirks of its own templates.
- Our own overrides of `admin/base_site.html` and `admin/index.html`, the stylesheet and the custom site class in
  `config/admin.py` would be replaced or reworked, because a theme overrides the same templates. The dashboard counters would
  move into the theme's own dashboard mechanism.
- The admin classes (24 classes in seven `admin.py` files at the time of writing) usually need to inherit the theme's own base
  classes to get its forms, filters and actions, and the read-only admins must keep their rules (no add, no change, no delete).
- The helpers `thumbnail` and `badge` produce plain HTML with our CSS classes, so they keep working but need equivalent styles.
- The tests that check markup (`config/tests/test_admin_site.py` and the label tests) would need updating.
- Check before adopting: whether the theme uses inline styles or scripts, because the Content Security Policy is report-only
  today and meant to be enforced later; and what its current documentation says about installation, because it changes.
- A rough size: one to two days including tests, on a branch, behind the same URLs and permissions.

### What it would give

A sidebar navigation, a real dashboard (charts, tables), nicer forms and filters, and a more modern look
overall.

## When to reconsider

- The platform team grows, or non-technical staff use the admin every day.
- The first page needs more than counters (charts, per-restaurant tables, alerts).
- The built-in polish above stops being enough for the data entry (many restaurants onboarded by hand).
- Before the pilot, when the restaurant-admin API and screens are planned: decide then whether restaurant staff get screens of
  their own (the plan) and the Django admin stays internal.

## Consequences

- The admin looks like Wasli's, shows where it runs, and is faster for entering a menu, with no new dependency.
- Choosing a brand colour later is one edit in `static/admin/css/wasli.css`.
- Adding a theme later is a contained piece of work, and this record says what it touches.
- `templates/` and `static/` are new top-level folders; both are included in the production image.
