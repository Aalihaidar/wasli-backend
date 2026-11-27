# Entering a restaurant in the Django admin

There is no seed command: the platform team enters each restaurant, its menu and its staff accounts by hand in the Django
admin of the environment (`/admin/`). This guide is the checklist, in the order that works, with the rules for images,
Arabic names, aliases, service distance and accounts. Never invent a menu: the restaurant supplies its own.

## Collect first

- The restaurant's name (English, and Arabic when it has one), its address and phone, and its logo.
- The **map position of the door** (latitude and longitude).
- How far from the restaurant it serves cars, if it wants a limit (see
  [Location and service distance](#location-and-service-distance)).
- The menu as photos, and every item with its price in AED, its sizes and options, and its Arabic name when there is one.
- Who will be the restaurant's admin and cashiers (see [Staff accounts](#staff-accounts)).

## Order of entry

1. **Restaurant** (Restaurants, Restaurants): the slug (filled from the English name; lowercase letters, digits and single
   hyphens, never `nearby`), the names, **Active** ticked, the address, the restaurant's own latitude and longitude, the
   optional service distance in metres, the phone, the logo and an optional brand colour (`#RRGGBB`), optional welcome
   messages. Leave `is_demo` off for a real restaurant. The default subscription status `trial` is fine: only `suspended` hides a restaurant. Upload the
   menu images on the same page, with a caption and a sort order.
2. **Menu** (Menu, Menu categories): one category per section, with an optional picture of the category (a subcategory and
   a sub-subcategory have one too), then its items on the same page, with the price **typed in
   AED** (the admin stores fils), availability, an optional photo and the aliases. Sizes and extras are option groups on
   the item's page, with options that carry a price difference in AED (a default option fills a required group the
   customer did not mention).
3. **Staff accounts**: create the users, then add them to the restaurant as members.
4. **Check** the result (see [Check it](#check-it)).

Coordinates: latitude first, then longitude. In the UAE latitude is about 22.5 to 26 and longitude about 51.5 to 56.5 (for
example Abu Dhabi city 24.5 and 54.4, Al Ain 24.2 and 55.7, Dubai 25.2 and 55.3, Fujairah 25.1 and 56.3), so the first
number is the smaller one. The admin accepts swapped values, so check the pair on a map.

To copy a position in Google Maps on a computer, zoom in on the entrance (the satellite layer helps), right-click the spot
and click the two numbers at the top of the menu to copy them. On a phone, press and hold the spot; the numbers appear in
the search box. Paste the first number in *Latitude* and the second in *Longitude*.

## Menu structure: categories, subcategories and options

A menu has **up to three levels** of categories: a category, its **subcategories** and their **sub-subcategories**. Nesting
is optional: a restaurant with a short menu uses one level. Items can be put at any level, so a heading can have a few dishes
of its own next to its subheadings. An item holds option groups (sizes, extras), which hold options.

To make a subcategory, add a category (Menu, Menu categories, Add) and choose its **Parent**:

- **Parent empty:** a top-level category.
- **Parent = a top-level category:** a subcategory. **Parent = a subcategory:** a sub-subcategory.
- The parent must be a category of the **same restaurant**. The list of parents shows the path (`Burgers > Grilled`) and leaves
  out a category that is already on the third level, because a fourth level is not allowed.
- To move a category, change its Parent. The admin refuses a loop (a category inside itself or inside one of its own
  subcategories) and a move that would make the branch deeper than three levels.
- Use **Sort order** inside each level to set the order customers see. The categories reach the app depth first: a category,
  then its subcategories, then the next category.
- **Hiding a category hides everything inside it.** Untick *Is active* on a category to hide its subcategories and all their
  items, for customers and for the assistant. A category with subcategories cannot be deleted: move or delete them first.

Two things that are not categories:

- **Sizes, flavours, milk and extras are option groups** on the item (for example *Size* with *Small* and *Large*, each with
  its price difference in AED), not categories and not separate items.
- **Do not repeat an item** in two categories. If a dish appears under two headings in the printed menu, enter it once.

Keep the structure as close to the printed menu as it is useful. A category is only a heading: there is no need for one for
every printed page, and a short menu needs no subcategories at all.

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

Do not repeat the English name itself, and do not add another item's name. Do not give an item an alias that is a general
word shared by many items (for example "burger"): when a customer says it, the assistant asks which one, which is right. Sizes, milk and extras do not take aliases: the
assistant matches them by meaning from their names ("كبير" for "Large").

After entering the menu, test the matching with the real provider and the real menu, using invented sentences. It needs the
Gemini key in the environment: without it the spike uses the fake provider, which proves nothing about matching.

```bash
python manage.py assistant_spike order --restaurant <slug> --locale ar --text "ابغى برجر دجاج كبير"
```

## Location and service distance

There is no parking lot to enter. Customers may park anywhere, and a restaurant has only its own location and, if it
wants, the distance it serves.

- **Position:** the restaurant's door, as latitude and longitude (the admin's *Place* section).
- **Service distance (`service_radius_m`):** metres from the restaurant that it serves cars, for example 300. **Leave it
  empty for no limit of its own.**
- **Who sees the restaurant on the map:** a customer within the **search distance** of the restaurant (3,000 m by default,
  the `NEARBY_SEARCH_RADIUS_M` setting) and, if the restaurant sets a service distance, within that too. A restaurant with no
  service distance is listed for everyone inside the search distance.
- **What the restaurant sees on an order:** the customer's position on a map, the distance in metres and a label: `in_lot`
  inside the service distance, `near` up to three times it, `far` beyond, `unknown` when the customer did not share the
  position. With no service distance the label is measured against 300 m. Nothing is refused because of the distance: the
  restaurant decides and can reject with a reason such as "Customer is too far".
- **Where the car is:** the customer types it in the chat's one car question (level, bay, street, landmark), and the app
  sends the phone's position. The staff order shows both.

## Images

The admin checks that a file is an image but not its size or type, so follow these rules. Every picture is downloaded by a
customer's phone, often over mobile data, and a chat opens all the menu images of a restaurant, so small files make the
chat open fast. The pictures are served from the media bucket, not from the API server.

Prepare every picture with **Squoosh** (see [Preparing a picture with Squoosh](#preparing-a-picture-with-squoosh)).

1,600 px is a maximum, not a target. A picture that is already smaller is **not enlarged** (that only makes it blurry): convert it to JPEG or WebP and compress it to 300 KB or less. If the text is hard to read when you zoom in, or the long side is under about 1,000 px, take or scan the menu again at a higher resolution. A very tall picture (for example 1,000 × 3,000 px) would shrink to an unreadable width at 1,600 px, so cut it into several pictures, one per section, each about 1,200 × 1,600 px, and number them with the sort order.

| Image | Where it is used | Format | Size | Weight | Notes |
| --- | --- | --- | --- | --- | --- |
| **Logo** | map list, chat avatar, restaurant page | PNG (WebP is also fine), never SVG | **512 × 512 px**, square | under about 100 KB | Keep the artwork centred with a margin: it is shown in a circle. A transparent or plain background is fine. At least 256 × 256 px |
| **Menu images** | sent in the chat; the customer opens them full width and pinches to zoom | JPEG or WebP | **1,600 px on the long side at most**, and **about 1,000 px at least** | **300 KB or less** each | One image per menu page or section, in the order you want (sort order). Shoot flat and straight in good light so the text is readable zoomed. Convert iPhone HEIC photos to JPEG. A smaller picture is kept at its size, never enlarged |
| **Item photo** (optional) | the item picker | JPEG or WebP | **800 × 800 px**, square | under about 100 KB | Skip it when there is no good photo |
| **Category picture** (optional; also for a subcategory and a sub-subcategory) | shown with the category in the menu | JPEG or WebP | **800 × 800 px**, square | under about 100 KB | The same rules as an item photo |
| **Cover** | not used by the API yet | | | | Leave it empty |

### Where the files are stored

You do not choose a folder: the backend places every upload in the restaurant's own folder of the media bucket, named after the
restaurant's slug and the English names, all in lowercase kebab case ([ADR 0023](adr/0023-image-folders-follow-the-admin.md)).
For a restaurant `gulf-food`:

```text
restaurants/gulf-food/logo/logo.png
restaurants/gulf-food/cover/cover.jpg
restaurants/gulf-food/menu-images/<caption>.jpg
restaurants/gulf-food/menu/burgers.webp                      the picture of the category "Burgers"
restaurants/gulf-food/menu/burgers/chicken-burger.webp       an item of Burgers
restaurants/gulf-food/menu/burgers/spicy.webp                the picture of the subcategory "Spicy"
restaurants/gulf-food/menu/burgers/spicy/hot-wings.webp      an item of Spicy
```

A name with no English letters falls back to `item` or `category`. A new upload never replaces a file: when a name is taken the
storage adds a short suffix (`logo_k3j9d2.png`). **The folders follow the admin by themselves:** when you rename a restaurant
(its slug), a category, an item or a menu image caption, or move a category under another one, the backend moves the affected
files right after you save (a category with many items takes a few seconds). If a move cannot finish (the storage is down), the
files stay where they were and nothing is lost; run `python manage.py organize_media --dry-run` and then
`python manage.py organize_media` to bring everything back in line.

### Preparing a picture with Squoosh

The standard tool is **Squoosh** ([squoosh.app](https://squoosh.app)), a free tool that runs in the browser. Open it, drop
the file on the page, and use the panel on the right. **Resize is off by default**, so a picture keeps its original,
often huge, size until you turn it on.

| Picture | Resize (turn it on, keep the aspect ratio) | Compress | Target |
| --- | --- | --- | --- |
| **Menu image** | long side **1,600 px** (leave it as it is when it is smaller; never enlarge) | **MozJPEG**, quality **80** | 300 KB or less |
| **Item photo** | **800 × 800 px** | **MozJPEG**, quality **75** | about 100 KB or less |
| **Logo** | **512 × 512 px** | **OxiPNG** (lossless PNG) | about 100 KB or less |

1. Choose the settings above, then read the size under the right-hand image (for example "200 kB").
2. Over the target: lower the quality in steps of 5 (not below about 65 for a menu with text), or reduce the long side of a
   menu image to 1,400 px.
3. Drag the black bar across the preview and zoom in on the text and the edges: it must stay readable and clean.
4. Click the blue download button and give the file a clear name (`gulf-food-menu-1.jpg`, `gulf-food-logo.png`).

Squoosh shows a message such as "No image found in the clipboard" when it opens: ignore it. WebP is also accepted and is a
little smaller than JPEG at the same quality, but JPEG works everywhere. Then open the restaurant page in the admin: the
preview shows what was stored.

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
- `/api/v1/restaurants/nearby?lat=<lat>&lng=<lng>` with a point **close to the restaurant** lists it, with `is_open` and a
  distance. Never use a real customer's position: a position is personal data, and the server log prints the path only.
- The logo and the menu images load, which also proves the media bucket works on that environment.

Production is a separate environment with its own database: the same entry is repeated there when production exists.
