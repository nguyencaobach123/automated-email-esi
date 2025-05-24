import logging
import sys

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )
    logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
    logging.getLogger('google.auth.transport.requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.INFO)

logger = logging.getLogger("EmailAutomator")
