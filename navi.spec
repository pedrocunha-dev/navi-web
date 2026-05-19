# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for NAVI.

Build:
    pyinstaller --clean --noconfirm navi.spec

Output in dist/NAVI_Web/ (onedir mode, visible console window).
"""
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_data_files,
    copy_metadata,
)

# ============================================================
# Paths
# ============================================================
# SPECPATH is the folder where the .spec lives (set by PyInstaller at runtime).
ROOT = Path(SPECPATH).resolve()

# Playwright Chromium folder. build.bat sets PLAYWRIGHT_BROWSERS_PATH to .pw-browsers/
# inside the project before running 'playwright install chromium', so the browser
# lands there and can be bundled deterministically.
PW_BROWSERS = ROOT / '.pw-browsers'
if not PW_BROWSERS.exists():
    raise SystemExit(
        f'ERROR: folder {PW_BROWSERS} does not exist. '
        f'Run "build.bat" (which calls playwright install with PLAYWRIGHT_BROWSERS_PATH '
        f'pointing to .pw-browsers/) before generating the build.'
    )


# ============================================================
# Data files (files that must be available at runtime)
# ============================================================
datas = []

# Django templates and static files go to the bundle root. settings.BASE_DIR
# points to sys._MEIPASS when packaged, so Django finds 'painel/templates'
# and 'painel/static' from there.
datas += [
    (str(ROOT / 'painel' / 'templates'), 'painel/templates'),
    (str(ROOT / 'painel' / 'static'),    'painel/static'),
]

# Playwright Chromium. setup_playwright_path() in scrapers/common/paths.py
# sets PLAYWRIGHT_BROWSERS_PATH to sys._MEIPASS / 'ms-playwright'.
datas += [(str(PW_BROWSERS), 'ms-playwright')]

# Package metadata that some libraries query at runtime via importlib.metadata.
# groq (Pydantic v2) and Django frequently do this.
for pkg in ('django', 'groq', 'pydantic', 'pydantic_core', 'anyio', 'httpx', 'sniffio'):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

# Data files declared by libraries (internal templates, .pyi, etc.)
for pkg in ('django',):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass


# ============================================================
# Hidden imports
# ============================================================
# Django discovers apps/backends/middleware/template engines by string at runtime
# so PyInstaller cannot detect them. collect_submodules('django') pulls the entire
# package — the size cost is worth the reliability.
hiddenimports = []
hiddenimports += collect_submodules('django')

# Project apps and settings module
hiddenimports += [
    'naviweb',
    'naviweb.settings',
    'naviweb.urls',
    'naviweb.wsgi',
    'painel',
    'painel.apps',
    'painel.urls',
    'painel.views',
    'painel.models',
]

# Scrapers (dynamically imported in some code paths)
hiddenimports += [
    'scrapers',
    'scrapers.common.paths',
    'scrapers.common.files',
    'scrapers.common.excel',
    'scrapers.common.images',
    'scrapers.common.word',
    'scrapers.common.ai_descricao',
    'scrapers.shared_scraper',
    'scrapers.imoveis_unificados',
    'scrapers.relatorios_unificados',
    'scrapers.Site1.site1_scraper',
    'scrapers.Site2.site2_scraper',
    'scrapers.Site3.site3_scraper',
]

# groq + pydantic use dynamic discovery
hiddenimports += collect_submodules('groq')
hiddenimports += collect_submodules('pydantic')

# openpyxl loads writers/readers by string
hiddenimports += collect_submodules('openpyxl')


# ============================================================
# Excludes (modulos pesados que nao usamos)
# ============================================================
# Esses sao arrastados por pandas/numpy/Django mas o NAVI nao chama.
# Cada um aqui economiza de 1MB a 40MB.
excludes = [
    # GUIs nao utilizadas
    'tkinter',
    '_tkinter',
    'Tkinter',

    # Plotting (pandas as vezes puxa quando detecta matplotlib instalado)
    'matplotlib',
    'matplotlib.tests',

    # Ciencia pesada
    'scipy',
    'scipy.tests',
    'sklearn',
    'sympy',
    'numba',

    # Jupyter / IPython
    'IPython',
    'jupyter',
    'jupyter_client',
    'jupyter_core',
    'notebook',
    'ipykernel',
    'ipywidgets',
    'jedi',
    'parso',

    # Testes
    'pytest',
    'unittest.mock',
    '_pytest',
    'pandas.tests',
    'numpy.tests',
    'PIL.tests',

    # Outros backends de DB do Django (so usamos sqlite)
    'django.db.backends.mysql',
    'django.db.backends.postgresql',
    'django.db.backends.oracle',

    # Outras coisas que aparecem em pandas/numpy
    'pandas.io.formats.style',  # depende de jinja2 + matplotlib
    'pyarrow',
    'fastparquet',
    'tables',
    'bottleneck',
    'numexpr',
    'xlrd',  # so se o NAVI nao le .xls antigo
    'xlwt',
    'odf',

    # Email backends que Django arrasta mas nao usamos
    'django.contrib.gis',
]


# ============================================================
# Analysis
# ============================================================
a = Analysis(
    ['navi_launcher.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)


# ============================================================
# EXE + COLLECT (onedir)
# ============================================================
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NAVI_Web',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # UPX desligado: antivirus corporativo costuma marcar como suspeito
    console=True,         # console preto visivel (decisao do usuario)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'navi.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='NAVI_Web',
)
