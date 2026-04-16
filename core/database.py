import sqlite3
import logging
from .config import DB_PATH

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path

    def execute(self, query, params=(), commit=False):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
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

    def get_pending_chapters(self):
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
