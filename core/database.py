import sqlite3
import logging
from .config import DB_PATH

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path

    def execute(self, query, params=(), commit=False, row_factory=None):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                if row_factory:
                    conn.row_factory = row_factory
                cursor = conn.cursor()
                cursor.execute(query, params)
                results = cursor.fetchall()
                if commit:
                    conn.commit()
                return results
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            raise

    def execute_transaction(self, operations):
        """
        Executes a list of (query, params) in a single transaction.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                cursor = conn.cursor()
                for query, params in operations:
                    cursor.execute(query, params)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Transaction error: {e}")
            conn.rollback()
            raise


class NovelRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def upsert_novel(self, data: dict, slug: str) -> int | None:
        query = """
            INSERT INTO novels (title, author, synopsis, source_url, slug, language, cover_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(title) DO UPDATE SET
                                          author       = excluded.author,
                                          synopsis     = excluded.synopsis,
                                          source_url   = excluded.source_url,
                                          slug         = excluded.slug,
                                          language     = excluded.language,
                                          last_updated = CURRENT_TIMESTAMP,
                                          cover_url    = excluded.cover_url
            RETURNING id
        """
        params = (
            data["title"],
            data.get("author"),
            data.get("synopsis"),
            data.get("url"),
            slug,
            data.get("language", "en"),
            data.get("cover_url"),
        )
        try:
            rows = self.db.execute(query, params, commit=True)
            if rows:
                return rows[0][0]
        except sqlite3.Error as e:
            # If RETURNING is not supported, it will raise an error (likely a Syntax Error or OperationalError)
            logger.warning(f"RETURNING clause failed, trying fallback: {e}")

        # Fallback if RETURNING is not supported or didn't return (though it should on insert/update)
        try:
            rows = self.db.execute(
                "SELECT id FROM novels WHERE title = ?", (data["title"],)
            )
            return rows[0][0] if rows else None
        except Exception as e:
            logger.error(f"Failed to upsert novel (fallback): {e}")
            return None

    def upsert_chapters(self, novel_id: int, chapters: list[dict]):
        operations = []
        for ch in chapters:
            query = """
                INSERT INTO chapters (novel_id, chapter_title, chapter_hash, chapter_order, chapter_url)
                VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(chapter_url) DO UPDATE SET
                    chapter_title = excluded.chapter_title,
                    chapter_order = excluded.chapter_order
            """
            params = (novel_id, ch["title"], "PENDING", ch["order"], ch["url"])
            operations.append((query, params))

        if operations:
            self.db.execute_transaction(operations)

    def link_tags(self, novel_id: int, tags: list[str]):
        for tag_name in tags:
            # Insert tag if not exists
            self.db.execute(
                "INSERT INTO tags (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
                (tag_name,),
                commit=True,
            )
            # Get tag id
            rows = self.db.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            if rows:
                tag_id = rows[0][0]
                # Link novel and tag
                self.db.execute(
                    "INSERT INTO novel_tags (novel_id, tag_id) VALUES (?, ?) ON CONFLICT(novel_id, tag_id) DO NOTHING",
                    (novel_id, tag_id),
                    commit=True,
                )

    def update_cover_path(self, novel_id: int, cover_path: str):
        query = "UPDATE novels SET cover_path = ? WHERE id = ?"
        self.db.execute(query, (cover_path, novel_id), commit=True)

    def get_pending_chapters(self, novel_id: int = None):
        if novel_id is not None:
            query = "SELECT id, chapter_title, chapter_url FROM chapters WHERE plain_content IS NULL AND novel_id = ?"
            return self.db.execute(query, (novel_id,))
        query = "SELECT id, chapter_title, chapter_url FROM chapters WHERE plain_content IS NULL"
        return self.db.execute(query)

    def update_chapter_content(
        self, ch_id: int, content_text: str, raw_html: str, chapter_hash: str
    ):
        query = """
            UPDATE chapters
            SET plain_content = ?,
                html_content = ?,
                chapter_hash = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        self.db.execute(
            query, (content_text, raw_html, chapter_hash, ch_id), commit=True
        )

    def get_novel_by_id(self, novel_id: int):
        """Retrieves a novel's data by its ID."""
        query = "SELECT * FROM novels WHERE id = ?"
        rows = self.db.execute(query, (novel_id,), row_factory=sqlite3.Row)
        if rows:
            return rows[0]
        return None

    def get_active_novels(self):
        query = "SELECT id, title, source_url, last_updated FROM novels WHERE status = 'ACTIVE'"
        return self.db.execute(query)

    def get_novel_chapters(self, novel_id: int):
        query = "SELECT chapter_order, chapter_url, id FROM chapters WHERE novel_id = ? ORDER BY chapter_order"
        rows = self.db.execute(query, (novel_id,))
        return {row[0]: {"url": row[1], "id": row[2]} for row in rows}

    def is_url_known(self, url: str) -> bool:
        """Checks if a URL exists in 'novels' or 'novel_sources'."""
        q1 = "SELECT 1 FROM novels WHERE source_url = ?"
        if self.db.execute(q1, (url,)):
            return True
        q2 = "SELECT 1 FROM novel_sources WHERE source_url = ?"
        if self.db.execute(q2, (url,)):
            return True
        return False

    def get_all_novels_for_fuzzy(self) -> list[tuple[int, str]]:
        """Returns all novel IDs and titles for fuzzy matching."""
        return self.db.execute("SELECT id, title FROM novels")

    def add_novel_source(self, novel_id: int, site: str, url: str):
        """Adds a source URL to an existing novel."""
        query = "INSERT INTO novel_sources (novel_id, source_site, source_url) VALUES (?, ?, ?)"
        self.db.execute(query, (novel_id, site, url), commit=True)

    def insert_discovered_novel(self, title: str, url: str, slug: str) -> int:
        """Inserts a new novel with 'discovered' status."""
        query = """
            INSERT INTO novels (title, source_url, slug, language, content_status)
            VALUES (?, ?, ?, 'en', 'discovered')
            RETURNING id
        """
        # Note: DatabaseManager.execute returns list of rows
        rows = self.db.execute(query, (title, url, slug), commit=True)
        if rows:
            return rows[0][0]
        # Fallback for older sqlite
        row = self.db.execute("SELECT id FROM novels WHERE title = ?", (title,))
        return row[0][0]

    def update_content_status(self, novel_id: int, status: str):
        """Updates the content_status of a novel."""
        query = "UPDATE novels SET content_status = ? WHERE id = ?"
        self.db.execute(query, (status, novel_id), commit=True)

    def update_novel_timestamp(self, novel_id: int):
        query = "UPDATE novels SET last_updated = CURRENT_TIMESTAMP WHERE id = ?"
        self.db.execute(query, (novel_id,), commit=True)

    def get_tags(self):
        query = "SELECT name FROM tags ORDER BY name ASC"
        rows = self.db.execute(query)
        return [row[0] for row in rows]

    def get_filtered_novels(
        self, include_tags=None, exclude_tags=None, sort_by="title"
    ):
        """
        Retrieves novels with tri-state tag filtering and sorting.
        sort_by options: 'title', 'last_updated', 'chapter_count', 'word_count'
        """
        params = []

        # Base query with chapter_count and chapters_read
        # We also need a way to get word_count. Word count is stored in chapters or novels?
        # Looking at schema: chapters has plain_content. Word count is len(content.split()).
        # The issue description says sort by Word Count (Descending).
        # Usually word count is per novel (sum of chapters).

        query = """
            SELECT n.*, 
                   (SELECT COUNT(*) FROM chapters WHERE novel_id = n.id) as chapter_count,
                   (SELECT COUNT(*) FROM reading_progress WHERE novel_id = n.id AND scroll_position >= 0.9) as chapters_read,
                   (SELECT SUM(length(plain_content) - length(replace(plain_content, ' ', '')) + 1) 
                    FROM chapters WHERE novel_id = n.id AND plain_content IS NOT NULL) as word_count
            FROM novels n
            WHERE 1=1
        """

        if include_tags:
            for tag in include_tags:
                query += """
                    AND EXISTS (
                        SELECT 1 FROM novel_tags nt 
                        JOIN tags t ON nt.tag_id = t.id 
                        WHERE nt.novel_id = n.id AND t.name = ?
                    )
                """
                params.append(tag)

        if exclude_tags:
            for tag in exclude_tags:
                query += """
                    AND NOT EXISTS (
                        SELECT 1 FROM novel_tags nt 
                        JOIN tags t ON nt.tag_id = t.id 
                        WHERE nt.novel_id = n.id AND t.name = ?
                    )
                """
                params.append(tag)

        # Sorting
        sort_map = {
            "title": "n.title ASC",
            "last_updated": "n.last_updated DESC",
            "chapter_count": "chapter_count DESC",
            "word_count": "word_count DESC",
        }
        order_by = sort_map.get(sort_by, "n.title ASC")
        query += f" ORDER BY {order_by}"

        rows = self.db.execute(query, tuple(params))

        # Convert to list of dicts for easier consumption in API
        # Since DatabaseManager.execute returns list of tuples, we need column names.
        # But DatabaseManager doesn't return column names.
        # We can either change DatabaseManager or use a different approach.
        # Actually reader/server.py uses sqlite3.Row.

        return rows
