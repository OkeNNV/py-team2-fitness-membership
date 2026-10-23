import logging

import requests
from django.conf import settings

TIMEOUT = 10
MESSAGE_MAX_LENGTH = 4096
URL = "https://api.telegram.org/bot{bot_token}/sendMessage"

logger = logging.getLogger(__name__)


def send_telegram_message(message: str) -> bool:
    """Send an HTML-formatted message to the staff Telegram chat.

    The message is sent with parse_mode=HTML, so it must already be valid
    Telegram HTML with all user-provided values escaped (the builders in
    notification_service.messages do this). The bot token and chat id are
    read from settings (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID). Messages
    longer than MESSAGE_MAX_LENGTH are truncated with a trailing "...", which
    may cut an HTML tag and make Telegram reject the message. This function
    never raises: every failure is logged and reported through the return
    value, and the bot token is never written to the logs.

    Args:
        message (str): HTML-formatted text to send, with user-provided
            values already escaped.

    Returns:
        bool: True if Telegram accepted the message, False otherwise
            (not configured, empty message, API error or network error).
    """
    chat_id = settings.TELEGRAM_CHAT_ID
    bot_token = settings.TELEGRAM_BOT_TOKEN

    if not chat_id or not bot_token:
        logger.warning(
            "Telegram notification skipped: "
            "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not configured"
        )
        return False

    if not message.strip():
        logger.warning("Telegram notification skipped: message is empty")
        return False

    if len(message) > MESSAGE_MAX_LENGTH:
        logger.warning(
            "Telegram message is too long (%s chars), truncated to %s chars",
            len(message),
            MESSAGE_MAX_LENGTH,
        )
        message = message[: MESSAGE_MAX_LENGTH - 3] + "..."

    url = URL.format(bot_token=bot_token)
    request_body = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        response = requests.post(
            url=url,
            data=request_body,
            timeout=TIMEOUT,
        ).json()

        if response.get("ok"):
            logger.debug("Telegram notification sent successfully")
            return True
        logger.warning(
            "Telegram API rejected the message: error_code=%s, description=%s",
            response.get("error_code"),
            response.get("description"),
        )
        return False

    except requests.exceptions.Timeout:
        logger.error("Telegram request timed out after %s seconds", TIMEOUT)
        return False
    except requests.exceptions.JSONDecodeError:
        logger.error("Telegram returned an invalid (non-JSON) response")
        return False
    except requests.exceptions.RequestException as exception:
        logger.error("Telegram request failed: %s", type(exception).__name__)
        return False
