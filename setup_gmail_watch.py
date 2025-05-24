import config # Load config to get topic name etc.
from logger_config import setup_logging, logger
import gmail_service # Reuse the authentication and service builder
import sys
import os

def check_venv():
    if sys.prefix == sys.base_prefix:
        logger.warning("Not running in a virtual environment! Please activate it first:")
        logger.warning("Windows: .venv\\Scripts\\activate")
        logger.warning("Unix: source .venv/bin/activate")
        sys.exit(1)

check_venv()

# --- Setup ---
setup_logging()

# --- Configuration from .env (via config.py) ---
# Make sure your .env has the correct topic name configured if needed
# Example: GMAIL_PUBSUB_TOPIC_PATH='projects/your-project-id/topics/your-gmail-topic-name'
# Load it in config.py if not already done:
# GMAIL_PUBSUB_TOPIC_PATH = os.getenv('GMAIL_PUBSUB_TOPIC_PATH')
# if not GMAIL_PUBSUB_TOPIC_PATH:
#     raise ValueError("Missing GMAIL_PUBSUB_TOPIC_PATH environment variable for watch setup")

# Hardcode or load from config
TARGET_USER_ID = 'me'
# Retrieve the correctly formatted topic name from config
# Ensure config.py loads 'GMAIL_PUBSUB_TOPIC_PATH' from .env
TARGET_TOPIC_NAME = config.GMAIL_PUBSUB_TOPIC_PATH
TARGET_LABELS = ['INBOX'] # Or ['YOUR_LABEL_ID'] e.g., ['Label_12345']

def setup_watch():
    """Calls the users.watch method to set up Gmail push notifications."""
    logger.info("Attempting to set up Gmail watch...")
    try:
        gmail_client = gmail_service.get_gmail_service()
        logger.info("Gmail service client obtained.")

        request_body = {
            'labelIds': TARGET_LABELS,
            'topicName': TARGET_TOPIC_NAME
        }

        logger.info(f"Watch Request Body: {request_body}")

        watch_response = gmail_client.users().watch(
            userId=TARGET_USER_ID,
            body=request_body
        ).execute()

        logger.info("Successfully called users.watch API.")
        logger.info(f"Watch Response: {watch_response}")
        logger.info(f"Notifications will be sent to {TARGET_TOPIC_NAME}")
        logger.info(f"Watch expires around: {watch_response.get('expiration')}")
        logger.warning("Remember to re-run this setup before the expiration date!")

    except gmail_service.HttpError as error:
        logger.error(f'An error occurred setting up Gmail watch: {error}', exc_info=True)
        logger.error(f'Response content: {error.content}') # Log detailed error
        logger.error("Check: Topic name correct? Permissions granted to Gmail SA on topic? API enabled?")
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {e}", exc_info=True)

if __name__ == '__main__':
    # Make sure the required config is present
    if not TARGET_TOPIC_NAME:
         logger.critical("Error: GMAIL_PUBSUB_TOPIC_PATH is not defined in config/.env")
    else:
        setup_watch()