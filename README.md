# Novel Processor

A comprehensive, modular, service-oriented novel scraper, manager, and reader system. Designed to fetch metadata, covers, and chapter content from various web novel platforms and provide a seamless offline reading experience.

## Features

-   **Modular Architecture**: Built with a Service-Based Architecture for easy maintenance and scalability.
-   **Multiple Adapters**: Built-in support for:
    -   [Royal Road](https://www.royalroad.com/)
    -   [Scribble Hub](https://www.scribblehub.com/) (includes Playwright support for dynamic content)
    -   [FanFiction.net](https://www.fanfiction.net/)
-   **Mass Discovery Pipeline**: Collect novel URLs from site-wide ranking lists (e.g., RoyalRoad "Best Rated") and automatically hydrate metadata.
-   **Cross-Platform Deduplication**: Intelligent fuzzy matching (95% similarity) to merge novels found on multiple platforms.
-   **Advanced Sync Service**: Cron-ready script to keep your library up-to-date with the latest chapters.
-   **Browser-Based Reader**: A fully offline, high-performance web reader with:
    -   Multiple themes (Light, Sepia, Dark, AMOLED).
    -   Customizable typography (Font size, line height, column width).
    -   Bookmarks, reading progress, and personal notes per chapter.
    -   Tri-state tag filtering (Include/Exclude/Neutral) and advanced sorting.
    -   On-demand chapter fetching directly from the UI.
-   **Robust Infrastructure**:
    -   Fast fetch using `curl_cffi` for speed and impersonation.
    -   Playwright fallback for sites with heavy JavaScript.
    -   Repository Pattern for SQLite database management.

## Project Structure

```text
project_root/
│
├── core/               # Shared infrastructure
│   ├── config.py       # Configuration (User-Agents, Delays, Paths)
│   ├── database.py     # SQLite Repository and Database Manager
│   └── network.py      # Network client (curl_cffi)
│
├── adapters/           # Site-specific parsing logic
│   ├── base.py         # Abstract base adapter
│   ├── royalroad.py
│   ├── scribblehub.py
│   ├── fanfiction.py
│   └── discovery_adapters.py # List page parsers
│
├── services/           # Business logic orchestration
│   ├── browser_service.py   # Playwright browser lifecycle
│   ├── cover_manager.py     # Image downloading and storage
│   ├── scraper_service.py   # High-level scraping workflow
│   ├── discovery_service.py # Mass discovery orchestration
│   └── novel_update_service.py # Sync logic
│
├── reader/             # Offline Reader Application (FastAPI + JS)
│   ├── server.py       # API Backend
│   ├── run.py          # Launcher
│   └── static/         # Frontend (HTML/CSS/JS)
│
├── utils/              # General utility functions
├── main.py             # Single novel scraper entry point
├── sync_novels.py      # Library update entry point
└── init_db.py          # Database schema and migrations
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
# Discover top 100 novels from RoyalRoad
python -m services.discovery_service --site royalroad --start 1 --end 5

# Discover top 400 novels from ScribbleHub
python -m services.discovery_service --site scribblehub --start 1 --end 20
```

### 2. Single Novel Scraping
Scrape a specific novel by URL:
```bash
python main.py --url https://www.royalroad.com/fiction/12345/novel-title
```
*Use `--no-fetch` to skip downloading chapter content (metadata only).*

### 3. Synchronizing Updates
Run this to check for new chapters in your library (ideal for cron jobs):
```bash
python sync_novels.py --fetch-content
```

### 4. Reading Offline
Start the web-based reader:
```bash
python reader/run.py
```
This will launch a local server at `http://localhost:8765` and open your default browser.

## Configuration

Settings such as `FETCH_DELAY`, `TIMEOUT`, and `USER_AGENT` can be adjusted in `core/config.py`. Database location is also defined here (`novels.db` by default).

## License

[MIT](LICENSE)
