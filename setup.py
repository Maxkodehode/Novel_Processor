import os
import zipfile
import urllib.request
from pathlib import Path


def ensure_novel_grabber():
    # Configuration
    url = "https://github.com/Flameish/Novel-Grabber/releases/latest/download/Novel-Grabber.zip"
    parent_dir = Path("./scraper")
    target_folder = parent_dir / "Novel-Grabber"
    temp_zip = "temp_ng.zip"

    # 1. Check if the directory already exists
    if target_folder.exists():
        return  # Everything is already set up

    print(f"Novel-Grabber not found in {parent_dir}. Downloading...")

    # 2. Create the scraper directory if needed
    parent_dir.mkdir(parents=True, exist_ok=True)

    # 3. Download the file
    try:
        urllib.request.urlretrieve(url, temp_zip)

        # 4. Extract the ZIP
        # Since the ZIP contains a folder named 'Novel-Grabber',
        # extracting to ./scraper creates ./scraper/Novel-Grabber/
        with zipfile.ZipFile(temp_zip, "r") as zip_ref:
            zip_ref.extractall(parent_dir)

        print("Successfully installed Novel-Grabber.")
    except Exception as e:
        print(f"Error downloading tool: {e}")
    finally:
        if os.path.exists(temp_zip):
            os.remove(temp_zip)


# Run the check before starting the main program
if __name__ == "__main__":
    ensure_novel_grabber()
    # Your program logic starts here
    print("Starting scraper...")
