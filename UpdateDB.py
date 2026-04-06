from datetime import datetime, timedelta
from Processing_Epub import get_db_connection


def check_all_novels():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Fetch all novels from the database
    cursor.execute("SELECT id, title, source_url, last_updated FROM novels")
    all_novels = cursor.fetchall()

    for novel in all_novels:
        # Unpack the data from the row
        n_id, title, source_url, last_updated_str = novel

        # 2. Convert the stored string date to a Python date object
        if last_updated_str is None:
            last_date = datetime.now() - timedelta(days=31)
        else:
            last_date = datetime.strptime(last_updated_str, "%Y-%m-%d %H:%M:%S")

        # 3. Check the 30-day rule

        if datetime.now() > last_date + timedelta(days=30):
            print(f"Checking for updates: {title}...")

            # Insert your Novel-Grabber / Hashing logic here
            # ...

            # 4. Update the 'last_updated' timestamp so it doesn't check again tomorrow
            today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "UPDATE novels SET last_updated = ? WHERE id = ?", (today, n_id)
            )
            conn.commit()
        else:
            print(f"Skipping {title}: Last check was less than 30 days ago.")

    conn.close()


if __name__ == "__main__":
    check_all_novels()
