import os
import sys
from pathlib import Path

PASTA_TEMP = Path.home() / "AppData" / "Local" / "NAVI" / "tmp" / "imobiliario"
DOWNLOADS_DIR = Path.home() / "Downloads"


def get_resource_path(filename: str) -> Path:
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / filename
    return Path(__file__).resolve().parents[2] / filename


def setup_playwright_path() -> None:
    if hasattr(sys, '_MEIPASS'):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(get_resource_path("ms-playwright"))
