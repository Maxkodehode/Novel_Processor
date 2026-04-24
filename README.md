# Novel Processor

A comprehensive, modular, service-oriented novel scraper, manager, and reader system. Designed to fetch metadata, covers, and chapter content from various web novel platforms and provide a seamless offline reading experience.

## Features

-   **Modular Architecture**: Built with a Service-Based Architecture for easy maintenance and scalability.
-   **Multiple Adapters**: Built-in support for:
    -   [Royal Road](https://www.royalroad.com/)
    -   [Scribble Hub](https://www.scribblehub.com/) (Playwright support for JS-rendered chapter lists, using `toc_fic_show_all()` to load all chapters in a single pass)
    -   [FanFiction.net](https://www.fanfiction.net/)
-   **Mass Discovery Pipeline**: Crawl site-wide ranking lists and automatically hydrate your library with novel metadata and full chapter lists.
-   **Cross-Platform Deduplication**: Two-tier deduplication — exact URL matching and intelligent fuzzy title matching (95% similarity) — to avoid inserting the same novel twice across platforms.
-   **Advanced Sync Service**: Cron-ready script to keep your library up-to-date with the latest chapters.
-   **Database Maintenance Tools**: Standalone scripts to backfill missing chapter URLs and download missing chapter content across your entire library.
-   **Browser-Based Reader**: A fully offline, high-performance web reader with:
    -   Multiple themes (Light, Sepia, Dark, AMOLED).
    -   Customizable typography (Font size, line height, column width, font family).
    -   Bookmarks, reading progress, and personal notes per chapter.
    -   Tri-state tag filtering (Include/Exclude/Neutral) and advanced sorting.
    -   On-demand chapter fetching and updating directly from the UI.
-   **Robust Infrastructure**:
    -   Fast fetch using `curl_cffi` for speed and browser impersonation.
    -   Playwright fallback for sites with heavy JavaScript.
    -   Jittered, rate-limited request delays throughout to avoid being blocked.
    -   Repository Pattern for SQLite database management.
    -   Structured fetch logging with automatic log rotation (keeps last 10 runs).

## Project Structure

```text
project_root/
│
├── core/               # Shared infrastructure
│   ├── config.py       # Configuration (User-Agents, Delays, Paths)
│   ├── database.py     # SQLite Repository and Database Manager
│   ├── network.py      # Network client (curl_cffi)
│   └── run_logger.py   # Structured per-run fetch logging
│
├── adapters/           # Site-specific parsing logic
│   ├── base.py                # Abstract base adapter
│   ├── royalroad.py
│   ├── scribblehub.py
│   ├── fanfiction.py
│   ├── discovery_base.py      # Abstract base discovery adapter
│   └── discovery_adapters.py  # List page parsers for mass discovery
│
├── services/           # Business logic orchestration
│   ├── browser_service.py      # Playwright browser lifecycle
│   ├── cover_manager.py        # Image downloading and storage
│   ├── scraper_service.py      # High-level scraping workflow
│   ├── discovery_service.py    # Mass discovery orchestration
│   └── novel_update_service.py # Sync logic
│
├── reader/             # Offline Reader Application (FastAPI + JS)
│   ├── server.py       # API Backend
│   ├── run.py          # Launcher
│   └── static/         # Frontend (HTML/CSS/JS)
│
├── utils/                     # General utility functions
├── main.py                    # Single novel scraper entry point
├── sync_novels.py             # Library update entry point
├── backfill_chapter_urls.py   # Fix novels missing chapter titles and URLs
├── backfill_chapters.py       # Download missing chapter content library-wide
└── init_db.py                 # Database schema and migrations
```

## Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/Maxkodehode/Novel_Processor.git
    cd Novel_Processor
    ```

2.  **Set up a virtual environment**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    playwright install chromium
    ```

4.  **Initialize the database**:
    ```bash
    python init_db.py
    python reader/migrate_reader.py
    ```

## Usage

### 1. Mass Discovery
Hydrate your database with top-rated novels from supported platforms:
```bash
# Discover top 100 novels from RoyalRoad (20 novels per page)
python -m services.discovery_service --site royalroad --start 1 --end 5

# Discover top 400 novels from ScribbleHub
python -m services.discovery_service --site scribblehub --start 1 --end 20
```

Discovery saves the novel title, author, synopsis, cover, tags, and the full list of chapter titles and URLs. It does **not** download chapter text — that is a separate step. Rate limiting is applied automatically between every request.

### 2. Single Novel Scraping
Scrape a specific novel by URL:
```bash
# Full pipeline: scrape metadata + chapter list + download all content
python main.py --url https://www.royalroad.com/fiction/12345/novel-title

# Metadata and chapter list only (skip downloading chapter content)
python main.py --url https://www.royalroad.com/fiction/12345/novel-title --no-fetch

# Save a debug copy of the raw HTML and parsed JSON
python main.py --url https://www.royalroad.com/fiction/12345/novel-title --debug

# Use a locally saved HTML file instead of fetching (dev mode)
python main.py --url https://www.royalroad.com/fiction/12345/novel-title --use-local page.html
```

### 3. Synchronizing Updates
Run this to check for new chapters in your library (ideal for cron jobs):
```bash
# Check for new chapters only
python sync_novels.py

# Check for new chapters and download their content
python sync_novels.py --fetch-content
```

### 4. Database Maintenance

**Fix novels that are missing chapter titles and URLs** (e.g. novels discovered before the chapter-URL bug was fixed):
```bash
# Preview which novels would be fixed without making any changes
python backfill_chapter_urls.py --dry-run

# Fix all novels that have no chapter rows
python backfill_chapter_urls.py

# Fix a single novel by its database ID
python backfill_chapter_urls.py --id 42
```

**Download missing chapter content** for chapters that have a URL but no text yet:
```bash
python backfill_chapters.py
```

Both scripts are safe to re-run and will not create duplicate entries.

### 5. Reading Offline
Start the web-based reader:
```bash
python reader/run.py
```
This will launch a local server at `http://localhost:8765` and open your default browser.

## Configuration

All settings are in `core/config.py`:

| Setting | Default | Description |
|---|---|---|
| `DB_PATH` | `novels.db` | Database file (overridable via `DB_PATH` env var) |
| `FETCH_DELAY` | `8s` | Base delay between chapter content downloads |
| `FETCH_DELAY_JITTER` | `3s` | Max random extra seconds added to each delay |
| `FETCH_MAX_RETRIES` | `2` | Retry attempts before marking a chapter failed |
| `TIMEOUT` | `30s` | Network request timeout |
| `DISCOVERY_PAGE_DELAY_MIN/MAX` | `6–12s` | Delay between discovery list pages |
| `DISCOVERY_NOVEL_DELAY_MIN/MAX` | `8–14s` | Delay between per-novel hydration requests |
| `COVER_FETCH_DELAY` | `2s` | Delay before each cover image download |
| `COVERS_DIR` | `covers/` | Directory where cover images are saved |

## License

[MIT](LICENSE)