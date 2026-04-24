import os  # No module named 'os' error
import time  # No module named 'time' error
from datetime import datetime  # Unresolved reference 'datetime'
from core.config import DB_PATH


class RunLogger:
    def __init__(self, total_pending):
        self.total_pending = total_pending
        self.ok_count = 0
        self.failed_count = 0
        self.start_time = time.time()

        # Derive project root from DB_PATH
        # DB_PATH is likely 'novels.db' or an absolute path
        db_abs = os.path.abspath(DB_PATH)
        project_root = os.path.dirname(db_abs)
        self.logs_dir = os.path.join(project_root, "logs")

        if not os.path.exists(self.logs_dir):
            os.makedirs(self.logs_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = f"fetch_{timestamp}.log"
        self.filepath = os.path.join(self.logs_dir, self.filename)
        self.file = None

    def __enter__(self):
        self.file = open(self.filepath, "w", encoding="utf-8")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.file.write(f"[START] {timestamp} — {self.total_pending} chapters queued\n")
        self.file.flush()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            total_time = time.time() - self.start_time
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.file.write(f"[END] {timestamp}\n")
            self.file.write(
                f"Total: {self.total_pending} | OK: {self.ok_count} | Failed: {self.failed_count} | Elapsed: {total_time:.1f}s\n"
            )
            self.file.close()
            self._rotate_logs()

    def ok(self, ch_id, title, word_count, elapsed):
        self.ok_count += 1
        self.file.write(
            f'[OK]    ch_id={ch_id} "{title}" ({word_count} words) +{elapsed:.1f}s\n'
        )
        self.file.flush()

    def retry(self, ch_id, title, attempt, error):
        self.file.write(
            f'[RETRY] ch_id={ch_id} "{title}" attempt {attempt} — {error}\n'
        )
        self.file.flush()

    def fail(self, ch_id, title, error):
        self.failed_count += 1
        self.file.write(f'[FAIL]  ch_id={ch_id} "{title}" — {error}\n')
        self.file.flush()

    def _rotate_logs(self):
        try:
            files = [
                os.path.join(self.logs_dir, f)
                for f in os.listdir(self.logs_dir)
                if f.startswith("fetch_") and f.endswith(".log")
            ]
            files.sort(key=os.path.getmtime)

            while len(files) > 10:
                oldest_file = files.pop(0)
                os.remove(oldest_file)
        except Exception as e:
            # Fallback if rotation fails, don't crash the main process
            print(f"Error rotating logs: {e}")
