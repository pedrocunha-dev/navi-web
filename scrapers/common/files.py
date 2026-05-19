import shutil
from pathlib import Path

from scrapers.common.paths import PASTA_TEMP, DOWNLOADS_DIR


def gerar_nome_lote(site_slug: str) -> tuple[str, str]:
    """Retorna (caminho_xlsx, lote_numero) sem sobrescrever arquivos existentes."""
    PASTA_TEMP.mkdir(parents=True, exist_ok=True)
    for n in range(1, 10_000):
        caminho = PASTA_TEMP / f"{site_slug}_lote_{n}.xlsx"
        if not caminho.exists():
            return str(caminho), str(n)
    raise RuntimeError("Limite de lotes atingido.")


def copiar_para_downloads(src: Path) -> None:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, DOWNLOADS_DIR / src.name)
    print(f"📄 Cópia salva em: {DOWNLOADS_DIR / src.name}")
