# NAVI — Real Estate Scraping Panel

A Django web panel for scraping, consolidating, and exporting real estate listings. NAVI automates the full pipeline: fetching listing pages, downloading photos, generating structured `.xlsx` spreadsheets and `.docx` photo reports, and consolidating results from multiple scraping runs into unified files.

## Features

- **Three configurable scrapers** for different target sites
  - **Site 1** — runs in a visible browser window with automatic bot-challenge detection; handles paginated search results via path-based URLs (`-pagina-N.html`)
  - **Site 2 / Site 3** — run headless; handle paginated results via query-string (`?pagina=N`); share an identical HTML structure (unified scraper)
- **Page range scraping** — scrape multiple pages per site in a single run
- **AI description mode** — optionally visits each listing individually, reads its full description, and uses a Groq LLM to extract *Built Area* and *Land Area* into extra spreadsheet columns
- **Photo reports** — generates `.docx` files with property photos in a 2×3 (merged) or 2×4 grid layout
- **Consolidation pipeline** — merges all batch `.xlsx` files, deduplicates by (price, area), filters listings without photos, and generates a unified `.xlsx` and a consolidated `.docx` photo report
- **Proxy support** — optional authenticated HTTP proxy, configured at runtime via the Settings page; passed down to Playwright and `requests`
- **Cancellable jobs** — scraping runs in a background thread; the UI polls status every 3 seconds and shows a cancel button

## Requirements

- Python 3.10+
- Playwright Chromium

## Installation (Linux / macOS)

```bash
pip3 install -r requirements.txt
playwright install chromium
python3 manage.py migrate
python3 manage.py runserver
# Access at http://127.0.0.1:8000/
```

Alternatively, `python3 navi_launcher.py` starts the server and opens the browser automatically.

## Installation (Windows — development)

```bat
setup.bat
.venv\Scripts\activate
python manage.py migrate
python manage.py runserver
```

## Windows — distributable build

See **[BUILD.md](BUILD.md)** for full instructions. In short:

```bat
build.bat
```

This produces `dist/NAVI_Web/` and `dist/NAVI_Web.zip` — a self-contained executable that requires no Python installation on the end-user machine.

## Configuration

Open **Settings** (⚙ in the top-right corner of the panel) to set:

| Setting | Purpose |
|---|---|
| **Proxy** | Corporate/authenticated HTTP proxy (`http://host:port` + username/password). Leave disabled for direct connections. |
| **Groq API Key** | Required only when AI description mode is enabled. Obtain a free key at [groq.com](https://groq.com/). |

Both values are stored in the Django session and are never written to disk.

## Output files

All output files are written to `~/Downloads/`:

| File | Description |
|---|---|
| `site1_lote_N.xlsx` | Batch spreadsheet for Site 1, run N |
| `relatorio_fotografico_site1_lote_N.docx` | Photo report for Site 1, run N |
| `imoveis_unificados.xlsx` | Consolidated, deduplicated spreadsheet |
| `relatorio_fotografico_consolidado.docx` | Consolidated photo report |

## Adapting to a different site

1. **Site 1** — update `SITE1_BASE_URL` in `scrapers/Site1/site1_scraper.py` and update the CSS selectors inside `_extrair_card` to match the target site's HTML.
2. **Site 2 / Site 3** — update the selectors in `scrapers/shared_scraper.py` (`_extrair_card`) and the description selectors in `_SELETORES_DESC`.
3. If the AI description feature is used, update `_SELETORES_DESC` in `scrapers/Site1/site1_scraper.py` and `scrapers/shared_scraper.py` to match the individual listing pages.

## Project structure

```
scrapers/
├── Site1/site1_scraper.py        # Scraper for Site 1 (visible browser, bot-challenge handling)
├── Site2/site2_scraper.py        # Thin wrapper → shared_scraper.py
├── Site3/site3_scraper.py        # Thin wrapper → shared_scraper.py
├── shared_scraper.py             # Shared scraper for Site 2 and Site 3
├── imoveis_unificados.py         # Spreadsheet consolidation
├── relatorios_unificados.py      # Photo report consolidation
└── common/
    ├── ai_descricao.py           # Groq API — area extraction from description text
    ├── excel.py                  # .xlsx writer
    ├── files.py                  # Batch numbering, Downloads copy
    ├── images.py                 # Photo downloader (requests)
    ├── paths.py                  # Shared paths, Playwright setup
    └── word.py                   # .docx report builder
painel/
├── views.py                      # Django views, job state, scraping thread
├── urls.py
├── apps.py                       # Clears temp dir on startup
└── templates/painel/
    ├── dashboard.html
    └── configuracoes.html
```
