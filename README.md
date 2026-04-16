# Novel Processor

A modular, service-oriented novel scraper and manager designed to fetch metadata, covers, and chapter content from various web novel platforms.

## Features

- **Modular Architecture**: Built with a Service-Based Architecture for easy maintenance and scalability.
- **Multiple Adapters**: Built-in support for popular novel sites:
    - [Royal Road](https://www.royalroad.com/)
    - [Scribble Hub](https://www.scribblehub.com/) (includes Playwright support for dynamic content)
    - [FanFiction.net](https://www.fanfiction.net/)
- **Robust Database**: Uses SQLite with a Repository Pattern to manage novels, chapters, and tags.
- **Smart Fetching**: 
    - Fast fetch using `curl_cffi` for speed and impersonation.
    - Playwright fallback for sites with heavy JavaScript or anti-bot protection.
    - Automatic cover image downloading and management.
- **Resilient Pipeline**: Handles "Database is locked" errors and includes fallback mechanisms for older SQLite versions.

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
│   └── fanfiction.py
│
├── services/           # Business logic orchestration
│   ├── browser_service.py # Playwright browser lifecycle
│   ├── cover_manager.py   # Image downloading and storage
│   └── scraper_service.py # High-level scraping workflow
│
├── utils/              # General utility functions
│   └── text.py         # Slugification and text processing
│
├── main.py             # CLI Entry point
└── init_db.py          # Database schema initialization
```

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Maxkodehode/Novel_Processor.git
   cd Novel_Processor
   ```

2. **Set up a virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Initialize the database**:
   ```bash
   python init_db.py
   ```

## Usage

The `main.py` script is the primary entry point for the pipeline.

### Basic Scraping

Scrape a novel's metadata and fetch all chapters:
```bash
python main.py --url https://www.royalroad.com/fiction/12345/novel-title
```

### Scrape Metadata Only

If you only want to populate the database with metadata (titles, tags, synopsis, cover) without downloading chapter content:
```bash
python main.py --url https://www.royalroad.com/fiction/12345/novel-title --no-fetch
```

### Debug Mode

Save the raw HTML and parsed JSON output for inspection:
```bash
python main.py --url https://www.royalroad.com/fiction/12345/novel-title --debug
```

### Options

| Flag | Description |
|------|-------------|
| `--url` | **Required**. The landing page URL of the novel. |
| `--no-fetch` | Skip fetching chapter content after metadata is inserted. |
| `--debug` | Saves `page.html` and `output.json` for troubleshooting. |
| `--use-local <FILE>`| Use a local HTML file instead of fetching from the web (Dev mode). |

## Configuration

Settings such as `FETCH_DELAY`, `TIMEOUT`, and `USER_AGENT` can be adjusted in `core/config.py`.

## License

[MIT](LICENSE) (or specify your own)
