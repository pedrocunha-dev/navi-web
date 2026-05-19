import shutil
from pathlib import Path

from django.apps import AppConfig


class PainelConfig(AppConfig):
    name = 'painel'

    def ready(self):
        tmp_dir = Path.home() / "AppData" / "Local" / "NAVI" / "tmp" / "imobiliario"
        if tmp_dir.exists():
            for item in tmp_dir.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)
                except Exception:
                    pass
