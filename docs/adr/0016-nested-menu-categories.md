# ADR 0016: Menu categories can nest, up to three levels

- Status: accepted
- Date: 2026-11-20

## Context

A menu had one level of categories. Some restaurants print a menu with categories, subcategories and sub-subcategories
(for example Burgers, Grilled, Chicken). Flattening them into names such as "Burgers - Grilled" works, but loses the
structure the restaurant uses and gives the item picker nothing to group by. The owner wants subcategories and
sub-subcategories as an option from now, before any real menu is entered.

## Decision

- `MenuCategory` gets an optional `parent` (a category of the same restaurant). A menu has **up to three levels**: a
  category, a subcategory and a sub-subcategory. The model refuses a fourth level, a parent from another restaurant, a
  category inside itself or inside one of its own subcategories, and a move that would make the branch deeper than three
  levels. A category with subcategories cannot be deleted (the link is protected), and the database refuses a category that is
  its own parent.
- **Items can sit at any level**, not only the deepest, as in a printed menu where a heading has a few dishes of its own
  next to its subheadings.
- **Visibility.** A category is visible to customers when it is active and so is every category above it. Hiding a category
  hides its subcategories and their items, in the API and in what the assistant is shown. One function decides this
  (`menu.services.visible_categories`).
- **API.** The `menu` list of the restaurant detail stays **flat**, so the shape does not change. It is in depth-first
  order, a category followed by its subcategories, each level by `sort_order` and then name. Each category has an optional
  `parent_id` (the parent's id, **absent** for a top-level category, never `null`). An app that ignores `parent_id` shows a
  sensible flat list; an app that wants a tree builds it from `parent_id`. A flat list with ids also avoids a recursive
  schema, which generated clients handle badly.
- **Admin.** The category form has a *Parent* field that offers only categories that can still have children, and the list
  shows each category's path (`Burgers > Grilled`).

## Consequences

- The contract change is additive: a new optional property and a description. The apps change nothing until they want to
  show the structure.
- A restaurant with a flat menu is unaffected. A restaurant with a nested menu enters the structure as it is printed instead
  of flattening it ([`docs/data-entry.md`](../data-entry.md)).
- The assistant is shown the items only, as before; the category path is not part of the prompt. It can be added later if a
  large menu needs it for matching.
- A fourth level, or real tree rendering in the customer app, would be a new decision.
