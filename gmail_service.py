import os.path
import base64
from email.mime.text import MIMEText
from email.message import EmailMessage
import mimetypes # For potential attachments later
import pickle # Legacy, using json now for token

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config
from logger_config import logger

def get_gmail_service():
    """Authenticates and returns the Gmail API service client."""
    creds = None
    if os.path.exists(config.GMAIL_TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(config.GMAIL_TOKEN_FILE, config.GMAIL_SCOPES)
            logger.info(f"DEBUG: Loaded credentials from token file: {config.GMAIL_TOKEN_FILE}") ### ADD DEBUG ###
            # Attempt to check the associated project ID
            associated_project = getattr(creds, 'quota_project_id', 'N/A') ### ADD DEBUG ###
            logger.info(f"DEBUG: Project associated with token (quota_project_id): {associated_project}") ### ADD DEBUG ###

        except Exception as e:
            logger.warning(f"Could not load credentials from {config.GMAIL_TOKEN_FILE}: {e}. Will attempt re-auth.")
            creds = None

    if not creds or not creds.valid:
        logger.info("DEBUG: No valid token found or token needs refresh/re-auth.") ### ADD DEBUG ###
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("DEBUG: Refreshing expired token...") ### ADD DEBUG ###
                creds.refresh(Request())
                logger.info("Token refreshed successfully.")
                associated_project = getattr(creds, 'quota_project_id', 'N/A') ### ADD DEBUG ###
                logger.info(f"DEBUG: Project associated with refreshed token (quota_project_id): {associated_project}") ### ADD DEBUG ###
            except Exception as e:
                logger.warning(f"Failed to refresh token: {e}. Initiating full auth flow.")
                creds = None
        else:
            if not os.path.exists(config.GMAIL_CREDENTIALS_FILE):
                logger.error(f"Credentials file '{config.GMAIL_CREDENTIALS_FILE}' not found.")
                raise FileNotFoundError(f"Missing credentials file: {config.GMAIL_CREDENTIALS_FILE}")

            logger.info(f"DEBUG: Initiating OAuth flow using: {config.GMAIL_CREDENTIALS_FILE}") ### ADD DEBUG ###
            flow = InstalledAppFlow.from_client_secrets_file(
                config.GMAIL_CREDENTIALS_FILE, config.GMAIL_SCOPES)
            # Try to log project from credentials file itself
            try: ### ADD DEBUG ###
                client_config = flow.client_config ### ADD DEBUG ###
                proj_id = client_config.get('project_id', 'Not Found in client_config') ### ADD DEBUG ###
                logger.info(f"DEBUG: Project ID read from credentials.json (client_config): {proj_id}") ### ADD DEBUG ###
            except Exception as debug_e: ### ADD DEBUG ###
                logger.warning(f"DEBUG: Could not extract project_id from flow.client_config: {debug_e}") ### ADD DEBUG ###

            creds = flow.run_local_server(port=0)
            logger.info("OAuth flow completed. Credentials obtained.")
            associated_project = getattr(creds, 'quota_project_id', 'N/A') ### ADD DEBUG ###
            logger.info(f"DEBUG: Project associated with newly obtained creds (quota_project_id): {associated_project}") ### ADD DEBUG ###
            if not creds.quota_project_id and config.GOOGLE_PROJECT_ID: ### ADD FIX ###
                creds.quota_project_id = config.GOOGLE_PROJECT_ID ### ADD FIX ###
                logger.info(f"DEBUG: Explicitly set quota_project_id from config after OAuth: {creds.quota_project_id}") ### ADD FIX ###

            try:
                with open(config.GMAIL_TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
                logger.info(f"Credentials saved to {config.GMAIL_TOKEN_FILE}")
            except Exception as e:
                logger.error(f"Failed to save credentials to {config.GMAIL_TOKEN_FILE}: {e}")

    # Final check before building service
    if creds: ### ADD DEBUG ###
         final_associated_project = getattr(creds, 'quota_project_id', 'N/A') ### ADD DEBUG ###
         logger.info(f"DEBUG: FINAL check - Project associated with creds before build (quota_project_id): {final_associated_project}") ### ADD DEBUG ###
         # Compare with project ID from config (ensure config.py loads GOOGLE_PROJECT_ID)
         # if config.GOOGLE_PROJECT_ID and final_associated_project != config.GOOGLE_PROJECT_ID: ### ADD DEBUG ###
         #    logger.warning(f"DEBUG: *** MISMATCH WARNING *** Creds project ({final_associated_project}) != Config project ({config.GOOGLE_PROJECT_ID})") ### ADD DEBUG ###
    else: ### ADD DEBUG ###
         logger.error("DEBUG: FINAL check - Credentials object is None before building service!") ### ADD DEBUG ###

    try:
        service = build('gmail', 'v1', credentials=creds)
        logger.info("Gmail service client created.")
        return service
    except HttpError as error:
        logger.error(f'An error occurred building Gmail service: {error}')
        raise
    except Exception as e:
        logger.error(f'An unexpected error occurred building Gmail service: {e}', exc_info=True)
        raise


def list_unread_emails(service):
    """Lists unread emails, optionally filtered by a label."""
    query = 'is:unread'
    if config.GMAIL_WATCH_LABEL_ID:
        query += f' label:{config.GMAIL_WATCH_LABEL_ID} in:inbox'
    else:
        query += ' in:inbox' # Default to inbox if no label specified

    try:
        logger.debug(f"Listing emails with query: '{query}'")
        response = service.users().messages().list(
            userId=config.GMAIL_USER_ID,
            q=query
        ).execute()
        messages = response.get('messages', [])
        logger.info(f"Found {len(messages)} unread email(s) matching criteria.")
        return messages # List of dicts [{'id': '...', 'threadId': '...'}]
    except HttpError as error:
        logger.error(f'An error occurred listing emails: {error}')
        return []
    except Exception as e:
        logger.error(f'An unexpected error occurred listing emails: {e}', exc_info=True)
        return []


def get_email_details(service, message_id: str) -> dict | None:
    """Gets detailed information (sender, subject, body, headers) for a specific email."""
    try:
        logger.debug(f"Fetching details for message ID: {message_id}")
        message = service.users().messages().get(
            userId=config.GMAIL_USER_ID,
            id=message_id,
            format='full' # Get headers and full payload
        ).execute()

        payload = message.get('payload', {})
        headers = payload.get('headers', [])
        parts = payload.get('parts')

        email_data = {
            'message_id': message_id,
            'thread_id': message.get('threadId'),
            'sender': None,
            'subject': None,
            'body': None,
            'message_id_header': None # For replying
        }

        # Extract headers
        for header in headers:
            name = header.get('name', '').lower()
            if name == 'from':
                email_data['sender'] = header.get('value')
            elif name == 'subject':
                email_data['subject'] = header.get('value')
            elif name == 'message-id':
                 email_data['message_id_header'] = header.get('value') # Crucial for threading replies

        # Extract body (prefer plain text)
        body_plain = None
        body_html = None

        if parts:
            for part in parts:
                mime_type = part.get('mimeType', '')
                part_body = part.get('body', {}).get('data')
                if part_body:
                    decoded_body = base64.urlsafe_b64decode(part_body).decode('utf-8', errors='replace')
                    if mime_type == 'text/plain':
                        body_plain = decoded_body
                        break # Prefer plain text, stop searching
                    elif mime_type == 'text/html':
                        body_html = decoded_body # Keep html as fallback

            # If no plain text part found, check nested parts (common in multipart/alternative)
            if not body_plain:
                 for part in parts:
                      if part.get('parts'):
                           for sub_part in part.get('parts'):
                                mime_type = sub_part.get('mimeType', '')
                                sub_part_body = sub_part.get('body', {}).get('data')
                                if sub_part_body:
                                    decoded_body = base64.urlsafe_b64decode(sub_part_body).decode('utf-8', errors='replace')
                                    if mime_type == 'text/plain':
                                        body_plain = decoded_body
                                        break
                                    elif mime_type == 'text/html' and not body_html: # Only take first html if no plain
                                        body_html = decoded_body
                           if body_plain: break # Found plain in subpart

        else: # No parts, check top-level body if exists (rare for text emails)
            top_body_data = payload.get('body', {}).get('data')
            if top_body_data:
                 # Assume plain text if no mimeType specified at top level? Risky.
                 # Better to rely on parts structure. Let's log if this happens.
                 logger.warning(f"Email {message_id} has body data but no 'parts'. Structure unexpected.")
                 # Attempt decode if mimeType hints text
                 if 'text/plain' in payload.get('mimeType',''):
                     body_plain = base64.urlsafe_b64decode(top_body_data).decode('utf-8', errors='replace')

        # Assign the best available body
        email_data['body'] = body_plain if body_plain else body_html
        if not email_data['body']:
            logger.warning(f"Could not extract body for message ID: {message_id}")
            email_data['body'] = "" # Ensure body is not None

        # Basic cleanup (optional, can be improved)
        # email_data['body'] = clean_email_body(email_data['body']) # Implement if needed

        logger.info(f"Successfully parsed email details for ID: {message_id}")
        return email_data

    except HttpError as error:
        logger.error(f'An error occurred getting email details for {message_id}: {error}')
        return None
    except base64.BinasciiError as b64_error:
         logger.error(f"Base64 decoding error for message {message_id}: {b64_error}", exc_info=True)
         return None
    except Exception as e:
        logger.error(f'An unexpected error occurred getting email details for {message_id}: {e}', exc_info=True)
        return None


def send_reply(service, original_email_data: dict, reply_body: str):
    """Sends a reply email using the Gmail API, ensuring proper threading."""
    if not original_email_data.get('sender'):
        logger.error("Cannot send reply: Original sender not found.")
        return False
    if not original_email_data.get('message_id_header'):
        logger.error("Cannot send reply: Original Message-ID header not found for threading.")
        # Could potentially still send without threading, but it's bad practice.
        return False
    if not original_email_data.get('thread_id'):
        logger.warning("Original thread ID not found. Reply might not thread correctly.")
        # Continue anyway, but log it.

    try:
        # Create the MIME message
        message = EmailMessage()
        message.set_content(reply_body)
        
        # Properly format the To header with email address validation
        sender_email = original_email_data['sender']
        # Extract email from "Name <email@domain.com>" format if needed
        if '<' in sender_email and '>' in sender_email:
            sender_email = sender_email[sender_email.find('<')+1:sender_email.find('>')]
        message['to'] = sender_email
        
        # Set other headers
        message['subject'] = f"Re: {original_email_data.get('subject', 'Your Inquiry')}"
        message['In-Reply-To'] = original_email_data['message_id_header']
        message['References'] = original_email_data['message_id_header']

        # Encode the message in base64url format
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        create_message = {
            'raw': encoded_message,
            'threadId': original_email_data.get('thread_id')
        }

        logger.info(f"Sending reply to {sender_email} regarding thread {original_email_data.get('thread_id')}")
        sent_message = service.users().messages().send(
            userId=config.GMAIL_USER_ID,
            body=create_message
        ).execute()
        logger.info(f"Reply sent successfully. New Message ID: {sent_message['id']}")
        return True

    except HttpError as error:
        logger.error(f'An error occurred sending reply: {error}')
        return False
    except Exception as e:
        logger.error(f'An unexpected error occurred sending reply: {e}', exc_info=True)
        return False


def mark_as_read(service, message_id: str):
    """Marks an email as read by removing the UNREAD label."""
    try:
        logger.debug(f"Marking message ID {message_id} as read.")
        service.users().messages().modify(
            userId=config.GMAIL_USER_ID,
            id=message_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()
        logger.info(f"Message ID {message_id} marked as read.")
        return True
    except HttpError as error:
        logger.error(f'An error occurred marking {message_id} as read: {error}')
        return False
    except Exception as e:
         logger.error(f'Unexpected error marking {message_id} as read: {e}', exc_info=True)
         return False

# --- Optional: Pub/Sub Watcher Setup (More complex, requires cloud setup) ---
# def watch_mailbox(service):
#     request = {
#         'labelIds': ['INBOX'], # Or your specific label
#         'topicName': config.GMAIL_WATCH_TOPIC_NAME
#     }
#     if config.GMAIL_WATCH_LABEL_ID:
#          request['labelIds'] = [config.GMAIL_WATCH_LABEL_ID]

#     try:
#          response = service.users().watch(userId=config.GMAIL_USER_ID, body=request).execute()
#          logger.info(f"Gmail watch request successful: {response}")
#          # You need an HTTPS endpoint to receive notifications from Pub/Sub now
#          return response
#     except HttpError as error:
#          logger.error(f"Failed to set up Gmail watch: {error}")
#          return None
