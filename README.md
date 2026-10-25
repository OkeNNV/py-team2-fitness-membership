# py-team2-fitness-membership

## Telegram notifications

Club staff get short Telegram messages about important events: a new membership, a freeze,
a successful payment, an expired membership and upcoming expirations. Messages are sent
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
| Payment received | a payment becomes `PAID` for the first time | `notify_payment_success(payment)` | `PaymentService.mark_payment_as_paid_and_membership_as_active`, `payment_service/services.py` | ⏳ pending |
| Membership expired | the daily job marks a membership as `EXPIRED` | `notify_membership_expired(membership)` | `mark_expired_memberships`, `membership_service/tasks.py` | ✅ |
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
💰 Payment received

Payment ID: #31
Member: Anna Kovalenko (anna.kovalenko@example.com)
Type: 🛒 Membership purchase
Amount: 49.99 USD
Plan: Gold (gold-30)
Membership ID: #12
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
6. To add a new event: add it to `NotificationEvent` and write a builder in
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