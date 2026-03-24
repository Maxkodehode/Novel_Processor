import sqlite3


def create_pure_schema():
    # This connects to the file; if it doesn't exist, it creates it
    conn = sqlite3.connect("novels.db")
    cursor = conn.cursor()

    # 1. The Novels Table: Basic info about the book
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS novels (
                                                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                         title TEXT NOT NULL UNIQUE,
                                                         synopsis TEXT,
                                                         author TEXT,
                                                         source_url TEXT,
                                                         cover_path TEXT,
                                                         slug TEXT NOT NULL UNIQUE,
                                                         language NOT NULL TEXT
                   )
                   """)

    # 2. The Chapters Table: The actual text, linked to a novel
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS chapters (
                                                           id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                           novel_id INTEGER,
                                                           title TEXT,
                                                           content TEXT,
                                                           FOREIGN KEY (novel_id) REFERENCES novels (id)
                       )
                   """)

    # 3. The Tags Table: A unique master list of genres/tags
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS tags (
                                                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                       name TEXT NOT NULL UNIQUE
                   )
                   """)

    # 4. The Link Table: Connects many novels to many tags
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS novel_tags (
                                                             novel_id INTEGER,
                                                             tag_id INTEGER,
                                                             PRIMARY KEY (novel_id, tag_id),
                       FOREIGN KEY (novel_id) REFERENCES novels (id),
                       FOREIGN KEY (tag_id) REFERENCES tags (id)
                       )
                   """)

    conn.commit()
    conn.close()
    print("✅ Empty Database Schema Created Successfully!")


if __name__ == "__main__":
    create_pure_schema()
