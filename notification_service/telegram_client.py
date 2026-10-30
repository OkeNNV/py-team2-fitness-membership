"""Sending messages to the staff Telegram chat through aiogram.

Two entry points:

* ``send_telegram_message(message) -> bool`` is the simple public function.
  It never raises: every failure is logged and reported as ``False``.
* ``send_telegram_message_or_raise(message) -> None`` is for Celery tasks.
  It raises ``TemporaryTelegramError`` (worth retrying, may carry
  ``retry_after``) or ``PermanentTelegramError`` (retrying is pointless).

aiogram is async, so the sending is wrapped in ``asyncio.run``. It must be
called from synchronous code (a Celery task, a shell, a management command),
never from inside a running event loop (for example an async view).

The bot token is never written to the logs or to exception messages.
"""

import asyncio
import html
import logging
import re

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramMigrateToChat,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.utils.token import TokenValidationError
from django.conf import settings

from notification_service.exceptions import (
    PermanentTelegramError,
    TelegramSendError,
    TemporaryTelegramError,
)

DEFAULT_TIMEOUT = 10.0
MESSAGE_MAX_LENGTH = 4096

# Matches an HTML tag, including a tag that was cut in half at the very end.
_TAG_RE = re.compile(r"<[^>]*(?:>|$)")

logger = logging.getLogger(__name__)


def _get_timeout() -> float:
    """Return the total HTTP timeout in seconds from settings.

    Reads TELEGRAM_TIMEOUT and falls back to DEFAULT_TIMEOUT when the setting
    is missing, not a number or not positive.
    """
    try:
        timeout = float(getattr(settings, "TELEGRAM_TIMEOUT", DEFAULT_TIMEOUT))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT
    return timeout if timeout > 0 else DEFAULT_TIMEOUT


def _truncate(text: str) -> str:
    """Cut the text to MESSAGE_MAX_LENGTH and end it with "..."."""
    if len(text) <= MESSAGE_MAX_LENGTH:
        return text
    logger.warning(
        "Telegram message is too long (%s chars), truncated to %s chars",
        len(text),
        MESSAGE_MAX_LENGTH,
    )
    return text[: MESSAGE_MAX_LENGTH - 3] + "..."


def _to_plain_text(message: str) -> str:
    """Turn an HTML message into plain text: drop tags, unescape entities."""
    return html.unescape(_TAG_RE.sub("", message))


def _is_markup_error(exc: TelegramBadRequest) -> bool:
    """Return True when Telegram rejected the message because of bad HTML."""
    return "can't parse entities" in (getattr(exc, "message", "") or "").lower()


async def _deliver(token: str, chat_id: str, message: str, timeout: float) -> None:
    """Send the message; retry once as plain text if the HTML is rejected.

    A new Bot (and HTTP session) is created per call and always closed, so it
    is safe to use from different Celery processes and event loops.
    """
    session = AiohttpSession(timeout=timeout)
    async with Bot(token=token, session=session) as bot:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=_truncate(message),
                parse_mode=ParseMode.HTML,
            )
        except TelegramBadRequest as exc:
            if not _is_markup_error(exc):
                raise
            logger.warning(
                "Telegram rejected the HTML markup, resending as plain text: %s",
                getattr(exc, "message", ""),
            )
            await bot.send_message(
                chat_id=chat_id,
                text=_truncate(_to_plain_text(message)),
                parse_mode=None,
            )


def _classify(exc: Exception) -> TelegramSendError:
    """Log the failure and convert it to a temporary or permanent error.

    Only the exception type and Telegram's own description are logged, never
    str(exception) of network errors, because it may contain the bot token.
    """
    if isinstance(exc, TelegramRetryAfter):
        logger.warning("Telegram rate limit hit, retry after %s seconds", exc.retry_after)
        return TemporaryTelegramError("Telegram rate limit hit", retry_after=exc.retry_after)

    if isinstance(exc, TelegramNetworkError):
        logger.error("Telegram network error or timeout: %s", type(exc).__name__)
        return TemporaryTelegramError("Telegram network error or timeout")

    if isinstance(exc, TelegramServerError):
        logger.error("Telegram server error: %s", type(exc).__name__)
        return TemporaryTelegramError("Telegram server error")

    if isinstance(exc, TelegramMigrateToChat):
        logger.error(
            "Telegram chat was upgraded to a supergroup, set TELEGRAM_CHAT_ID to %s",
            exc.migrate_to_chat_id,
        )
        return PermanentTelegramError("Telegram chat id has changed")

    if isinstance(exc, TelegramAPIError):
        logger.error(
            "Telegram API rejected the message: %s: %s",
            type(exc).__name__,
            getattr(exc, "message", ""),
        )
        return PermanentTelegramError(f"Telegram API error: {type(exc).__name__}")

    if isinstance(exc, TokenValidationError):
        logger.error("TELEGRAM_BOT_TOKEN has an invalid format")
        return PermanentTelegramError("Telegram bot token is invalid")

    logger.error("Unexpected error while sending Telegram message: %s", type(exc).__name__)
    return PermanentTelegramError(f"Unexpected error: {type(exc).__name__}")


def send_telegram_message_or_raise(message: str) -> None:
    """Send an HTML message to the staff Telegram chat or raise.

    Meant for Celery tasks that decide about retries themselves. The message
    must be valid Telegram HTML with all user values escaped (the builders in
    notification_service.messages do this). If Telegram rejects the markup,
    the text is resent once without formatting.

    Args:
        message (str): HTML-formatted text to send.

    Raises:
        TemporaryTelegramError: Rate limit, network error, timeout or Telegram
            5xx. Check ``retry_after`` for the wait Telegram asked for.
        PermanentTelegramError: Not configured, empty message, called from a
            running event loop, invalid token or any other error that a retry
            cannot fix.
    """
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning(
            "Telegram notification skipped: "
            "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not configured",
        )
        raise PermanentTelegramError("Telegram is not configured")

    if not message.strip():
        logger.warning("Telegram notification skipped: message is empty")
        raise PermanentTelegramError("Message is empty")

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass  # no running loop: this is the normal case
    else:
        logger.error(
            "Telegram message not sent: called from a running event loop, "
            "use it only from sync code such as a Celery task",
        )
        raise PermanentTelegramError("Called from a running event loop")

    try:
        asyncio.run(_deliver(str(token), str(chat_id), message, _get_timeout()))
    except Exception as exc:
        # "from None" drops the original exception from the traceback,
        # because its text may contain the bot token.
        raise _classify(exc) from None

    logger.debug("Telegram notification sent successfully")


def send_telegram_message(message: str) -> bool:
    """Send an HTML message to the staff Telegram chat, never raising.

    Args:
        message (str): HTML-formatted text to send, with user-provided
            values already escaped.

    Returns:
        bool: True if Telegram accepted the message, False otherwise.
    """
    try:
        send_telegram_message_or_raise(message)
    except TelegramSendError:
        return False  # already logged
    except Exception as exc:
        logger.error("Unexpected error in send_telegram_message: %s", type(exc).__name__)
        return False
    return True
