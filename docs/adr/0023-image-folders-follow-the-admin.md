# ADR 0023: Uploaded images go to one folder per restaurant, laid out like the admin

- Status: accepted
- Date: 2026-11-24

## Context

Images were stored by kind (`restaurants/logos/`, `menu/items/`, `restaurants/menu/`), so the bucket mixed every restaurant's files
under random names. The owner wants to browse the media bucket the way the admin is organised: one folder per restaurant, its
logo, its cover, and the menu in the same tree as the categories, subcategories and sub-subcategories, in each environment.
Categories also need a picture of their own (they had none), and the picture must reach the customer app.

## Decision

- **One folder per restaurant**, named after its `slug` (already lowercase kebab case and unique), laid out as
  `restaurants/<slug>/logo/logo.<ext>`, `cover/cover.<ext>`, `menu-images/<caption>.<ext>` and `menu/...`. Everything below the
  restaurant is lowercase kebab case of the **English** name (`core.media_paths.kebab`: ASCII letters and digits, parts cut at 40
  characters for a folder and 60 for a file, a fallback of `category`, `item` or `menu-image` when nothing is left, such as an
  Arabic-only name).
- **The menu mirrors the category tree.** An item's file sits in the folder of its category
  (`menu/burgers/spicy/hot-wings.webp`). A category's own picture sits **one level above its folder**, named after the category
  (`menu/burgers.webp` for the category whose folder is `menu/burgers/`; `menu/burgers/spicy.webp` for a subcategory).
- **Menu images stay** (the pictures of the printed menu that the welcome sends and `menu_images` lists), in `menu-images/`, named
  after their caption. Removing them would be a breaking contract change and was not chosen.
- **A picture for each category level.** `MenuCategory.image` is optional and uploaded in the admin. The API adds `image_url` to
  every menu category: an absolute URL or `null`, like an item's `image_url`. Additive for a reader of the response (the key is
  always present), so no breaking label.
- **The extension is kept** (lowercased); nothing is converted. A new upload never overwrites a file (files are cached for a year),
  so when a name is taken the storage adds its short suffix (`logo_k3j9d2.png`).
- **A rename moves the files, so the folders always match the admin.** After a change is committed (a restaurant's slug or name,
  a category's name or parent, an item's name, a menu image's caption), `core.media_sync.organize` runs for that restaurant only:
  it copies each file that is out of place to its new name, points the row and the chat's picture messages at it, and deletes the
  old file only when no row still names it. Saves that cannot move a file (the order number, the heartbeat) and creations (the
  upload already used the right path) do not look at the storage. The move never fails the save: if the storage is down, the file
  stays where it was, the error is logged, and the next run repairs it.
- **`python manage.py organize_media`** does the same for every restaurant by hand (`--dry-run` prints the plan). It moves the
  files uploaded before this layout existed and repairs a move that could not finish. It can be run again at any time, and a file
  with the storage's suffix counts as in place.
- **Storage columns grow** from 100 to 300 characters (`IMAGE_NAME_LENGTH`): three category levels, an item and a suffix fit.

## Consequences

- Production starts with an empty bucket and gets this layout from its first upload; only staging needs `organize_media`, once.
- A rename of a category with many items copies and deletes each file in the request that saved it (a few seconds at most for a
  menu of this size). A very large menu would need the move in a background task.
- Two restaurants cannot share a folder (the slug is unique). Two categories or items whose names give the same kebab case in the
  same folder keep separate files through the suffix.
- The public URLs of moved files change; the API always returns the current one, so the apps are not affected, but a link someone
  saved by hand stops working. A run that moves files briefly leaves both copies in the bucket.
- The customer app is told about `image_url` on categories in a round; it may ignore it.
