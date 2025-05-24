import requests
import config
from logger_config import logger
import time
import base64 # Import the base64 module
from urllib.parse import urlencode # Import urlencode
# import json # No longer needed

# Base URL for eBay Browse API (Production and Sandbox)
EBAY_BROWSE_API_BASE_URL = {
    "sandbox": "https://api.sandbox.ebay.com/buy/browse/v1",
    "production": "https://api.ebay.com/buy/browse/v1"
}

# OAuth Token Endpoint
# Using the standard endpoint for Client Credentials Grant flow
EBAY_OAUTH_TOKEN_URL = {
    "sandbox": "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
    "production": "https://api.ebay.com/identity/v1/oauth2/token"
}

# Cache for OAuth token
oauth_token = None
token_expiry_time = 0

def get_oauth_token():
    """
    Obtains an OAuth access token using the client credentials grant flow.
    Caches the token and refreshes it when expired.
    """
    global oauth_token, token_expiry_time

    # Use cached token if not expired
    if oauth_token and time.time() < token_expiry_time:
        return oauth_token

    if not config.EBAY_OAUTH_CLIENT_ID or not config.EBAY_OAUTH_CLIENT_SECRET:
        logger.error("eBay OAuth Client ID or Client Secret not configured. Cannot obtain access token.")
        return None

    token_url = EBAY_OAUTH_TOKEN_URL.get(config.EBAY_ENVIRONMENT)
    if not token_url:
        logger.error(f"Invalid eBay environment specified: {config.EBAY_ENVIRONMENT}")
        return None

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {base64.b64encode(f'{config.EBAY_OAUTH_CLIENT_ID}:{config.EBAY_OAUTH_CLIENT_SECRET}'.encode()).decode()}"
    }

    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope"
        # Environment is determined by the token_url domain, not a parameter in the body for this endpoint
    }

    try:
        logger.info(f"Attempting to obtain eBay OAuth token from {token_url}")
        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status() # Raise an exception for bad status codes

        logger.debug(f"eBay OAuth token response status code: {response.status_code}")
        logger.debug(f"eBay OAuth token response text: {response.text}")

        token_data = response.json()
        logger.debug(f"Parsed eBay OAuth token response data: {token_data}")

        oauth_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 3600) # Default to 1 hour if not provided
        token_expiry_time = time.time() + expires_in - 60 # Refresh 60 seconds before expiry

        if oauth_token:
            logger.info("Successfully obtained eBay OAuth token.")
            return oauth_token
        else:
            logger.error("OAuth token not found in the response.")
            # Log the full response data if token is not found
            logger.error(f"Full token response data: {token_data}")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Error obtaining eBay OAuth token: {e}")
        if hasattr(e, 'response') and e.response is not None:
             logger.error(f"Error response status code: {e.response.status_code}")
             logger.error(f"Error response text: {e.response.text}")
        return None

def search_ebay_items(query: str) -> list[dict]:
    """
    Searches for items on eBay using the Browse API via HTTP requests.

    Args:
        query: The search query string.

    Returns:
        A list of dictionaries, each representing an eBay item,
        or an empty list if no items are found or an error occurs.
    """
    # Expecting query to be a dictionary directly
    params = query
    logger.info(f"DEBUG: search_ebay_items received query (dictionary): {params}") # Log the input query dictionary

    token = get_oauth_token()
    if not token:
        logger.error("Failed to obtain eBay OAuth token. Cannot perform search.")
        return []

    base_url = EBAY_BROWSE_API_BASE_URL.get(config.EBAY_ENVIRONMENT)
    if not base_url:
        logger.error(f"Invalid eBay environment specified: {config.EBAY_ENVIRONMENT}")
        return []

    search_url = f"{base_url}/item_summary/search"

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US", # Assuming US marketplace for now
        "Content-Type": "application/json"
    }

    # Ensure 'q' is in params
    if 'q' not in params:
        logger.warning("Input params dictionary does not contain a 'q' key.")
        return []

    # Ensure limit is set if not provided in the input dictionary
    if 'limit' not in params:
        params['limit'] = 50 # Default limit

    try:
        logger.info(f"Performing eBay Browse API search with parameters: {params} in {config.EBAY_ENVIRONMENT} environment")
        # Log the parameters being sent
        logger.info(f"API Request Parameters: {params}")

        response = requests.get(search_url, headers=headers, params=params)
        response.raise_for_status() # Raise an exception for bad status codes

        # Log the actual URL used by requests
        logger.info(f"Actual API Request URL: {response.url}")

        # Log the response status and content
        logger.info(f"API Response Status Code: {response.status_code}")
        logger.debug(f"API Response Body: {response.text}")

        search_results = response.json()

        items = []
        if search_results.get("itemSummaries"):
            for item in search_results["itemSummaries"]:
                item_details = {
                    'title': item.get('title', 'N/A'),
                    'itemId': item.get('itemId', 'N/A'),
                    'itemWebUrl': item.get('itemWebUrl', 'N/A'),
                    'price': item.get('price', {}).get('value', 'N/A'),
                    'currency': item.get('price', {}).get('currency', 'N/A'),
                    'condition': item.get('condition', 'N/A'),
                    # Add other relevant fields as needed
                }
                items.append(item_details)

        logger.info(f"Found {len(items)} items for query: '{query}'")
        return items

    except requests.exceptions.RequestException as e:
        logger.error(f"eBay Browse API search error for '{query}': {e}")
        if hasattr(e, 'response') and e.response is not None:
             logger.error(f"Error response: {e.response.text}")
        return []
    except Exception as e:
        logger.error(f"An unexpected error occurred during eBay Browse API search for '{query}': {e}", exc_info=True)
        return []

# Example usage (for testing)
if __name__ == '__main__':
    # Replace with a test query
    test_query = "thinkpad t470"
    logger.info(f"Performing test eBay Browse API search for: '{test_query}'")
    found_items = search_ebay_items(test_query)
    if found_items:
        logger.info("Test search results:")
        for item in found_items:
            logger.info(f"- {item.get('title')} ({item.get('price')} {item.get('currency')}) - {item.get('itemWebUrl')}")
    else:
        logger.info("No items found in test search.")
