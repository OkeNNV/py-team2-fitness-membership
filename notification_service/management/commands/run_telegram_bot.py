"""Django command that runs the Telegram bot."""

import asyncio
import logging

from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.utils.token import TokenValidationError
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from notification_service.bot import run_bot


class Command(BaseCommand):
    """Run the Telegram bot (long polling) that answers /start and /chatid."""

    help = "Run the Telegram bot that answers /start and /chatid."  # noqa: VNE003

    def handle(self, *args, **options) -> None:
        """Start the bot and block until it is stopped."""
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        if not token:
            raise CommandError("TELEGRAM_BOT_TOKEN is not configured")

        logging.basicConfig(level=logging.INFO)
        self.stdout.write("Telegram bot is starting, press Ctrl+C to stop")

        try:
            asyncio.run(run_bot(str(token)))
        except KeyboardInterrupt:
            self.stdout.write("Telegram bot stopped")
        except TokenValidationError:
            raise CommandError("TELEGRAM_BOT_TOKEN has an invalid format") from None
        except TelegramUnauthorizedError:
            raise CommandError("Telegram rejected TELEGRAM_BOT_TOKEN") from None
