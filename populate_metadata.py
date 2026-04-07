import json
import sqlite3


def populate_from_json(json_path="output.json", db_path="novels.db"):
    with open(json_path, "r") as f:
        data = json.load(f)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    # Insert novel
    cursor.execute(
        """
        INSERT INTO novels (title, author, synopsis, source_url, slug, language)
        VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(title) DO UPDATE SET
            author     = excluded.author,
                                      synopsis   = excluded.synopsis,
                                      source_url = excluded.source_url,
                                      language   = excluded.language,
                                      last_updated = CURRENT_TIMESTAMP
        """,
        (
            data["title"],
            data["author"],
            data["synopsis"],
            data["url"],
            data["title"].lower().replace(" ", "-"),
            data["language"],
        ),
    )

    cursor.execute("SELECT id FROM novels WHERE title = ?", (data["title"],))
    row = cursor.fetchone()
    if not row:
        print("Error: Novel not found after insert.")
        conn.close()
        return
    novel_id = row[0]

    # Insert chapter placeholders
    chapters_inserted = 0
    for ch in data["chapters"]:
        cursor.execute(
            """
            INSERT INTO chapters (novel_id, chapter_title, chapter_hash, chapter_order, chapter_url)
            VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chapter_url) DO UPDATE SET
                chapter_title = excluded.chapter_title,
                                                chapter_order = excluded.chapter_order
            """,
            (novel_id, ch["title"], "PENDING", ch["order"], ch["url"]),
        )
        if cursor.rowcount:
            chapters_inserted += 1

    # Insert tags and link them to this novel
    tags_linked = 0
    for tag_name in data.get("tags", []):
        cursor.execute(
            "INSERT INTO tags (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
            (tag_name,),
        )

        cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
        tag_row = cursor.fetchone()
        if not tag_row:
            continue
        tag_id = tag_row[0]

        # Link tag to this novel
        cursor.execute(
            """
            INSERT INTO novel_tags (novel_id, tag_id)
            VALUES (?, ?)
                ON CONFLICT(novel_id, tag_id) DO NOTHING
            """,
            (novel_id, tag_id),
        )
        tags_linked += 1

    conn.commit()
    conn.close()
    print(f"✅ '{data['title']}' — novel_id={novel_id}")
    print(f"   Chapters : {chapters_inserted} inserted / {len(data['chapters'])} total")
    print(f"   Tags     : {tags_linked} linked")


if __name__ == "__main__":
    populate_from_json()
