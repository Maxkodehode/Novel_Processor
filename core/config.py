import os

# Database
DB_PATH = os.getenv("DB_PATH", "novels.db")

# Network
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
FETCH_DELAY = 8  # seconds between requests
TIMEOUT = 30
FETCH_MAX_RETRIES = 2

# Files
COVERS_DIR = "covers"

# DB Config
COMMIT_BATCH_SIZE = 10
