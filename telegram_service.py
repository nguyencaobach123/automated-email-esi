import telegram
import config
from logger_config import logger
import asyncio # python-telegram-bot v20+ is async
import urllib.parse
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

async def forward_to_support(email_data: dict):
    """
    Forwards summarized email details to the designated Telegram support chat.

    Args:
        email_data: Dictionary containing 'sender', 'subject', 'body', 'message_id'.
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram forwarding skipped: Token or Chat ID not configured.")
        return False

    bot = telegram.Bot(token=config.TELEGRAM_BOT_TOKEN)
    sender = email_data.get('sender', 'Unknown Sender')
    subject = email_data.get('subject', 'No Subject')
    body_preview = email_data.get('body', 'No Body')[:1000] # Preview length
    message_id = email_data.get('message_id', 'N/A')

    # Extract the email address from the sender field
    sender_email = sender.split('<')[-1].strip('>') if '<' in sender else sender

    # Construct the Gmail link using the thread ID
    gmail_link = f"https://mail.google.com/mail/u/0/#inbox/{email_data.get('thread_id', 'N/A')}"

    # Update the message text to include the Gmail link
    message_text = (
        f"🆘 *Manual Support Needed*\n\n"
        f"*From:* {sender}\n"
        f"*Subject:* {subject}\n"
        f"*Gmail Msg ID:* {message_id}\n\n"
        f"*Content Preview:*\n"
        f"{body_preview}...\n\n"
        f"Reply to this email: {sender_email}\n"
        f"[View in Gmail]({gmail_link})"
    )

    # Remove the inline keyboard since it's no longer needed
    reply_markup = None

    try:
        logger.info(f"Forwarding email (ID: {message_id}) to Telegram chat {config.TELEGRAM_CHAT_ID}")
        await bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text=message_text,
            parse_mode=telegram.constants.ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        logger.info(f"Successfully forwarded email (ID: {message_id}) to Telegram.")
        return True
    except telegram.error.TelegramError as e:
        logger.error(f"Failed to send message to Telegram: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during Telegram forwarding: {e}", exc_info=True)
        return False

# Helper to run async function from sync code if needed in main loop
def run_async_forward(email_data: dict):
     """Runs the async forward_to_support function."""
     try:
         # Get the current event loop or create a new one if needed
         loop = asyncio.get_event_loop_policy().get_event_loop()
         # Schedule the coroutine and wait for it to complete
         result = loop.run_until_complete(forward_to_support(email_data))
         return result
     except RuntimeError as e:
         # Handle cases where there's no running loop or policy issues
         logger.warning(f"Could not get asyncio event loop ({e}). Trying asyncio.run().")
         try:
             # asyncio.run creates a new event loop
             result = asyncio.run(forward_to_support(email_data))
             return result
         except Exception as run_e:
             logger.error(f"Failed to run async forward using asyncio.run: {run_e}", exc_info=True)
             return False
     except Exception as e:
         logger.error(f"General error running async Telegram forward: {e}", exc_info=True)
         return False
