import time
import config # Ensure config is loaded early
from logger_config import setup_logging, logger
import gmail_service
import processing_service
import base64
import os
from google.oauth2 import service_account

# Import Pub/Sub client library
from google.cloud import pubsub_v1
from google.api_core import exceptions as google_api_exceptions

# --- Setup ---
setup_logging()
SERVICE_ACCOUNT_KEY_FILE = 'gen-lang-client-0318010829-fdece7664895.json'
# Pub/Sub settings
PUBSUB_TIMEOUT_SECONDS = 60.0

def main_pubsub_listener():
    """Main loop listening to Pub/Sub subscription for Gmail notifications."""
    logger.info("Starting Email Automation Service (Pub/Sub Listener)...")

    # --- Initialize Gmail Service ---
    try:
        gmail_client = gmail_service.get_gmail_service()
        logger.info("Gmail service client obtained successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize Gmail service: {e}. Exiting.", exc_info=True)
        return

    # --- Initialize Pub/Sub Subscriber Client ---
    try:
        # Check if the key file exists
        if not os.path.exists(SERVICE_ACCOUNT_KEY_FILE):
            logger.critical(f"Service account key file not found at: {SERVICE_ACCOUNT_KEY_FILE}")
            raise FileNotFoundError(f"Missing service account key: {SERVICE_ACCOUNT_KEY_FILE}")

        # Create credentials explicitly from the file
        pubsub_credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_KEY_FILE,
            scopes=["https://www.googleapis.com/auth/pubsub"], # Scope needed for Pub/Sub
        )

        # Pass the explicit credentials to the client
        subscriber_client = pubsub_v1.SubscriberClient(credentials=pubsub_credentials)

        subscription_path = config.GMAIL_PUBSUB_SUBSCRIPTION_PATH
        logger.info(f"Pub/Sub subscriber client created using key file for subscription: {subscription_path}")
    except FileNotFoundError as fnf_err:
         logger.critical(f"Failed to initialize Pub/Sub: {fnf_err}", exc_info=True)
         return # Exit if key file is missing
    except Exception as e:
        logger.critical(f"Failed to create Pub/Sub subscriber client using key file: {e}. Exiting.", exc_info=True)
        return

    # --- Define the Callback Function ---
    def process_message_callback(message: pubsub_v1.subscriber.message.Message) -> None:
        """Callback executed when a message is pulled from Pub/Sub."""
        message_id_pubsub = message.message_id
        logger.info(f"Received Pub/Sub message ID: {message_id_pubsub}")
        try:
            # Decode data (usually base64)
            data_str = message.data.decode("utf-8")
            logger.debug(f"Message Data: {data_str}")

            # Call the processing logic
            processing_service.process_pubsub_message(data_str, gmail_client)

            # Acknowledge the message so Pub/Sub doesn't redeliver it
            logger.debug(f"Acknowledging Pub/Sub message {message_id_pubsub}")
            message.ack()
            logger.info(f"Successfully processed and acknowledged Pub/Sub message {message_id_pubsub}")

        except Exception as e:
            logger.error(f"Error processing Pub/Sub message {message_id_pubsub}: {e}", exc_info=True)
            # Do NOT acknowledge the message on error, let Pub/Sub retry
            message.nack()
            logger.warning(f"Nacked Pub/Sub message {message_id_pubsub} due to processing error.")


    # --- Start the Subscription Pull ---
    streaming_pull_future = subscriber_client.subscribe(
        subscription_path, callback=process_message_callback
    )
    logger.info(f"Listening for messages on {subscription_path}...")

    # --- Keep the Main Thread Alive (until interrupted) ---
    try:
        while True:
             time.sleep(PUBSUB_TIMEOUT_SECONDS) 

    except KeyboardInterrupt:
        logger.info("Shutdown requested. Stopping Pub/Sub listener...")
        streaming_pull_future.cancel()  # Signal the background thread to stop
        streaming_pull_future.result(timeout=30) # Wait for cancellation to complete
        logger.info("Pub/Sub listener stopped.")
    except google_api_exceptions.GoogleAPICallError as api_error:
         logger.critical(f"Pub/Sub API Error: {api_error}. Check permissions/subscription path.", exc_info=True)
         streaming_pull_future.cancel()
         streaming_pull_future.result(timeout=30)
    except Exception as e:
        logger.critical(f"Unexpected error in main listener loop: {e}", exc_info=True)
        streaming_pull_future.cancel() # Attempt graceful shutdown
        streaming_pull_future.result(timeout=30) # Wait for shutdown

    finally:
        subscriber_client.close()
        logger.info("Pub/Sub subscriber client closed.")


if __name__ == '__main__':

    # --- Start the main listener ---
    main_pubsub_listener()
    logger.info("Email Automation Service stopped.")