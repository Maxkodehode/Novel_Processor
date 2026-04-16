import uvicorn
import webbrowser
import threading
import time


def open_browser():
    time.sleep(1.0)
    webbrowser.open("http://localhost:8765")


if __name__ == "__main__":
    import os
    import sys

    sys.path.append(os.getcwd())
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("reader.server:app", host="127.0.0.1", port=8765, reload=False)
