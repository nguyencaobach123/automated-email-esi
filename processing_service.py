import config
import gemini_service
import gmail_service
import telegram_service
import ebay_service # Import the new ebay_service
from logger_config import logger
import json # To parse potential message data from Pub/Sub

def process_pubsub_message(pubsub_message_data: str, gmail_service_client):
    """
    Processes a message received from the Pub/Sub subscription triggered by Gmail.

    Args:
        pubsub_message_data: The raw data string from the Pub/Sub message.
        gmail_service_client: The authenticated Gmail API service client.
    """
    try:
        # Decode the message data (usually base64 encoded JSON)
        message_content = json.loads(pubsub_message_data)
        email_address = message_content.get('emailAddress')
        history_id = message_content.get('historyId')

        logger.info(f"Received notification for {email_address} (History ID: {history_id}). Fetching recent unread.")

        unread_messages = gmail_service.list_unread_emails(gmail_service_client)

        if not unread_messages:
            logger.info("No unread messages found after notification trigger (might be already processed or not matching criteria).")
            return

        # --- Process the *first* unread message found.
        # --- A robust system might process all or handle potential races.
        message_summary = unread_messages[0]
        message_id = message_summary.get('id')
        if not message_id:
            logger.warning("Found message summary without ID after notification, skipping.")
            return

        logger.info(f"--- Triggered processing for Message ID: {message_id} ---")

        # --- Get Full Email Details ---
        email_details = gmail_service.get_email_details(gmail_service_client, message_id)

        if not email_details:
            logger.error(f"Failed to retrieve details for message {message_id} after notification. Skipping.")
            # gmail_service.mark_as_read(gmail_service_client, message_id)
            return

        # --- Simplified Processing Logic ---
        subject = email_details.get('subject', '')
        body = email_details.get('body', '')

        if not body:
            logger.warning(f"Email {message_id} has no body content. Marking as read.")
            gmail_service.mark_as_read(gmail_service_client, message_id)
            logger.info(f"--- Finished processing (skipped empty body) for email ID: {message_id} ---")
            return

        # 1. Classify Email
        classification = gemini_service.classify_email(subject, body)

        if classification == "SPAM":
            logger.info(f"Email {message_id} classified as SPAM. Marking read.")
            gmail_service.mark_as_read(gmail_service_client, message_id)

        elif classification == "PROCESS":
            # Generate eBay search parameters using Gemini
            search_params = gemini_service.generate_ebay_search_params(body)

            if not search_params or "q" not in search_params:
                 logger.warning(f"Gemini failed to generate valid search parameters or missing 'q' for email {message_id}. Forwarding.")
                 # Forward to Telegram as fallback if parameters are not generated or missing 'q'
                 forwarded = telegram_service.run_async_forward(email_details)
                 if forwarded:
                     gmail_service.mark_as_read(gmail_service_client, message_id) # Mark read if forwarded
                 else:
                     logger.error(f"Failed to forward email {message_id} to Telegram after failed parameter generation.")
                 return

            # --- Perform eBay Search ---
            logger.info(f"Performing eBay search with parameters: {search_params}")
            relevant_items = ebay_service.search_ebay_items(search_params) # Pass the dictionary of parameters

            if relevant_items:
                logger.info(f"Found {len(relevant_items)} relevant items from eBay.")
                for i, item in enumerate(relevant_items):
                    # Access item details using dictionary keys from the new ebay_service
                    title = item.get('title', 'N/A')
                    price = item.get('price', 'N/A')
                    currency = item.get('currency', 'N/A')
                    url = item.get('itemWebUrl', 'N/A')
                    logger.info(f"Relevant item {i+1}: Title: {title}, Price: {price} {currency}, URL: {url}")

                # Evaluate if the retrieved items are relevant and sufficient for a reply
                is_items_relevant_and_sufficient = gemini_service.evaluate_knowledge_relevance(
                    original_body=body,
                    relevant_knowledge=relevant_items # Pass eBay items here
                )

                if is_items_relevant_and_sufficient:
                    # Generate response using the eBay items
                    response_text = gemini_service.generate_response(
                        original_subject=subject,
                        original_body=body,
                        relevant_knowledge=relevant_items # Pass eBay items here
                    )

                    if response_text:
                        success = gmail_service.send_reply(
                            gmail_service_client,
                            email_details,
                            response_text
                        )

                        if success:
                            gmail_service.mark_as_read(gmail_service_client, message_id)
                            logger.info(f"Email {message_id} replied to with relevant eBay items.")
                            return
                else:
                    # Forward to Telegram if relevant items found but not deemed sufficient
                    forwarded = telegram_service.run_async_forward(email_details)
                    if forwarded:
                        gmail_service.mark_as_read(gmail_service_client, message_id)
                        logger.info(f"Email {message_id} forwarded to Telegram due to insufficient relevant eBay items.")
                        return
            else:
                # Forward to Telegram when no relevant items are found
                # Use search_params.get('q', 'N/A') to log the actual query
                logger.info(f"No relevant items found on eBay for query: '{search_params.get('q', 'N/A')}'. Forwarding email.")
                forwarded = telegram_service.run_async_forward(email_details)
                if forwarded:
                    gmail_service.mark_as_read(gmail_service_client, message_id)
                    logger.info(f"Email {message_id} forwarded to Telegram due to no relevant eBay items found.")
                    return

        else: # classification is None or unexpected
            logger.error(f"Could not classify email {message_id} or classification failed. Forwarding for manual review.")
            # Forward to Telegram as fallback
            forwarded = telegram_service.run_async_forward(email_details)
            if forwarded:
                gmail_service.mark_as_read(gmail_service_client, message_id) # Mark read if forwarded
            else:
                logger.error(f"Failed to forward unclassified email {message_id} to Telegram.")

        logger.info(f"--- Finished processing for email ID: {message_id} ---")

    except json.JSONDecodeError:
        logger.error(f"Failed to decode Pub/Sub message data: {pubsub_message_data}")
    except Exception as e:
        logger.error(f"Error processing Pub/Sub message: {e}", exc_info=True)
