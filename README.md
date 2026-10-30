# py-team2-fitness-membership

## Telegram notifications

Club staff get short Telegram messages about important events: a new membership, its
activation, a freeze and an unfreeze, a successful payment, an expired membership and upcoming
expirations. Messages are sent
in the background, so a slow or unavailable Telegram never slows down or breaks an API request.

### How it works

```
Django view / Celery Beat job
        │  notify_membership_created(membership)      (notification_service/services.py)
        ▼
     Redis queue  ◄── the task is queued only after the DB transaction is committed
        │
        ▼
Celery worker: send_notification(event, object_id)    (notification_service/tasks.py)
        │  loads the object, builds the text           (notification_service/messages.py)
        ▼
Telegram Bot API (aiogram)                             (notification_service/telegram_client.py)
        ▼
Staff Telegram chat
```

Only the event name and the object id travel through Redis. The worker loads fresh data
from the database and builds the message itself.

### Setup

1. Create a bot: open [@BotFather](https://t.me/BotFather), send `/newbot` and copy the token.
2. Create a chat for the staff (a group works best) and add the bot to it.
3. Get the chat id: add the bot to the group, run the bot (see below) and send `/chatid`
   in that group. The id of a group is negative, for a supergroup it starts with `-100`.
4. Put the values into `.env` (the file is not committed, use `.env.sample` as a template):

| Variable | Description | Default |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather. Never commit it or paste it into chats. | empty (notifications are skipped) |
| `TELEGRAM_CHAT_ID` | Id of the staff chat that receives the messages. | empty (notifications are skipped) |
| `TELEGRAM_TIMEOUT` | Total HTTP timeout for one request to Telegram, in seconds. | `10` |
| `CELERY_BROKER_URL` | Redis url used by the queue. In Docker it is set to `redis://redis:6379/0`. | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Redis url for task results. | `redis://localhost:6379/0` |
| `TIMEZONE` | Time zone of the scheduled jobs (daily reminders). | `Europe/Kyiv` |

Every developer should use **their own dev bot and a test chat**. Two running instances of the
same bot (for example on two laptops) conflict with each other, and tests must never write
to the real staff chat.

### Running

**Everything in Docker:**

```bash
docker compose up -d --build
docker compose ps
```

Services related to notifications: `redis` (queue), `celery` (worker that sends messages),
`celery-beat` (daily jobs) and `bot` (answers `/start` and `/chatid`).

After you change Python code or `.env`, restart the worker, it reads them only at start:

```bash
docker compose restart celery
```

**Django on your machine, Redis and the database in Docker:**

```bash
docker compose up -d db redis
python manage.py migrate
celery -A config worker -l info          # on Windows add: -P solo
python manage.py run_telegram_bot        # optional, only for /chatid
```

In `.env` use `DB_HOST=localhost`, `DB_PORT=5433` (the port published by `docker-compose.yml`)
and `CELERY_BROKER_URL=redis://localhost:6379/0`.

If the worker is not running, messages simply wait in the queue and nothing arrives in Telegram.

### Events

| Event | When it is sent | Function | Called from | Status |
|---|---|---|---|---|
| New membership | a membership is created | `notify_membership_created(membership)` | membership purchase, `membership_service/views.py` | ⏳ pending |
| Membership frozen | a freeze is saved | `notify_membership_frozen(membership)` | `freeze` action, `membership_service/views.py` | ⏳ pending |
| Membership unfrozen | a frozen membership becomes `ACTIVE` again, by hand or when the freeze ends | `notify_membership_unfrozen(membership)` | `resume` action, `membership_service/views.py`; `unfreeze_memberships`, `membership_service/tasks.py` | ⏳ pending |
| Payment received | a payment becomes `PAID` for the first time | `notify_payment_success(payment)` | `PaymentService.mark_payment_as_paid_and_membership_as_active`, `payment_service/services.py` | ⏳ pending |
| Membership activated | a new membership becomes `ACTIVE` after its first payment | `notify_membership_activated(membership)` | `PaymentService.mark_payment_as_paid_and_membership_as_active`, `payment_service/services.py` | ⏳ pending |
| Membership expired | the daily job marks a membership as `EXPIRED`, a renewal fails, or an unpaid membership expires | `notify_membership_expired(membership)` | `mark_expired_memberships`, `membership_service/tasks.py`; `PaymentService.mark_payment_as_expired`, `payment_service/services.py` | ✅ daily job, ⏳ pending for unpaid |
| Expires soon | 7, 3 and 1 day before `end_date` | `notify_expiration_reminder(membership, days_left)` | `send_expiration_reminders`, `membership_service/tasks.py` | ✅ |

The two daily jobs run every day at 08:00 in the `TIMEZONE` time zone and only look at `ACTIVE`
memberships.

#### Example messages

The labels are bold in Telegram.

```
🆕 New membership

ID: #12
Member: Anna Kovalenko (anna.kovalenko@example.com)
Plan: Gold (gold-30)
Tier: 🥇 Premium
Price paid: 49.99 USD
Period: 2026-11-01 → 2026-12-01 (30 days)
Status: 🟢 Active
Auto-renew: 🔄 Yes
```

```
❄️ Membership frozen

ID: #12
Member: Anna Kovalenko (anna.kovalenko@example.com)
Plan: Gold (gold-30)
Frozen period: 2026-11-10 → 2026-11-16 (7 days)
New end date: 2026-12-08
```

```
🔥 Membership unfrozen

ID: #12
Member: Anna Kovalenko (anna.kovalenko@example.com)
Plan: Gold (gold-30)
Status: 🟢 Active
Was frozen: 2026-11-10 → 2026-11-16 (7 days)
Ends: 2026-12-08
```

```
💰 Payment received

Payment ID: #31
Member: Anna Kovalenko (anna.kovalenko@example.com)
Type: 🛒 Membership purchase
Amount: 49.99 USD
Plan: Gold (gold-30)
Membership ID: #12
```

```
✅ Membership activated

ID: #12
Member: Anna Kovalenko (anna.kovalenko@example.com)
Plan: Gold (gold-30)
Status: 🟢 Active
Period: 2026-11-01 → 2026-12-01 (30 days)
Auto-renew: 🔄 Yes
```

```
⌛ Membership expired

ID: #12
Member: Anna Kovalenko (anna.kovalenko@example.com)
Plan: Gold (gold-30)
Ended: 2026-12-01
Auto-renew: ❌ No
```

```
⏰ Membership expires soon

ID: #12
Member: Anna Kovalenko (anna.kovalenko@example.com)
Plan: Gold (gold-30)
Ends: 2026-12-01
Days left: 3 days
```

The Stripe session url and id are never included in a message.

### Sending a notification from your code

Other apps use only the functions from `notification_service.services`:

```python
from notification_service.services import notify_membership_created

notify_membership_created(membership)
```

Rules:

1. Do not call the Celery task directly, use the `notify_*` functions.
2. Save the object first, then call the function. The worker reads the object from the
   database, not from memory.
3. The function waits for the transaction to commit (`transaction.on_commit`), so it is safe
   to call it inside `transaction.atomic()`. A rolled-back change sends nothing.
4. The function never raises. If Redis is unavailable the error is logged and your request
   continues.
5. Call `notify_payment_success` only when the status really changes from `PENDING` to `PAID`,
   otherwise a repeated Stripe webhook sends the message twice.
6. Call `notify_membership_activated` and `notify_membership_unfrozen` only after the status
   was saved as `ACTIVE` and only when it really changed (not for a membership that was
   already `ACTIVE`). For a bulk `.update()` load the objects first and notify each one.
7. To add a new event: add it to `NotificationEvent` and write a builder in
   `notification_service/messages.py`, register it in `_BUILDERS` and in `_EVENT_SOURCES`
   (`notification_service/tasks.py`), then add a `notify_*` function.

### What happens when something goes wrong

| Situation | Behaviour |
|---|---|
| Telegram is unavailable, a network error, a timeout or a 5xx | The task is retried up to 5 times. The pause is `min(10 · 2ⁿ, 300)` seconds (10, 20, 40, 80, 160) plus up to 5 seconds of random jitter. |
| Telegram answers 429 (too many requests) | The task waits as long as Telegram asks (`retry_after`) plus 1 second. Telegram allows roughly 20 messages per minute to one group, so many expirations at once arrive with a delay, but they arrive. |
| All retries are used | The notification is dropped and an error is written to the log. Nothing else is affected. |
| Wrong token, the bot was removed from the chat, chat not found, bad request | No retry, because it cannot help. The reason is written to the log. |
| The group became a supergroup | Its chat id changes. The log says so, set the new `TELEGRAM_CHAT_ID`. |
| Telegram cannot parse the HTML | The message is sent again once as plain text. |
| Redis is down | The `notify_*` function logs the error and returns, the API request is not affected. The notification is lost. |
| The object was deleted before the worker ran | The notification is skipped with a warning. |
| Text is longer than 4096 characters | It is cut, and a single field is cut at 200 characters. |

Good to know:

- If Telegram answers slowly, a message can be delivered and still be retried, so a duplicate
  is possible. For staff notifications this is acceptable.
- The bot token is never written to logs or exception messages.
- The sender uses `asyncio.run`, so it must be called from synchronous code (a Celery task,
  a management command or the Django shell), not from an async view.

### Telegram bot (`/start`, `/chatid`)

The bot is a separate process that answers two commands:

- `/start`: a short greeting;
- `/chatid`: replies with the id of the current chat, use it to fill `TELEGRAM_CHAT_ID`.

```bash
python manage.py run_telegram_bot     # or: docker compose up -d bot
```

Sending notifications does not need the bot process, the worker talks to Telegram directly.
Only one process may run the bot for the same token. Commands sent while the bot was offline
are ignored after a restart.

### Checking it manually

In `python manage.py shell` (inside Docker: `docker compose exec app python manage.py shell`):

```python
# 1. Only Telegram: no database, no queue
from notification_service.telegram_client import send_telegram_message
send_telegram_message("Just <b>test</b>")           # True and a message in the chat

# 2. A real card from the database, without the queue
from notification_service.tasks import send_notification
send_notification.run("membership_created", 1)      # 1 is a membership id

# 3. The full path through Redis and the worker
from membership_service.models import Membership
from notification_service.services import notify_membership_created
notify_membership_created(Membership.objects.first())
```

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| Nothing arrives, no `received` line in the worker log | The worker or Redis is not running, or the `notify_*` call is missing. Check `docker compose ps` and `docker compose logs celery`. |
| `Telegram API rejected the message: TelegramUnauthorizedError` | `TELEGRAM_BOT_TOKEN` is wrong or was revoked. |
| `chat not found` | `TELEGRAM_CHAT_ID` is wrong, or the bot is not in that chat. |
| A bot reply or `/chatid` returns a different id than expected | The command was sent in another chat (a private chat id is positive, a group id is negative). |
| `Could not queue notification` in the application log | Redis is unavailable, check `CELERY_BROKER_URL` and `docker compose ps`. |
| Repeated conflict errors in the bot log | The same bot token is used by two running instances. |
| Changes in code or `.env` have no effect | Restart the worker: `docker compose restart celery`. |
| On Windows the local worker does not start | Use `celery -A config worker -l info -P solo`. |

### Tests

```bash
pytest notification_service/tests.py
```

The tests never call the real Telegram (the aiogram call is replaced by a mock) and need only the
database. They cover the Telegram client and its error handling, all message builders, the Celery
task with its retry rules and the `notify_*` functions.

### Where the code lives

| File | Purpose |
|---|---|
| `notification_service/services.py` | `notify_*` functions for other apps |
| `notification_service/tasks.py` | the `send_notification` Celery task and the retry policy |
| `notification_service/messages.py` | message texts, HTML escaping, `NotificationEvent` |
| `notification_service/telegram_client.py` | sending through aiogram, error classification |
| `notification_service/exceptions.py` | `TemporaryTelegramError`, `PermanentTelegramError` |
| `notification_service/bot.py` | the bot with `/start` and `/chatid` |
| `notification_service/management/commands/run_telegram_bot.py` | `python manage.py run_telegram_bot` |

## Membership service

The `Membership Service` manages the complete lifecycle of club memberships: purchasing, viewing, freezing, resuming, upgrading, and canceling automatic renewals. All endpoints are protected and respect role-based permissions (regular members manage only their own memberships, while staff members can view and filter all records).

### Core Business Rules

1. **Single Active Membership:** A user can have at most one `ACTIVE` or `FROZEN` membership at a time. This is enforced both at the application level (serializers/views) and guaranteed at the database level via a conditional `UniqueConstraint`.
2. **Purchasing (`POST /api/memberships/`):** 
   * Sets `start_date` to today and calculates `end_date` based on the selected plan's duration.
   * Creates a `MEMBERSHIP_PURCHASE` payment record and generates a Stripe Checkout session.
   * Triggers a staff notification via `notify_membership_created`.
3. **Freezing (`POST /api/memberships/<id>/freeze/?to=YYYY-MM-DD`):**
   * Allowed only for `ACTIVE` memberships within their validity window.
   * **One-time limit:** Each membership can be frozen only once (`was_frozen = True`).
   * **Duration limit:** Maximum freeze window cannot exceed **30 days**.
   * Shifts the membership `end_date` forward by the number of frozen days and updates Stripe trial/billing end if auto-renew is enabled.
4. **Resuming (`POST /api/memberships/<id>/resume/`):**
   * Unfreezes a `FROZEN` membership back to `ACTIVE`.
   * If resumed before the scheduled `frozen_to` date, unused freeze days are automatically subtracted back from `end_date`.
5. **Upgrading (`POST /api/memberships/<id>/upgrade/?plan_id=...`):**
   * Allows upgrading to a plan with a higher price and same duration (for auto-renew).
   * Calculates a prorated upgrade fee (`UPGRADE_FEE`) based on the remaining value of the current plan using daily rates.
6. **Canceling Auto-Renewal (`POST /api/memberships/<id>/cancel-renewal/`):**
   * Communicates with Stripe to cancel the subscription at the end of the paid period and updates `auto_renew = False`.

### API Endpoints (`/api/memberships/`)

| Method | Endpoint | Description | Access |
|---|---|---|---|
| **GET** | `/api/memberships/memberships/` | List and filter memberships (`status`, `auto_renew`, `member_id`, `from`, `to`) | Users see own, `staff` sees all |
| **POST** | `/api/memberships/memberships/` | Purchase a new membership and init Stripe payment | `IsAuthenticated` |
| **GET** | `/api/memberships/memberships/<id>/` | Retrieve membership details, plan info, and payments | Owner or `staff` |
| **POST** | `/api/memberships/memberships/<id>/freeze/` | Freeze active membership (`?to=YYYY-MM-DD`) | Owner or `staff` |
| **POST** | `/api/memberships/memberships/<id>/resume/` | Resume a frozen membership back to `ACTIVE` | Owner or `staff` |
| **POST** | `/api/memberships/memberships/<id>/upgrade/` | Create upgrade payment session (`?plan_id=...`) | Owner or `staff` |
| **POST** | `/api/memberships/memberships/<id>/cancel-renewal/` | Disable auto-renewal at period end in Stripe | Owner or `staff` |

### Database Constraints

The `Membership` model uses robust database-level constraints to prevent invalid states:
* `unique_active_or_frozen_membership_per_member`: Ensures a member cannot have overlapping active or frozen memberships.
* `membership_end_date_gte_start_date`: Ensures `end_date` is never earlier than `start_date`.
* `membership_frozen_range_valid`: Ensures `frozen_to` is greater than or equal to `frozen_from` when specified.
## Stripe payments

Stripe handles initial membership purchases, paid plan upgrades and automatic renewals.
The application creates Checkout Sessions, stores their state in the `Payment` model and
changes memberships only after receiving a verified Stripe webhook.

The client must not mark a payment as paid directly. Stripe webhooks are the source of truth
for successful, expired and recurring payments.

### How it works

```text
Client creates a membership or requests an upgrade
        │
        ▼
PaymentService creates a Stripe Checkout Session
        │
        ├── Payment(status=PENDING)
        └── session_url is returned to the client
                    │
                    ▼
             User pays in Stripe
                    │
                    ▼
POST /api/payments/webhook/
        │  verifies the Stripe-Signature header
        ▼
PaymentService updates Payment and Membership
        │
        ├── initial purchase → membership becomes ACTIVE
        ├── upgrade fee     → the new plan is applied
        ├── renewal paid    → end_date is extended
        └── renewal failed  → membership becomes EXPIRED
```

The API returns the Stripe-hosted `session_url`. The frontend should redirect the user to
that URL and wait for the webhook to update the payment and membership state.

### Setup

Add the Stripe credentials to `.env`:

| Variable | Description |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe secret API key. Use a test-mode key during development. |
| `STRIPE_WEBHOOK_SECRET` | Signing secret used to verify incoming Stripe webhooks. |

Never commit either value or expose the secret key to the frontend.

For local development, forward Stripe events to Django with the Stripe CLI:

```bash
stripe login
stripe listen --forward-to localhost:8000/api/payments/webhook/
```

Copy the `whsec_...` value printed by `stripe listen` into `STRIPE_WEBHOOK_SECRET`, then
restart Django.

The webhook endpoint is:

```text
POST /api/payments/webhook/
```

It is CSRF-exempt because requests come from Stripe, but every request must contain a valid
`Stripe-Signature`. A missing or invalid signature returns `400`. If the webhook secret is
not configured, the endpoint returns `500`.

### Stripe products and prices

Creating a membership plan also creates the following Stripe objects:

- one Stripe Product;
- one one-time USD price for ordinary purchases;
- one recurring USD price whose interval matches `duration_days`.

The Stripe Product ID is saved in `MembershipPlan.stripe_product_id`.

Billing fields cannot be changed after a plan has been synchronized with Stripe. Create a
new plan instead. When an unused plan is deleted, its active Stripe prices and product are
archived before the local plan is removed.

A plan cannot be deleted while it is referenced by a membership or an upgrade payment.

### Payment types and statuses

| Field | Value | Meaning |
|---|---|---|
| Type | `MEMBERSHIP_PURCHASE` | Initial payment for a membership |
| Type | `UPGRADE_FEE` | Prorated payment for moving to a more expensive plan |
| Status | `PENDING` | Checkout Session was created and is waiting for Stripe |
| Status | `PAID` | Stripe confirmed the payment |
| Status | `EXPIRED` | Checkout Session expired before payment |

Each payment stores:

- its membership and, for upgrades, the target plan;
- the amount in USD;
- the Stripe Checkout Session ID;
- the Stripe-hosted Checkout URL;
- its creation time.

Payment fields exposed by the API are read-only. Payments are created and updated only by
the payment workflow.

### Purchasing a membership

Authenticated users create a membership through:

```text
POST /api/memberships/memberships/
```

Example request:

```json
{
  "plan_id": 3,
  "auto_renew": true
}
```

The response contains both the membership and its payment:

```json
{
  "membership": {
    "id": 12,
    "plan": 3,
    "status": "FROZEN",
    "auto_renew": true,
    "price_at_purchase": "49.99"
  },
  "payment": {
    "id": 31,
    "status": "PENDING",
    "money_to_pay": "49.99",
    "payment_type": "MEMBERSHIP_PURCHASE",
    "target_plan": null,
    "session_url": "https://checkout.stripe.com/..."
  }
}
```

The membership is initially `FROZEN` and becomes `ACTIVE` only after Stripe sends a paid
`checkout.session.completed` event.

For an ordinary membership, Checkout uses one-time payment mode. When `auto_renew=true`,
Checkout uses subscription mode and the resulting Stripe subscription ID is stored on the
membership.

Before Checkout is created, the service verifies that:

- the plan is synchronized with Stripe;
- exactly one suitable active Stripe price exists;
- the Stripe amount matches `price_at_purchase`;
- the Stripe currency is USD;
- the membership has not already been paid.

If an open or completed pending Checkout Session already exists, it is reused. This prevents
repeated API requests from creating several active sessions for the same purchase.

### Successful and expired Checkout Sessions

The initial payment is completed by the webhook, not by the success redirect.

For a successful membership purchase:

1. the membership period starts on the current local date;
2. `end_date` is calculated from the plan duration;
3. the membership becomes `ACTIVE`;
4. the Stripe subscription ID is saved when auto-renew is enabled;
5. the payment becomes `PAID`;
6. a payment notification is queued.

For a successful upgrade:

1. the Stripe subscription price is changed for future billing cycles when auto-renew is enabled;
2. the membership is assigned to the target plan;
3. the upgrade payment becomes `PAID`;
4. a payment notification is queued.

When `checkout.session.expired` is received, a pending payment becomes `EXPIRED`.
An unpaid initial membership also becomes `EXPIRED` when no other pending or paid purchase
payment exists for it.

Repeated completion and expiration webhooks are safe: an already paid or expired payment is
returned without applying the same state change twice.

### Automatic renewal

Auto-renew memberships use a Stripe subscription.

| Stripe event | Condition | Application behaviour |
|---|---|---|
| `invoice.paid` | `billing_reason=subscription_cycle` | Set `end_date` from the Stripe billing period and keep the membership `ACTIVE` |
| `invoice.payment_failed` | `billing_reason=subscription_cycle` | Cancel the Stripe subscription, set the membership to `EXPIRED` and disable auto-renew |
| Other invoice events | — | Acknowledge without changing the membership |

A frozen membership remains `FROZEN` after a successful renewal, but its `end_date` is still
updated from the Stripe invoice.

Freezing an auto-renew membership moves the Stripe billing date to the extended membership
end date without proration. Resuming it early moves the billing date back when unused freeze
days are removed.

Automatic renewal can be disabled through:

```text
POST /api/memberships/memberships/{membership_id}/cancel-renewal/
```

Stripe is configured with `cancel_at_period_end=true`, so access continues until the end of
the already paid period. Calling the endpoint again is safe and returns a successful response.

### Plan upgrades

An upgrade Checkout Session is created through:

```text
POST /api/memberships/memberships/{membership_id}/upgrade/?plan_id={new_plan_id}
```

An upgrade is allowed only when:

- the membership is `ACTIVE` or `FROZEN`;
- its initial purchase payment is already `PAID`;
- the target plan is more expensive than the current plan;
- a payable part of the membership period remains;
- auto-renew memberships keep the same plan duration.

The upgrade fee is prorated by the remaining days:

```text
current daily rate = current plan price / current plan duration
new daily rate     = new plan price / new plan duration

upgrade fee =
    (new daily rate - current daily rate) × remaining membership days
```

The result is rounded to two decimal places and charged as a one-time USD payment.

The plan does not change when the upgrade session is created. It changes only after the
corresponding `checkout.session.completed` webhook confirms payment.

If an open upgrade session already exists for the same target plan, it is reused. A request
for a different target plan is rejected until the existing session is paid or expires.

For auto-renew memberships, a successful upgrade also changes the subscription item to the
new recurring price with `proration_behavior="none"`. The one-time upgrade fee covers the
current period; the new recurring price applies to future cycles.

### Webhook events

| Event | When it is processed | Result |
|---|---|---|
| `checkout.session.completed` | `payment_status=paid` | Complete the initial purchase or upgrade |
| `checkout.session.expired` | always | Mark the related pending payment as expired |
| `invoice.paid` | recurring subscription cycle | Renew the membership |
| `invoice.payment_failed` | recurring subscription cycle | Expire the membership and cancel its subscription |
| Any other event | — | Return `200` without changes |

Stripe may deliver the same event more than once. Payment transitions are protected with
database transactions and row locks, and already processed payments are not applied again.

Returning a non-2xx response tells Stripe to retry the webhook. For example, malformed
recurring invoices without a subscription ID or line items return `500`.

### What happens when something goes wrong

| Situation | Behaviour |
|---|---|
| Missing `Stripe-Signature` | The webhook returns `400`. |
| Invalid payload or signature | The webhook returns `400` and logs a warning. |
| `STRIPE_WEBHOOK_SECRET` is missing | The webhook returns `500`. |
| The plan has no Stripe Product ID | Checkout creation is rejected. |
| No active matching Stripe price exists | Checkout creation is rejected. |
| Several matching active prices exist | Checkout creation is rejected to avoid selecting an arbitrary price. |
| Stripe amount differs from the local membership price | Checkout creation is rejected. |
| Stripe currency is not USD | Checkout creation is rejected. |
| A membership was already paid | A second initial Checkout Session is not created. |
| A repeated paid webhook arrives | The already paid payment is returned without repeating the update. |
| A recurring payment fails | The Stripe subscription is cancelled and the membership expires. |
| Stripe cannot update a subscription during freeze or cancellation | The local membership change is not applied and the API returns an error. |

### Current development URLs

Checkout Sessions currently use these redirect URLs:

```text
http://localhost:8000/payments/success/
http://localhost:8000/payments/cancel/
```

They are redirect destinations only and do not confirm a payment. The corresponding Django
routes are not currently defined, so they should be replaced with real frontend URLs before
deployment.

The frontend must treat the redirect as informational and fetch the membership again until
the webhook has changed the payment state.

### Checking it manually

Start Django and the Stripe webhook forwarder:

```bash
python manage.py runserver
stripe listen --forward-to localhost:8000/api/payments/webhook/
```

Trigger test events with the Stripe CLI:

```bash
stripe trigger checkout.session.completed
stripe trigger checkout.session.expired
stripe trigger invoice.paid
stripe trigger invoice.payment_failed
```

Generic CLI fixtures might not contain IDs that exist in the local database. For a complete
end-to-end check, create a membership through the API, open its returned `session_url` and
pay with a Stripe test card:

```text
4242 4242 4242 4242
```

Use any future expiration date, any three-digit CVC and any postal code.

Then verify that:

- the webhook request returned `200`;
- the payment changed from `PENDING` to `PAID`;
- the membership changed from `FROZEN` to `ACTIVE`;
- `stripe_subscription_id` was saved when auto-renew was enabled.

### Tests

The payment test module currently contains only the default placeholder. Payment behaviour
should be covered with mocked Stripe clients; automated tests must never call the real Stripe
API.

The main scenarios to cover are:

- one-time and subscription Checkout creation;
- reuse and expiration of pending sessions;
- successful initial payments and upgrades;
- repeated webhook delivery;
- successful and failed recurring payments;
- upgrade fee calculation;
- cancellation and subscription price changes;
- invalid webhook signatures.

### Where the code lives

| File | Purpose |
|---|---|
| `membership_service/models.py` | `Membership` model, status choices, properties (`was_frozen`, `frozen_days`), and database constraints |
| `membership_service/views.py` | `MembershipViewSet` handling purchase, freeze, resume, upgrade, list, and filters |
| `membership_service/serializers.py` | Serializers for reading, creating, freezing, and upgrading memberships |
| `membership_service/tests/` | Unit and integration tests covering the membership lifecycle and business rules |
| `payment_service/models.py` | Payment types, statuses and stored Stripe session data |
| `payment_service/services.py` | Checkout, product, payment, upgrade and subscription logic |
| `payment_service/views.py` | Stripe webhook validation and event routing |
| `payment_service/serializers.py` | Read-only payment API representation |
| `payment_service/urls.py` | Webhook URL |
| `membership_service/views.py` | Purchase, upgrade, freeze and cancel-renewal endpoints |
| `plan_service/views.py` | Stripe Product creation and archival |
| `plan_service/serializers.py` | Protection of Stripe-synchronized billing fields |
