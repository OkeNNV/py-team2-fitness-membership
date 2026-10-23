class TelegramSendError(Exception):
    """Base class for all errors raised when sending a Telegram message.

    Messages of these exceptions never contain the bot token.
    """


class TemporaryTelegramError(TelegramSendError):
    """A failure that may go away on its own, so a retry makes sense.

    Examples: rate limit (429), network error, timeout, Telegram 5xx.

    Attributes:
        retry_after (float | None): Seconds Telegram asked us to wait before
            the next attempt, or None when Telegram did not say.
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class PermanentTelegramError(TelegramSendError):
    """A failure that a retry cannot fix.

    Examples: token or chat id not configured, invalid token, bot was kicked
    from the chat, bad request, empty message.
    """
