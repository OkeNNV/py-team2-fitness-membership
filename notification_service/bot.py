"""Telegram bot that answers the /start and /chatid commands.

The bot is only needed to find out the chat id for TELEGRAM_CHAT_ID.
Sending notifications to the staff chat does not depend on it: the Celery
task talks to Telegram directly.

Run it with ``python manage.py run_telegram_bot``. Only one process can poll
Telegram for the same bot token at a time.
"""

import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

logger = logging.getLogger(__name__)

START_TEXT = "Hello! I am the Fitness Club bot.\nSend /chatid to get the id of this chat."

router = Router()


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Greet the user and mention the /chatid command."""
    await message.answer(START_TEXT)


@router.message(Command("chatid"))
async def handle_chat_id(message: Message) -> None:
    """Reply with the id of the chat where the command was sent."""
    await message.answer(f"Chat ID: <code>{message.chat.id}</code>")


def build_dispatcher() -> Dispatcher:
    """Create a dispatcher with all bot handlers attached."""
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


async def run_bot(token: str) -> None:
    """Run the bot with long polling until it is stopped.

    Args:
        token (str): Telegram bot token. It is passed in by the caller, this
            module does not read settings or environment variables.
    """
    dispatcher = build_dispatcher()
    default = DefaultBotProperties(parse_mode=ParseMode.HTML)

    async with Bot(token=token, default=default) as bot:
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            drop_pending_updates=True,
        )
