import sqlite3
import hashlib
import os
from pathlib import Path
from ebooklib import epub
from bs4 import BeautifulSoup


def get_db_connection():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(current_dir, "novels.db")
    return sqlite3.connect(db_path)


def generate_slug(text):
    return text.lower().replace(" ", "-").replace("'", "")[:50]


SCRIPT_DIR = Path(__file__).parent


def process_all_novels(directory_path=None):
    if directory_path is None:
        base_path = SCRIPT_DIR / "Scraped_Novels"
    else:
        base_path = Path(directory_path)

    if not base_path.exists():
        print(f"Directory not found. Creating: {base_path.absolute()}")
        base_path.mkdir(parents=True, exist_ok=True)
        print("Directory created. Please add your EPUB files there.")
        return

    epub_files = list(base_path.glob("*.epub"))

    if not epub_files:
        print(f"No EPUB files found in {base_path.name}. Skipping sync.")
        return

    print(f"Found {len(epub_files)} novels. Starting database sync...")

    conn = get_db_connection()
    cursor = conn.cursor()

    for epub_file in epub_files:
        try:
            book = epub.read_epub(str(epub_file))

            # Fix: metadata returns list of tuples like [('Value', {})]
            title_meta = book.get_metadata("DC", "title")
            title = title_meta[0][0] if title_meta else epub_file.stem

            author_meta = book.get_metadata("DC", "creator")
            author = author_meta[0][0] if author_meta else "Unknown"

            lang_meta = book.get_metadata("DC", "language")
            language = lang_meta[0][0] if lang_meta else "en"

            slug = generate_slug(title)

            cursor.execute(
                "INSERT OR IGNORE INTO novels (title, author, slug, language) VALUES (?, ?, ?, ?)",
                (title, author, slug, language),
            )

            # Fix: extract int from tuple
            cursor.execute("SELECT id FROM novels WHERE title = ?", (title,))
            novel_id = cursor.fetchone()[0]

            order_counter = 1.0
            for item in book.get_items_of_type(9):
                html_content = item.get_content().decode("utf-8")
                soup = BeautifulSoup(html_content, "html.parser")

                header = soup.find(["h1", "h2", "h3"])
                chapter_title = (
                    header.get_text() if header else f"Chapter {int(order_counter)}"
                )

                plain_content = soup.get_text(separator="\n")
                chapter_hash = hashlib.md5(plain_content.encode()).hexdigest()

                cursor.execute(
                    """INSERT OR IGNORE INTO chapters 
                    (novel_id, chapter_title, chapter_hash, plain_content, html_content, chapter_order)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        novel_id,
                        chapter_title,
                        chapter_hash,
                        plain_content,
                        html_content,
                        order_counter,
                    ),
                )

                order_counter += 1.0

            conn.commit()
            print(f"Successfully processed: {title}")

        except Exception as e:
            print(f"Failed to process {epub_file.name}: {e}")

    conn.close()


# Fix: moved to module level, outside the function
if __name__ == "__main__":
    process_all_novels()
