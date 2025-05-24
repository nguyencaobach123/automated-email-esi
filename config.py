import os
from dotenv import load_dotenv

load_dotenv(override=True)

# Gmail
GMAIL_CREDENTIALS_FILE = 'credentials.json'
GMAIL_TOKEN_FILE = os.getenv('GMAIL_TOKEN_FILE', 'token.json')
GMAIL_SCOPES = [os.getenv('GMAIL_SCOPES', 'https://www.googleapis.com/auth/gmail.modify')]
GMAIL_USER_ID = os.getenv('GMAIL_USER_ID', 'me')
GMAIL_WATCH_LABEL_ID = os.getenv('GMAIL_WATCH_LABEL_ID') 

# Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("Missing GEMINI_API_KEY environment variable")

# Google Cloud & Pub/Sub
GOOGLE_PROJECT_ID = os.getenv('GOOGLE_PROJECT_ID')
GMAIL_PUBSUB_SUBSCRIPTION_PATH = os.getenv('GMAIL_PUBSUB_SUBSCRIPTION_PATH')
GMAIL_PUBSUB_TOPIC_PATH = os.getenv('GMAIL_PUBSUB_TOPIC_PATH')
if not GMAIL_PUBSUB_TOPIC_PATH and __name__ == 'setup_gmail_watch': 
     print("Warning: GMAIL_PUBSUB_TOPIC_PATH not set in .env, needed for watch setup.")
if not GOOGLE_PROJECT_ID or not GMAIL_PUBSUB_SUBSCRIPTION_PATH:
    raise ValueError("Missing GOOGLE_PROJECT_ID or GMAIL_PUBSUB_SUBSCRIPTION_PATH environment variables")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("Warning: Telegram Bot Token or Chat ID not configured. Forwarding will fail.")


# Processing
try:
    SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', 0.75))
except ValueError:
    print("Warning: Invalid SIMILARITY_THRESHOLD. Using default 0.75")
SIMILARITY_THRESHOLD = 0.75

# Gemini Model Names
GEMINI_CLASSIFICATION_MODEL = 'gemini-2.0-flash'
GEMINI_GENERATION_MODEL = 'gemini-2.0-flash'

# eBay API
EBAY_APP_ID = os.getenv('EBAY_APP_ID')
EBAY_DEV_ID = os.getenv('EBAY_DEV_ID')
EBAY_CERT_ID = os.getenv('EBAY_CERT_ID')

if not EBAY_APP_ID or not EBAY_DEV_ID or not EBAY_CERT_ID:
    print("Warning: eBay API keys not configured. eBay search will fail.")

# eBay Browse API OAuth Credentials
EBAY_OAUTH_CLIENT_ID = os.getenv('EBAY_OAUTH_CLIENT_ID')
EBAY_OAUTH_CLIENT_SECRET = os.getenv('EBAY_OAUTH_CLIENT_SECRET')

# eBay API Environment (sandbox or production)
EBAY_ENVIRONMENT = os.getenv('EBAY_ENVIRONMENT', 'sandbox')
