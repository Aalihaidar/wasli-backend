# Legal texts (drafts)

Drafts of the two customer-facing texts, written for the first launch and kept in step with what the backend does. They are **not legal advice**: have a lawyer licensed in the UAE review them, and fill the `[bracketed]` values, before they are published.

| File | For |
| --- | --- |
| [`privacy-policy.md`](privacy-policy.md) | Customers: what personal data Wasli collects, why, who sees it, how long it is kept and their rights |
| [`terms-of-use.md`](terms-of-use.md) | Customers: how the service works, what the restaurant and Wasli are each responsible for, and the rules of use |

Not written yet: the restaurants' subscription agreement and its data-processing terms (a restaurant receives customers' orders, car details and positions), and a cookie notice (the apps use none for tracking).

## Values the owner fills in

- The company's legal name, trade licence number, registered address and emirate; the privacy, support and general contact emails and a phone number.
- The minimum age (the drafts say 18), the governing emirate and courts, and which language prevails.
- The retention periods in section 6 of the policy (proposals only).

## Checks against the product before publishing

- **Payment:** the texts say Wasli takes no payment and the customer pays the restaurant directly. Change both texts the day online payment is added.
- **Providers:** the policy names Render, Neon, Cloudflare, Groq, Google (Gemini), Resend and an SMS provider to be chosen. Keep the list equal to what runs in production; the production messaging backend is disabled until Resend and an SMS provider exist.
- **Positions:** a position is kept with the order and shown to that restaurant's staff only; it is never logged, sent to the assistant or returned to the app. If that changes, change the policy first.
- **Voice:** the audio is processed in memory and never stored; only the transcript stays. Keep it true.
- **Cancellation by the customer** is not in the app yet; the terms say so.

## Work these texts imply in the backend (to plan, not built)

- **Retention:** nothing deletes orders, chats, positions or technical records yet (only the messaging outbox is purged, after 24 hours). Build scheduled deletion that matches section 6 before the pilot.
- **Rights requests:** a way to export and delete one customer's data (the owner can do it by hand in the Django admin at first; an endpoint for account deletion belongs to the pre-pilot list in `docs/steps.md`).
- **Where the texts are shown:** the customer app links to both texts (sign-up screen and settings). That is a request for the customer app: a public address for each text (the staging Pages site, or a page of the backend) is still to be agreed.
- **Arabic:** the UAE expects Arabic and English versions. Have a certified translator produce the Arabic text from the final English one.
