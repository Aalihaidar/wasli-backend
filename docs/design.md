# Wasli design

The visual rules for every Wasli screen: the customer site, the restaurant site, the later mobile
and tablet apps (all built in Flutter, in the two repositories `wasli-customer-flutter` and
`wasli-restaurant-flutter`) and the Django admin used by
the platform team. A screen that follows this file looks like Wasli. A rule that is missing here is
decided once, in a pull request that changes this file.

Direction chosen by the owner on 2026-11-11: **Ink & Mustard**. A deep ink navy for trust and a
mustard accent for warmth, on a warm off-white background, set in one family (Rubik) that covers
Latin and Arabic. It was picked from thirty directions ranked on fit, distinctiveness, readability,
Arabic and Latin type quality, and loading weight.

## How to use this file

- Token names are `snake_case` here. Flutter uses the same names in `lowerCamelCase`
  (`primary_dark` becomes `primaryDark`); the Django admin uses CSS variables (see
  [Django admin](#django-admin)).
- The hex values in this file are the source of truth. The Flutter theme and the admin stylesheet
  copy them; they never invent a colour of their own.
- Use a token, never a raw hex value, in a widget or a template.
- Both languages ship from day one. Every screen is checked in English (left to right) and in Arabic
  (right to left) before it is done.

## Colour

### Brand and surfaces

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `primary` | `#1F2A44` | `#F2B705` | Main actions, links, the app bar, selected states |
| `primary_dark` | `#121A2E` | `#C99700` | Pressed state of `primary`, headers on the admin |
| `on_primary` | `#FFFFFF` | `#121A2E` | Text and icons on `primary` |
| `accent` | `#F2B705` | `#F2B705` | Highlights: badges, progress, the active tab, price chips |
| `on_accent` | `#121A2E` | `#121A2E` | Text and icons on `accent` |
| `background` | `#FAFAF7` | `#0F1626` | Page background |
| `surface` | `#FFFFFF` | `#182036` | Cards, sheets, inputs, chat bubbles from the restaurant |
| `text` | `#121A2E` | `#F2F1EC` | Body text and headings |
| `text_muted` | `#5B6475` | `#A9B0C0` | Secondary text, captions, placeholders |
| `border_subtle` | `#E3E4E0` | `#2A3550` | Card and divider lines (decoration only) |
| `border_input` | `#7E869A` | `#7B849C` | Input and checkbox outlines (3 : 1 against the surface) |
| `link` | `#2C4FA3` | `#8FB0FF` | Text links in the admin and on web pages (hover: `text`) |
| `focus_ring` | `#1F2A44` | `#F2B705` | Keyboard and screen-reader focus outline, 2 px with a 2 px gap |
| `error` | `#B3261E` | `#FFB4AB` | Error text, destructive buttons, invalid inputs |
| `on_error` | `#FFFFFF` | `#4D1410` | Text on `error` |

`primary_dark` in the dark theme is the pressed colour of the mustard button; it is not used as a
text colour.

### Status colours

The same in every screen, so staff read an order the same way everywhere. A status is never shown by
colour alone: it always carries its label.

| Status | Order state | Light background | Light text | Dark background | Dark text |
| --- | --- | --- | --- | --- | --- |
| `status_warn` | placed, waiting for the restaurant | `#FDF0D0` | `#7A4B00` | `#4A3300` | `#FFDF9B` |
| `status_info` | accepted, being prepared | `#DBEAFE` | `#1E3A8A` | `#14305F` | `#BCD4FF` |
| `status_ok` | ready | `#DFF3E4` | `#14532D` | `#123D24` | `#B7EFC8` |
| `status_bad` | rejected | `#FDE2E0` | `#8A1C14` | `#4D1410` | `#FFC6C0` |

Any other state (for example a closed conversation) uses a neutral pill: `surface` fill with a
`border_subtle` outline and `text_muted` text.

### Rules for the accent

- Mustard is a fill and a highlight, never text on a light background (it is 1.7 : 1 there).
- Text and icons on mustard are always `on_accent` (`#121A2E`).
- At most one strong mustard element per screen region: a badge, a progress bar or a selected tab,
  not all three side by side.
- In the dark theme the mustard is the main action colour, because navy on a dark background has no
  contrast.

### Contrast checks

Computed with the WCAG 2.x contrast formula. The minimum is 4.5 : 1 for text and 3 : 1 for
component outlines and large graphics.

| Pair | Ratio |
| --- | --- |
| `on_primary` on `primary` (light) | 14.3 : 1 |
| `on_accent` on `accent` | 9.5 : 1 |
| `text` on `background` (light) | 16.6 : 1 |
| `text_muted` on `background` (light) | 5.7 : 1 |
| `link` on `background` (light) | 7.3 : 1 |
| `text_muted` on `surface` (light) | 6.0 : 1 |
| `error` on `background` (light) | 6.3 : 1 |
| `border_input` on `surface` (light) | 3.6 : 1 |
| `text` on `background` (dark) | 16.0 : 1 |
| `text_muted` on `surface` (dark) | 7.4 : 1 |
| `link` on `background` (dark) | 8.4 : 1 |
| `on_accent` on `accent` as the dark main button | 9.5 : 1 |
| `border_input` on `surface` (dark) | 4.3 : 1 |
| every status pair, light and dark | 6.5 : 1 or more |

A new colour pair is checked the same way before it is added.

## Typography

One family, **Rubik** (variable, weights 400 to 700), for both English and Arabic. It is open source
(SIL Open Font License). A single variable font keeps the first load small.

- Bundle the font file in the app (`assets/fonts/`). Do not download it when the app opens.
- Digits are always Western (0 to 9), in Arabic and in English.
- Only these weights are used: 400 regular, 500 medium, 600 semibold, 700 bold.

| Style | Size / line height | Weight | Use |
| --- | --- | --- | --- |
| `display` | 32 / 40 | 700 | Restaurant name on its page, empty-state titles |
| `heading_1` | 24 / 32 | 700 | Screen titles |
| `heading_2` | 20 / 28 | 600 | Section titles |
| `heading_3` | 17 / 24 | 600 | Card titles, item names |
| `body` | 16 / 24 | 400 | Body text, chat messages |
| `body_strong` | 16 / 24 | 500 | Prices, emphasis inside body text |
| `body_small` | 14 / 20 | 400 | Secondary information |
| `label` | 14 / 20 | 500 | Form labels, tabs, chips |
| `button` | 16 / 20 | 600 | Button text |
| `caption` | 12 / 16 | 400 | Timestamps, hints, legal text |

Sizes are in logical pixels (`sp` in Flutter) and follow the user's text-size setting up to 200%.
No layout may break when text is enlarged.

Arabic and English together:

- Set letter spacing to `0` for Arabic. For Latin, only `display` and `heading_1` use
  `-0.01em`.
- Use the line heights above as the start. Arabic letters are taller: if an Arabic line clips or
  looks tight, raise the line height by `0.1` for the Arabic locale only, and test with a long
  mixed line (an item name in Arabic with a Latin brand in it).
- Never rely on bold or italic to separate scripts; use size and colour.
- Do not use all capitals for emphasis in English (Arabic has no capitals).

## Spacing, shape and depth

| Token | Value | Use |
| --- | --- | --- |
| `space_1` to `space_8` | 4, 8, 12, 16, 24, 32, 48, 64 | Padding, gaps and margins; always one of these |
| `page_gutter` | 16 on a phone, 24 on a tablet | Left and right page margin |
| `content_max_width` | 560 for the customer site, 1200 for the restaurant site | Centre the content on wide screens |
| `radius_sm` | 8 | Chips, small tags, inputs inside dense tables |
| `radius_md` | 12 | Buttons, inputs, cards |
| `radius_lg` | 16 | Bottom sheets, dialogs, chat bubbles |
| `radius_full` | 999 | Status pills, avatars, the mustard badge |
| `elevation_0` | none, a 1 px `border_subtle` line | Cards at rest |
| `elevation_1` | `0 1px 2px rgba(18, 26, 46, 0.08)` | A card that can be picked up or dragged |
| `elevation_2` | `0 8px 24px rgba(18, 26, 46, 0.16)` | Sheets, menus, dialogs |
| `motion_fast` | 120 ms | Hover, press and focus changes |
| `motion_standard` | 200 ms, `cubic-bezier(0.2, 0, 0, 1)` | Most transitions |
| `motion_sheet` | 300 ms, same curve | Sheets and page changes |

- Depth comes from borders first and shadows second. Do not stack shadows.
- Respect the system "reduce motion" setting: replace movement with a fade.
- Every tap target is at least 48 by 48. The restaurant screen's accept and reject buttons are 56
  high.

## Components

### Buttons

| Kind | Fill | Text | Border | Use |
| --- | --- | --- | --- | --- |
| Primary | `primary` | `on_primary` | none | The one main action of a screen |
| Secondary | `surface` | `primary` | 1.5 px `primary` | A second action next to the main one |
| Tertiary | none | `primary` | none | Low-emphasis actions, in lists |
| Destructive | `error` | `on_error` | none | Reject, delete, cancel an order |

Height 48 (56 on the restaurant screen), horizontal padding 20, radius `radius_md`, text style
`button`. Pressed: `primary_dark` fill. Disabled: 38% opacity, no shadow. A button that starts a
request shows a spinner in place of its label and stays the same width. Icons sit before the label
in the reading direction.

### Inputs

Height 52, `surface` fill, 1.5 px `border_input` outline, radius `radius_md`, label above in `label`
style (never a placeholder as the only label). Focus: 2 px `primary` outline. Invalid: `error`
outline, an error icon, and the message below in `caption` in `error` colour. Helper text in
`text_muted`.

### Cards and lists

A card is `surface` with a 1 px `border_subtle` outline, radius `radius_md` and padding `space_4`.
A restaurant card shows the logo (48 by 48, `radius_md`), the name in `heading_3`, one line of
information in `body_small`, and a single status pill. A menu item row shows the name, the price in
`body_strong`, and a 72 by 72 photo at the end of the row (the start side in Arabic).

### Status pills

`radius_full`, padding 4 by 10, `caption` text in weight 600, colours from the status table. A
pill always has its text label.

### Chat

- The restaurant's messages (and Wasli's questions) sit on the start side in a `surface` bubble with
  a `border_subtle` outline and `text` colour.
- The customer's messages sit on the end side in a `primary` bubble with `on_primary` text.
- Bubbles use `radius_lg`, with the corner toward the sender squared to 4.
- The accept and reject result is a full-width banner using the status colours, not a bubble.
- Timestamps are `caption` in `text_muted`. Menu images open full screen.
- The order summary card inside the chat lists the lines, then the total in `heading_3`, with the
  confirm button below it.

### Bars and navigation

The top bar is `primary` with `on_primary` text and icons, height 56. The active tab shows a 3 px
`accent` underline. The customer site has no bottom navigation: its screens are the map, the
restaurant and the chat. The restaurant site uses a tab bar for the order lists (new, accepted,
ready).

### Feedback

Empty states: a simple line illustration, a `heading_2` title and one sentence, in `text_muted`.
Errors from the API show the message of the error code, never a raw server message. A loading list
shows grey placeholder rows, not a spinner on its own. A banner that needs the user's attention uses
the matching status colours and stays until dismissed.

## Right to left

- Mirror the layout in Arabic: start and end replace left and right in every rule above.
- Mirror icons that point or move (back arrow, send, next). Do not mirror logos, clocks, play
  buttons, or digits.
- Numbers, prices and the plate number stay left to right inside Arabic text; write prices as
  `AED 6.00`.
- Test every screen in Arabic with a long name and an English word in the same line.

## Accessibility

- Contrast is at least 4.5 : 1 for text and 3 : 1 for outlines and icons (see the checks above).
- Meaning is never carried by colour alone.
- Every control has a text label for screen readers; images that carry meaning have a description;
  decorative images have none.
- Focus is always visible and follows the reading order. All screens work with a keyboard.
- Text can grow to 200% without clipping or horizontal scrolling.

## Flutter

The theme lives in each Flutter repository (`wasli-customer-flutter` and `wasli-restaurant-flutter`),
in one place (`lib/theme/`), generated from this file by hand: when this file changes, both themes
change in the same piece of work.

```dart
// Light scheme, copied from the Colour table.
const lightScheme = ColorScheme(
  brightness: Brightness.light,
  primary: Color(0xFF1F2A44),
  onPrimary: Color(0xFFFFFFFF),
  secondary: Color(0xFFF2B705),
  onSecondary: Color(0xFF121A2E),
  error: Color(0xFFB3261E),
  onError: Color(0xFFFFFFFF),
  surface: Color(0xFFFFFFFF),
  onSurface: Color(0xFF121A2E),
  outline: Color(0xFF7E869A),
  outlineVariant: Color(0xFFE3E4E0),
);
```

- `scaffoldBackgroundColor` is `background`, the font family is `Rubik`, and `ThemeData` is built
  with `useMaterial3: true`.
- Status colours and the other tokens that Material has no slot for live in a `ThemeExtension`
  (`WasliColors`) so a widget reads `context.wasli.statusWarnBackground`.
- The dark scheme follows the Dark column; follow the system setting by default.
- The font is declared under `flutter: fonts:` in `pubspec.yaml`, with the licence file shipped in
  the app's licence page.

## Django admin

The admin follows this file. Its stylesheet, `static/admin/css/wasli.css`, keeps Django's variable
names and gives them the values below, in the light and the dark theme (it follows the visitor's
system setting, and the theme button in the header overrides it). The two Rubik files it loads
(`static/admin/fonts/`, with the font's licence) are the only files the stylesheet adds; they come
from this site, so the Content Security Policy needs no change. Statuses and thumbnails use the CSS
classes in `core/admin_display.py`, never inline styles.

| Django variable | Light | Dark |
| --- | --- | --- |
| `--secondary` (header), `--primary` (list and form captions) | `primary` | `surface` and `border_subtle` |
| `--breadcrumbs-bg` | `primary_dark` | `border_subtle` |
| `--accent` (the site name in the header) | `accent` | `accent` |
| `--body-bg`, `--darkened-bg` | `background`, `surface` | `background`, `surface` |
| `--body-fg`, `--body-medium-color`, `--body-loud-color` | `text` | `text` |
| `--body-quiet-color` | `text_muted` | `text_muted` |
| `--link-fg`, `--link-hover-color` | `link`, `text` | `link`, `text` |
| `--link-selected-fg` | `primary` | `accent` |
| `--hairline-color`, `--selected-bg` | `border_subtle` | `border_subtle` |
| `--border-color` (inputs) | `border_input` | `border_input` |
| `--error-fg` | `error` | `error` |
| `--button-bg`, `--default-button-bg` | `primary`, `primary_dark` | `accent` |
| `--button-hover-bg`, `--default-button-hover-bg` | `primary_dark`, `primary` | `primary_dark` (the dark column's) |
| `--button-fg` | `on_primary` | `on_accent` |
| `--delete-button-bg` | `error` | `error` |
| messages and `--selected-row` | the status colours | the status colours |
| `--wasli-brand`, `--wasli-brand-dark` | `primary`, `primary_dark` | (light values; only used in the light theme) |
| `--font-family-primary` | Rubik, then the system fonts | Rubik, then the system fonts |

Two things stay as they were, on purpose: the environment badge next to the site name keeps its
three signal colours (green for local, amber for staging, red for production), and Django's neutral
grey for secondary buttons stays in the light theme.

## Changing this file

A new colour, size or component is added here first, in a pull request that also updates the
Flutter theme or the admin stylesheet, with its contrast check. Removing or renaming a token is a
breaking change for the frontend: say so in the pull request.
