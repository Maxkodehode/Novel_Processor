import sys
import os

print("--- DIAGNOSTICS ---")
print(f"Current Python Path: {sys.executable}")

if ".venv" in sys.executable:
    print("✅ SUCCESS: Rider is using your Virtual Environment.")
else:
    print("❌ ALERT: Rider is still using System Python. Libraries won't work.")

try:
    import ebooklib
    print("✅ SUCCESS: ebooklib is installed and ready.")
except ImportError:
    print("❌ ERROR: ebooklib not found. Did you run 'pip install' in the right terminal?")