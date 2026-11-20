# Entering a restaurant in the Django admin

There is no seed command: the platform team enters each restaurant, its menu and its staff accounts by hand in the Django
admin of the environment (`/admin/`). This guide is the checklist, in the order that works, with the rules for images,
Arabic names, aliases, parking and accounts. Never invent a menu: the restaurant supplies its own.

## Collect first

- The restaurant's name (English, and Arabic when it has one), its address and phone, and its logo.
- The **map position of the door** (latitude and longitude).
- The **parking area** customers use: its name, its centre and a radius (see [Parking area](#parking-area)).
- The menu as photos, and every item with its price in AED, its sizes and options, and its Arabic name when there is one.
- Who will be the restaurant's admin and cashiers (see [Staff accounts](#staff-accounts)).

## Order of entry

1. **Parking lot** (Restaurants, Parking lots): name, address, latitude, longitude of the **centre**, radius in metres
   (300 by default).
2. **Restaurant** (Restaurants, Restaurants): the slug (filled from the English name; lowercase letters, digits and single
   hyphens, never `nearby`), the names, **Active** ticked, the parking lot, the restaurant's own latitude and longitude,
   phone and address, the logo and an optional brand colour (`#RRGGBB`), optional welcome messages. Leave `is_demo` off for
   a real restaurant. The default subscription status `trial` is fine: only `suspended` hides a restaurant. Upload the
   menu images on the same page, with a caption and a sort order.
3. **Menu** (Menu, Menu categories): one category per section, then its items on the same page, with the price **typed in
   AED** (the admin stores fils), availability, an optional photo and the aliases. Sizes and extras are option groups on
   the item's page, with options that carry a price difference in AED (a default option fills a required group the
   customer did not mention).
4. **Staff accounts**: create the users, then add them to the restaurant as members.
5. **Check** the result (see [Check it](#check-it)).

Coordinates: latitude first, then longitude. In the UAE the first is about 24 to 25 and the second about 54 to 55. The admin
accepts swapped values, so check them on a map. To copy a position, press and hold the spot in Google Maps.

## English-only restaurants

Many restaurants have an English name and an English-only menu. The Arabic names of the restaurant, the category, the item,
the option group and the option are **optional**: leave them empty. The API then sends the English text in the Arabic
field too (names, descriptions and captions), so an app never receives an empty name, and nothing is copied into the
database, so renaming the English text renames both. Add the Arabic names later if the restaurant gets them; there is no
migration. The decision is in [ADR 0014](adr/0014-optional-arabic-names.md).

### Aliases

Aliases are other names customers use for an item. The assistant that understands the customer's order matches what is
said, in Arabic or English, against the English name, the Arabic name and the aliases, so good aliases matter most for an
English-only menu. One alias per line in the admin (a comma also splits), at most 20 per item and 60 characters each,
trimmed and without duplicates.

Add, for each item:

- the short or spoken names ("zinger", "karak", "shawarma plate");
- the Arabic name or names a customer would say, in Arabic letters ("برجر دجاج", "كرك");
- Arabic words written in Latin letters when that is how people type them ("burger dajaj");
- the common alternative spellings ("chai karak", "cheese toast").

Do not repeat the English name itself, and do not add another item's name. Sizes, milk and extras do not take aliases: the
assistant matches them by meaning from their names ("كبير" for "Large").

After entering the menu, test the matching with the real provider and the real menu, using invented sentences. It needs the
Gemini key in the environment: without it the spike uses the fake provider, which proves nothing about matching.

```bash
python manage.py assistant_spike order --restaurant <slug> --locale ar --text "ابغى برجر دجاج كبير"
```

## Parking area

A **parking lot** here is the area where the restaurant's customers park. It does not have to be a formal lot: for a
roadside restaurant it is the stretch in front of the door; for a mall or a shared lot it is that lot.

- **Centre:** the middle of where the cars stand (in front of the door for a roadside restaurant).
- **Name:** shown to customers, so use the real name of the lot or the place ("Gulf Food parking area").
- **Radius:** the default is 300 m, right for a shared lot. A roadside restaurant can use about 150 m. The radius decides
  who sees the restaurant on the map (the customer must be within it of the centre) and the label on an order (inside the
  radius `in_lot`, up to three times it `near`, beyond it `far`).
- The customer's exact place (level, bay, street, landmark) is not part of this record: the chat's car question collects it
  in one free answer.

## Images

The admin checks that a file is an image but not its size or type, so follow these rules. Every picture is downloaded by a
customer's phone, and the free server's traffic is limited, so small files matter.

| Image | Where it is used | Format | Size | Weight | Notes |
| --- | --- | --- | --- | --- | --- |
| **Logo** | map list, chat avatar, restaurant page | PNG (WebP is also fine), never SVG | **512 × 512 px**, square | under about 100 KB | Keep the artwork centred with a margin: it is shown in a circle. A transparent or plain background is fine. At least 256 × 256 px |
| **Menu images** | sent in the chat; the customer opens them full width and pinches to zoom | JPEG or WebP | up to **1,600 px on the long side** | **300 KB or less** each | One image per menu page or section, in the order you want (sort order). Shoot flat and straight in good light so the text is readable zoomed. Convert iPhone HEIC photos to JPEG |
| **Item photo** (optional) | the item picker | JPEG or WebP | **800 × 800 px**, square | under about 100 KB | Skip it when there is no good photo |
| **Cover** | not used by the API yet | | | | Leave it empty |

Compress before uploading (any image tool will do), then open the restaurant page in the admin: the preview shows what was
stored.

## Staff accounts

One account table serves everybody. A restaurant account always has a **username** (an email or a phone number is not
enough), and a person can belong to more than one restaurant.

**Username:** 3 to 30 characters, lowercase letters, digits, `.`, `_` and `-`, starting with a letter, no `@`. It is unique
across all restaurants, so every restaurant uses its own prefix.

**Naming rule:** `<restaurant>-admin` and `<restaurant>-cashier`, where `<restaurant>` is the restaurant's slug, shortened
when needed so the whole username stays within 30 characters (`-cashier2` takes 9). Further accounts add a number.

| Setup | Accounts for Gulf Food | Use it when |
| --- | --- | --- |
| **One account for everything** | `gulf-food-admin` (role `admin`) | A small restaurant. An admin has every permission, including seeing and deciding orders, so it does what a cashier does and manages the rest |
| **Admin and cashier** | `gulf-food-admin` and `gulf-food-cashier` | The manager and one shared cashier login |
| **Several of each** | `gulf-food-admin`, `gulf-food-admin2`, `gulf-food-cashier`, `gulf-food-cashier2`, `gulf-food-cashier3` | More than one manager, or one account per cashier so one person can be deactivated alone |

How to create one: Users, Add (username, full name, a temporary password from a password manager, tick *must change
password*), then on the restaurant's page add the user under staff members with the role `admin` or `cashier`. A cashier
only sees and decides orders; menu, prices, members and settings are for an admin. The first member must be an admin, a
restaurant always keeps at least one active admin, and an account is deactivated, never deleted. The staff sign-in
endpoints come with D3: until then the accounts exist but cannot sign in to the restaurant site.

## Check it

- `/api/v1/restaurants/<slug>` shows the restaurant, its images and the whole menu (with an English-only restaurant, the
  Arabic fields hold the English text).
- `/api/v1/restaurants/nearby?lat=<lat>&lng=<lng>` with the **parking area's own centre** lists it, with `is_open` and a
  distance. Never use a real customer's position: a position is personal data, and the server log prints the path only.
- The logo and the menu images load, which also proves the media bucket works on that environment.

Production is a separate environment with its own database: the same entry is repeated there when production exists.
