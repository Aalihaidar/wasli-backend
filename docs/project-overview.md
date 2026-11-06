# Wasli: project overview

A high-level picture of what Wasli is, who uses it, how an order travels through it and how this repository is organised. Read it first; the detailed rules are in [`api-conventions.md`](api-conventions.md) and in the generated `openapi/schema.yaml` (the final truth for endpoints, committed with the first endpoint). The checklist of work is [`steps.md`](steps.md).

> **Status:** the repository holds the Django scaffold, the `users` app and the empty shells of the other apps (`core`, `restaurants`, `menu`, `customers`, `chat`, `orders`, `assistant`). Everything below that is not in `users` is the agreed design, built milestone by milestone (D0 to D4 for the demo, then the pilot).

## 1. What Wasli is

Customers parked at a restaurant or cafeteria order **from the car, without honking**. They open a map (or scan the restaurant's QR code), tap the restaurant and **chat with it**: the order is typed or spoken, repeated back with prices and confirmed. The bot then asks one question about the car and the parking spot and one for an optional note, shows the whole order and sends it after a final confirmation. The restaurant sees the order with the car, the parking spot and the customer's distance, **accepts** it with a wait time or **rejects** it with a reason, the answer appears in the same chat, and staff bring the order to the car.

Restaurants pay a flat monthly subscription, with no commission. Languages are Arabic and English (right to left for Arabic), currency AED.

## 2. Who uses it

```mermaid
flowchart TB
    subgraph PT["Platform team (project owners)"]
        OWN["Owner"]
        BRO["Brother"]
    end
    ADM["Django admin<br/>full access to everything:<br/>restaurants, parking lots, menus,<br/>subscriptions, customers and bans"]
    OWN & BRO -->|"email + password"| ADM

    subgraph RA["Restaurant A (isolated tenant)"]
        A1["Restaurant admin<br/>username + password"]
        C1["Cashier or other staff<br/>username + password"]
        MENU["Menu, prices, availability"]
        SET["Restaurant settings"]
        ORD["Orders: view, accept,<br/>reject, mark ready"]
        A1 -->|"menu.edit"| MENU
        A1 -->|"restaurant.settings"| SET
        A1 -->|"members.manage:<br/>create, edit, deactivate,<br/>reactivate"| C1
        A1 -->|"orders.view, orders.decide<br/>reports.view"| ORD
        C1 -->|"orders.view<br/>orders.decide"| ORD
    end

    subgraph RB["Restaurant B (isolated tenant)"]
        B1["Its own admin and staff,<br/>menu and orders"]
    end

    CUST["Customer in a car<br/>email, phone or username + password"]
    CUST -->|"chats and orders,<br/>sees only their own orders"| ORD

    ADM ==>|"manages"| RA
    ADM ==>|"manages"| RB
    RA -. "no access either way" .- RB
```

| Who | Account | Can do |
| --- | --- | --- |
| Platform team | Superuser, signs in with email, uses Django admin | Everything: add, change or delete restaurants, menus, subscriptions, customers |
| Restaurant admin | `User` + membership with role `admin`, signs in with a username | Everything inside their own restaurant: menu, prices, settings, reports, orders, and their cashiers and other staff (create, edit, deactivate, reactivate). Never another restaurant |
| Cashier or other staff | `User` + membership with role `cashier`, signs in with a username | See orders, accept, reject, mark ready. Cannot change menu, prices, members or settings |
| Customer | `User` + a `Customer` profile (anonymous in the demo), signs in with email, phone or username | Chat with a restaurant, place and follow their own orders |

Every permission is a code checked on each request, never a role name: `orders.view`, `orders.decide`, `menu.edit`, `members.manage`, `restaurant.settings`, `reports.view`. An admin has all six, a cashier only the first two. A restaurant admin cannot grant more than their own role, and the last admin of a restaurant cannot be deactivated or demoted. Accounts are never deleted, because past orders point at the person who handled them: an admin deactivates a member (they can no longer sign in) and can reactivate them later.

## 3. The system at a glance

```mermaid
flowchart LR
    CS["Customer site<br/>Flutter web, on a phone"]
    RS["Restaurant site<br/>Flutter web, on a laptop"]
    ADMIN["Django admin<br/>platform team"]

    subgraph API["wasli-backend: Django and DRF"]
        CHAT["chat<br/>conversation engine,<br/>every bot text"]
        ORDERS["orders<br/>pricing, order creation,<br/>order status"]
        REST["restaurants and menu<br/>tenants, staff, menus"]
        PROF["customers<br/>profiles, sessions"]
        ASSIST["assistant<br/>adapter to the<br/>understanding provider"]
    end

    DB[("PostgreSQL")]
    GEM["Gemini<br/>understands text and voice"]

    CS -->|"JSON over HTTPS, polling"| API
    RS -->|"JSON over HTTPS, polling"| API
    ADMIN --> API
    API --> DB
    ASSIST --> GEM
```

- The two sites are separate Flutter apps in the sibling repository. They generate their API client from this repository's `openapi/schema.yaml`.
- The demo runs on free plans: the API on Render, the database on Neon, the two sites on Cloudflare Pages. There are two environments: `develop` is staging (its own Render service and Neon project) and `main` is production (its own Render service and Neon project). Local development and tests also use the staging Neon project directly, with no local database. Everything in the demo stays on free plans. The product moves to paid always-on hosting without changing the data model or the API.
- In the demo the sites poll every 3 seconds. The product replaces polling with a realtime stream and adds notifications, payments and phone verification.

## 4. How an order works

```mermaid
flowchart TD
    A["Customer parks"] --> B{"How to start?"}
    B -->|"Opens the site"| C["Map with nearby restaurants"]
    B -->|"Scans the restaurant QR code"| D["Chat with the restaurant"]
    C --> D
    D --> E["Bot: welcome message and menu images"]
    E --> F["Customer writes or says the order"]
    F --> G["Bot repeats the order with prices and total"]
    G --> H{"Confirm or edit?"}
    H -->|"Edit"| F
    H -->|"Confirm"| I["Bot asks one question: parking spot,<br/>plate, model and colour"]
    I --> J{"Anything missing?"}
    J -->|"Yes"| K["Bot asks only for what is missing"]
    K --> J
    J -->|"No"| L["Bot asks for an optional note"]
    L --> M["Bot shows the whole order:<br/>items, total, car, note, location"]
    M --> N{"Send to the restaurant?"}
    N -->|"Edit"| S["Choose: order, car and parking, or note"]
    S --> M
    N -->|"Yes"| O["Order appears on the restaurant screen<br/>with distance and map"]
    O --> P{"Restaurant decides"}
    P -->|"Accept: 5, 10 or 15 minutes"| Q["Confirmed message in the chat"]
    P -->|"Reject: reason and note"| R["Rejection message in the chat"]
```

### Who understands, who decides

```mermaid
sequenceDiagram
    participant C as Customer chat
    participant B as Backend
    participant G as Gemini
    C->>B: Order, typed or spoken
    B->>G: This restaurant's menu without prices,<br/>the current order, the message or audio
    G-->>B: Transcript and item changes
    B->>B: Check items against the menu, compute the total
    B-->>C: Order with prices and total: confirm or edit?
    C->>B: Confirm
    B-->>C: One question: parking spot, plate, model, colour
    C->>B: One answer, typed or spoken
    B->>G: Pick out the car and parking details
    G-->>B: The fields that were said
    B-->>C: Asks only for what is missing, then the note question
    B-->>C: Whole order: send it?
    C->>B: Yes, send
    B->>B: Create the order
    B-->>C: Order sent
```

The backend decides every next step, **writes every message** in the customer's language, checks items against the menu, calculates every price and creates the order. Gemini is called only to **understand** (the order, a yes or an edit, the car details inside one answer, voice) and never writes text, prices or orders. If it is unavailable the chat still works: the car questions are asked one at a time and an item picker builds the order.

### Conversation states

```mermaid
stateDiagram-v2
    [*] --> ordering: welcome, menu images, first question
    ordering --> ordering: customer adds or edits items
    ordering --> ask_car: customer confirms the order
    ask_car --> ask_car: something missing, ask only for it
    ask_car --> ask_note: parking, plate, model, colour complete
    ask_note --> review: note given or skipped
    review --> ordering: edit the order
    review --> ask_car: edit the car or parking
    review --> ask_note: edit the note
    review --> placed: customer confirms, order created
    placed --> [*]
```

### Order status

```mermaid
stateDiagram-v2
    [*] --> placed
    placed --> accepted: restaurant accepts and sets the wait time
    placed --> rejected: restaurant rejects with a reason
    placed --> cancelled: customer cancels before accept
    accepted --> ready: on the way to the car
    accepted --> delivered: handed over
    ready --> delivered: handed over
    ready --> not_found: staff cannot find the car
    not_found --> ready: customer corrects the car details
    ready --> no_show: customer left
    not_found --> no_show: no answer
    rejected --> [*]
    cancelled --> [*]
    delivered --> [*]
    no_show --> [*]
```

The demo covers `placed`, `accepted` and `rejected` (`ready` is optional). The other statuses come with the pilot. Any other transition is refused with a `409` error.

## 5. How the data fits together

```mermaid
erDiagram
    USER ||--o{ STAFF_MEMBERSHIP : "has (restaurant accounts)"
    RESTAURANT ||--o{ STAFF_MEMBERSHIP : employs
    USER ||--o| CUSTOMER : "may have (registered customers)"
    CUSTOMER ||--o{ CUSTOMER_SESSION : "signs in with"
    CUSTOMER ||--o{ VEHICLE : owns
    PARKING_LOT ||--o{ RESTAURANT : hosts
    RESTAURANT ||--o{ MENU_IMAGE : shows
    RESTAURANT ||--o{ MENU_CATEGORY : has
    MENU_CATEGORY ||--o{ MENU_ITEM : contains
    MENU_ITEM ||--o{ OPTION_GROUP : has
    OPTION_GROUP ||--o{ OPTION : has
    RESTAURANT ||--o{ CONVERSATION : has
    CUSTOMER ||--o{ CONVERSATION : starts
    CONVERSATION ||--o{ MESSAGE : contains
    CONVERSATION ||--o| ORDER : becomes
    RESTAURANT ||--o{ ORDER : receives
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--o{ ORDER_ITEM : contains
    ORDER ||--o{ ORDER_EVENT : logs

    USER {
        uuid id PK
        string username UK "NULL when empty"
        string email UK "NULL when empty"
        string phone UK "NULL when empty"
        bool is_staff "platform team only"
        bool is_superuser "platform team only"
        bool must_change_password
    }
    STAFF_MEMBERSHIP {
        uuid id PK
        uuid user_id FK
        uuid restaurant_id FK
        string role "admin or cashier"
        bool is_active
    }
    CUSTOMER {
        uuid id PK
        uuid user_id FK "NULL for anonymous demo customers"
        string display_name
        bool is_blocked
    }
    ORDER {
        uuid id PK
        uuid restaurant_id FK
        int number "unique per restaurant"
        string status
        int total_minor "fils, 100 per AED"
    }
```

Rules that apply to every table:

- UUID primary key, plus `created_at` and `updated_at` in UTC.
- Money is an integer in fils, in fields named `*_minor`, with the currency `AED` alongside.
- Every restaurant-owned row has a `restaurant` foreign key, and every query is scoped by it. Staff of one restaurant can never read or change another's data.
- An order keeps **snapshots** of names, prices and the customer's answers, so later menu edits never rewrite history. Anything an order points at is protected from deletion.
- Customer-facing text comes in pairs (`name_en`, `name_ar`).

## 6. How this repository is organised

| App | Owns |
| --- | --- |
| `users` | The one account table (`User`): username, email, phone, password |
| `core` | Base model, restaurant scoping, permission codes and checks, money and distance helpers |
| `restaurants` | Parking lots, restaurants, menu images, staff memberships |
| `menu` | Categories, items, option groups, options |
| `customers` | Customer profiles, sessions and their authentication, vehicles, blocks |
| `chat` | Conversations, messages, the conversation engine and every bot text in Arabic and English |
| `orders` | Orders, order items, order events, pricing, order creation and status changes |
| `assistant` | The adapter to the understanding provider (Gemini first, a fake one in tests), prompts, call log |

Working rules:

- Views stay thin; business rules live in tested services (`chat/engine.py`, `orders/services.py`, `assistant/services.py`).
- The API is **contract first**: `openapi/schema.yaml` is generated, committed in the same pull request as the endpoint and never edited by hand.
- Tests never call the real provider.
- Work flows from a topic branch to a pull request into `develop`, then a release pull request into `main`; see [`api-workflow.md`](api-workflow.md).

## 7. Where the project is going

| Step | What it delivers |
| --- | --- |
| D0 | Setup, apps, settings, first deploy |
| D1 | Data model, restaurant and menu endpoints, seed with the first restaurant, the Gemini spike |
| D2 | The conversation engine: welcome to a placed order, by text and by voice |
| D3 | Restaurant side: staff login, orders list, accept and reject (**the demo is shown here**) |
| D4 | Polish: second restaurant, logs, README |
| Before the pilot | Restaurant-admin API (menu, prices, members), customer sign-up and sign-in, audit log, two-factor sign-in for the platform team |
| Pilot and launch | Phone verification, more order statuses, payments choice, realtime, notifications, mobile apps |

The exact checklist, with every step, is in [`steps.md`](steps.md).
