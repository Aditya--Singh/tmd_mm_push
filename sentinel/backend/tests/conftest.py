import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp(prefix="sentinel-test-")
# the Master Directions listing is copied so a test can edit it to simulate RBI revising a document
import shutil

PAGES = Path(_tmp) / "pages"
shutil.copytree(FIX, PAGES)
_CHROME = "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome"  # sandbox Chromium; leave unset elsewhere
if Path(_CHROME).exists():
    os.environ.setdefault("CHROMIUM_PATH", _CHROME)
os.environ.update(
    {
        "DATA_DIR": _tmp,
        "DATABASE_URL": "",
        "LLM_PROVIDER": os.environ.get("TEST_LLM_PROVIDER", "none"),
        "EMBEDDING_PROVIDER": os.environ.get("TEST_EMBEDDING_PROVIDER", "hash"),
        "EMBEDDING_MODEL": "bge-m3",
        "EMBEDDING_BASE_URL": os.environ.get("LLM_BASE_URL", ""),
        "RBI_FEEDS": f"notification={FIX / 'notifications.xml'},press_release={FIX / 'press.xml'}",
        "FETCH_DETAIL_PAGE": "false",
        "SYNC_ON_STARTUP": "false",
        "SMTP_PASSWORD": "",
        "ADMIN_PASSWORD": "Test@Pass123",
        "JWT_SECRET": "test-secret-test-secret-test-secret",
        "POLITE_DELAY_SECONDS": "0",
        "NOTIFY_ON_FIRST_SYNC": "true",
        "DIGEST_THRESHOLD": "20",
        "MASTER_CIRCULARS_URL": str(PAGES / "mc_list.html"),
        "MASTER_DIRECTIONS_URL": str(PAGES / "md_list.html"),
        "HTTP_TIMEOUT_SECONDS": "3",
        "EMAIL_ENABLED": "true",
        "AUTH_ENABLED": "true",
        "BACKFILL_CONTINUOUS": "false",
        "AI_SUMMARY_QUEUE_ENABLED": "false",
    }
)
