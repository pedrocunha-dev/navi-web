# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the project

**Dependencies** (Linux):
```
pip3 install -r requirements.txt
playwright install chromium
```

**Django web panel** (Linux development):
```
python3 manage.py migrate   # first-time setup only
python3 manage.py runserver
# Access at http://127.0.0.1:8000/
```

Alternatively, `python3 navi_launcher.py` starts the server and opens the browser automatically. `use_reloader=False` is hardcoded there — do not change it, the reloader breaks PyInstaller bundles.

**Running a scraper directly** (for testing):
```python
import sys; sys.path.insert(0, '.')
from scrapers.Site1.site1_scraper import scrape_site1
scrape_site1('https://...', None)

from scrapers.Site2.site2_scraper import scrape_site2
scrape_site2('https://...', None)

# Second arg (arquivo_caminho) is always None — scrapers generate filenames internally via gerar_nome_lote()
# Optional kwargs: proxy={'server':..., 'username':..., 'password':...}, api_key='gsk_...'
```

## Windows build / packaging

The project is distributed to end users as a self-contained Windows executable built with PyInstaller.

**Entry point**: `navi_launcher.py` (not `manage.py`). It sets up paths, runs migrations, opens the browser, and starts `runserver` — all in one shot.

**Build** (run on Windows only):
```bat
build.bat          # no proxy
set HTTP_PROXY=http://user:pass@server:port && build.bat   # with proxy
```

`build.bat` creates an isolated `.venv-build/`, installs deps, downloads Chromium to `.pw-browsers/` (inside the project), then runs `pyinstaller navi.spec`. Output is `dist/NAVI_Web/` and `dist/NAVI_Web.zip`.

**`navi.spec`** bundles:
- `painel/templates/` and `painel/static/` → root of bundle (Django finds them via `sys._MEIPASS`)
- `.pw-browsers/` → `ms-playwright/` (Playwright locates Chromium via `setup_playwright_path()` in `scrapers/common/paths.py`)
- Metadata for `django`, `groq`, `pydantic`, etc. (needed by `importlib.metadata` at runtime)

If `ModuleNotFoundError` occurs in the packaged `.exe`, add the missing module to `hiddenimports` in `navi.spec` and rebuild.

**`naviweb/settings.py` dual-mode paths**: when running packaged, `BASE_DIR = Path(sys._MEIPASS)` (read-only bundle). User-writable data (SQLite DB, sessions) goes to `NAVI_USER_DIR = Path.home() / "AppData" / "Local" / "NAVI"`, which is separate from `BASE_DIR`. Do not write runtime data relative to `BASE_DIR` in the packaged version.

## Project overview

NAVI automates scraping, consolidation, and report generation for real estate listings. The interface is a Django web panel backed by a shared scraper layer.

## Architecture

### Shared scraper layer (`scrapers/`)

Each scraper loads the listing page, scrolls to trigger lazy-loaded cards, extracts data, downloads photos, and writes two output files per run:
- `<site>_lote_N.xlsx` — structured data spreadsheet
- `relatorio_fotografico_<site>_lote_N.docx` — Word report with photos

Files are saved to the temp dir and also copied directly to `~/Downloads` by the scraper itself.

**Temp dir** (Windows): `%LOCALAPPDATA%\NAVI\tmp\imobiliario\`
**Temp dir** (Linux): `~/AppData/Local/NAVI/tmp/imobiliario/` (same `Path.home()` logic, non-standard path on Linux)

**Batch numbering**: each scraper calls `gerar_nome_lote(site_slug)` at the start (before the scraping loop), which returns `(xlsx_path, lote_numero)` by scanning `PASTA_TEMP` for the next free slot. This same number is then used for the image folder (`imagens_<site>_lote_<N>/`) and the docx name. All three scrapers follow this pattern — do not hardcode `lote_1` anywhere.

**Temp dir is cleared on startup**: `painel/apps.py` `PainelConfig.ready()` deletes all contents of TMP_DIR when Django initializes, before the first request.

**`views.py` defines its own `TMP_DIR`** (`Path.home() / "AppData" / "Local" / "NAVI" / "tmp" / "imobiliario"`) rather than importing `PASTA_TEMP` from `scrapers.common.paths`. Both resolve to the same path, but they are not the same object — if you change the path in one place, update the other too.

### Shared scraper utilities (`scrapers/common/`)

- `paths.py` — `PASTA_TEMP`, `DOWNLOADS_DIR`, `get_resource_path()` (PyInstaller-aware, safe no-op outside PyInstaller), `setup_playwright_path()`
- `files.py` — `gerar_nome_lote(site_slug)` returns `(xlsx_path, lote_numero)`; `copiar_para_downloads()` copies a file to `~/Downloads`
- `excel.py` — `salvar_planilha(data, path, lote_numero, raspar_descricao=False)` writes the formatted `.xlsx`. Normal mode: 10 columns with `Área (m²)`. Description mode: 12 columns — replaces `Área (m²)` with `Área Construída (m²)` + `Área Terreno (m²)` and appends `Descrição`. `Preço Unit. (R$/m²)` uses `Área Construída (m²)` as base when in description mode.
- `images.py` — `download_image(url, save_path, imovel_idx, img_idx, timeout=15, proxy=None)` fetches a photo via `requests`. The `proxy` parameter is a dict `{server, username, password}` or `None`.
- `word.py` — `salvar_relatorio_shared()` and `salvar_relatorio_site1()` build the `.docx` photo reports. The document header reads `"[Organization]\n[Department]\n"` — edit those strings directly to customise the report header.
- `ai_descricao.py` — `analisar_descricao(descricao, area_card, api_key=None) -> dict` — calls the Groq API (model `openai/gpt-oss-120b`) to extract `area_construida` and `area_terreno`. Returns `{'area_construida': None, 'area_terreno': None}` silently if `api_key` is absent, empty, or on API failure.

### Proxy and API key — runtime configuration

**No static config files.** Both the proxy and the Groq API key are provided at runtime by the user via the web interface (`/configuracoes/`) and stored in the Django session.

All scraper public functions accept `proxy: dict | None = None` and `api_key: str | None = None`. These are read from the session in `views.py` and passed down the full call chain:

```
dashboard POST
  → _proxy_from_session(request)  →  proxy dict or None
  → _groq_key_from_session(request)  →  str or None
  → _run_scraping(..., proxy=proxy, api_key=api_key)
      → scrape_site1 / scrape_site2 / scrape_site3
          → chromium.launch(proxy=proxy)
          → download_image(..., proxy=proxy)
          → _enriquecer_com_descricao(..., proxy=proxy, api_key=api_key)
              → analisar_descricao(descricao, area_card, api_key=api_key)
```

`scrapers/config.py` exists but is not imported by the scrapers — kept only as a reference placeholder.

### Site 1 (`scrapers/Site1/site1_scraper.py`)

Uses **Playwright Chromium** with `headless=False` (visible window) and `--disable-blink-features=AutomationControlled`. The browser must stay visible so the user can solve bot-verification challenges if they appear.

**Bot-challenge handling**: After every `page.goto(...)`, the scraper calls `_is_bot_challenge(page)`. If a challenge is detected, `_aguardar_desafio(page, timeout=90)` polls every 2 seconds for up to 90 seconds waiting for the user to solve the challenge in the visible browser window.

**Additional human-simulation**: random delays (`_human_sleep`), variable scroll increments, mouse movement before scrolling, hover simulation on each property card before accessing its photo carousel.

**Card container selector**: `div.postingsList-module__card-container div[data-qa="posting PROPERTY"]`. If the listing page renders but no cards are found, this is the selector to check first.

**Field selectors** use `[data-qa="..."]` without a tag prefix to survive future tag changes. If fields come back empty after a site update, inspect the live page HTML and update the selectors inside the `for i, prop in enumerate(properties)` loop.

**`SITE1_BASE_URL`**: constant at the top of `site1_scraper.py` — set this to the base URL of the target site (e.g. `https://www.example.com`). It is prepended to relative `href` paths extracted from listing cards.

**Paginated URLs** (`-pagina-N.html`): navigating directly to these URLs can trigger bot detection. The scraper detects the pattern, loads page 1 first, performs a partial scroll, then clicks the pagination link for the target page (SPA navigation — no full page reload). Page 1 URLs are loaded directly.

**Scraper silent failure**: if the bot challenge does not resolve within 90 seconds, the scraper returns `None` without raising. `_run_scraping` in `views.py` detects this (no xlsx file in TMP_DIR after the call) and adds an error message.

### Site 2 and Site 3 (`scrapers/Site2/`, `scrapers/Site3/`, `scrapers/shared_scraper.py`)

Both sites share identical HTML. `scrapers/Site2/site2_scraper.py` and `scrapers/Site3/site3_scraper.py` are single-function thin wrappers that delegate entirely to `scrapers/shared_scraper.py:scrape_shared(url, site_slug, ...)`. All scraping logic lives in `shared_scraper.py`.

`scrape_shared` uses **Playwright** (`sync_playwright`, `headless=True`). It navigates directly to the URL passed and uses a scroll loop (`max_retries=5`, `time.sleep(1)`) to lazy-load all cards on that single page. Key selectors:

| Field | Selector |
|---|---|
| Cards | `a.olx-core-surface` |
| Location h2 | `h2[data-cy="rp-cardProperty-location-txt"]` |
| Street / address | `p[data-cy="rp-cardProperty-street-txt"]` |
| Price | `div[data-cy="rp-cardProperty-price-txt"] p` |
| Area | `li[data-cy="rp-cardProperty-propertyArea-txt"] h3` |
| Bedrooms | `li[data-cy="rp-cardProperty-bedroomQuantity-txt"] h3` |
| Bathrooms | `li[data-cy="rp-cardProperty-bathroomQuantity-txt"] h3` |
| Parking | `li[data-cy="rp-cardProperty-parkingSpacesQuantity-txt"] h3` |
| Photo carousel | `div.olx-core-carousel__container img` |

**Address assembly logic**: The `h2[data-cy="rp-cardProperty-location-txt"]` contains a `<span>` with the property-type description (discarded) and a text node that is either "Neighbourhood, City" or a condo name. The `p[data-cy="rp-cardProperty-street-txt"]` may be just a street name or a full "Street, Neighbourhood, City" string. Final address: use `street_p` as base; if the h2 text node contains a comma and is not already present in `street_p`, append it.

### AI description scraping mode (`raspar_descricao`)

All three scrapers accept `raspar_descricao: bool = False`. When `True`, after extracting all listing cards, the scraper keeps the browser open and visits each individual listing URL to read its full description. The description is then sent to `analisar_descricao()`.

**Flow inside each scraper:**
1. Extract all cards into plain Python dicts (with `Área (m²)` key).
2. For each item: navigate to the individual listing page, extract the description, download photos. Site 2/3 opens a second Chromium browser (`headless=False`) and navigates listing-to-listing (no `go_back()`). Site 1 stays in the same Chromium session and calls `page.go_back()` between listings.
3. Calls `analisar_descricao(descricao, area_card, api_key=api_key)`, pops `Área (m²)`, and sets `Área Construída (m²)`, `Área Terreno (m²)`, `Descrição`. If no `api_key` is set, areas come back as `None` (silent no-op).
4. Passes `raspar_descricao=True` to `salvar_planilha` to emit the 12-column layout.

**Site 1 individual-page navigation** (`_navegar_para_imovel`): first tries clicking the listing card link using `a[href*="{path}"]` (partial match — tracking params change after `go_back()`). After the click, verifies `page.url` actually changed. If not, falls back to `page.goto(link)`.

**Site 2/3 individual-page navigation** (`_enriquecer_com_descricao` in `shared_scraper.py`): the first Chromium browser (headless) is closed before this phase. A second browser (`headless=False`, `--disable-blink-features=AutomationControlled`) loads the search results page first to establish a session, then navigates directly to each listing URL.

**Description selectors — Site 2 / Site 3** (individual listing pages):
```python
_SELETORES_DESC = [
    '[data-testid="description-content"]',
    'p.description__content--text',
    '[data-cy="ldp-TextCollapse"] p',
]
```

**Description selectors — Site 1** (individual listing pages):
```python
_SELETORES_DESC = [
    '#longDescription',
    '[data-qa="POSTING_DESCRIPTION"]',
    '[class*="wrapper-description"]',
    '[class*="description-content"]',
    'section.article-section-description',
    'div[class*="description"] p',
]
```

If selectors stop working after a site redesign, inspect the individual listing HTML and update these lists in `shared_scraper.py` and `site1_scraper.py` respectively.

**Unification impact**: `executar_unificacao_planilhas()` normalises before concat — drops `Descrição` and renames `Área Construída (m²)` → `Área (m²)` for batches produced in description mode, so mixed batches merge cleanly.

### Consolidation pipeline

After individual scrapes, "Consolidate files" triggers both scripts in sequence:
- `scrapers/imoveis_unificados.py` — concatenates all `.xlsx` files, cleans prices/areas, deduplicates by (price, area), filters out listings without photos, writes `~/Downloads/imoveis_unificados.xlsx` and an intermediate `planilha_geral_preliminar.xlsx` in the temp dir.
- `scrapers/relatorios_unificados.py` — reads `planilha_geral_preliminar.xlsx` and builds `~/Downloads/relatorio_fotografico_consolidado.docx`. Site 1 listings use a 2×4 image grid; Site 2/3 use a 2×3 grid with the third row merged. **This script deletes the entire temp dir at the end** (`shutil.rmtree`).

### Page range scraping

The Django panel accepts a start/end page range per site. `build_page_urls(url, site, start, end)` in `views.py` constructs the full list of page URLs:
- **Site 1**: path-based — page 1 is `base.html`, page N is `base-pagina-N.html` (strips any existing `-pagina-N` suffix first).
- **Site 2 / Site 3**: query-param — page 1 is the base URL, page N appends `?pagina=N`.

`_run_scraping` iterates the list sequentially, calling the scraper once per page. Each call auto-increments the batch number, producing `lote_1`, `lote_2`, … files that are all merged by "Consolidate files".

### Web panel architecture

**`painel/`** — Django app (`naviweb/` project). Scrapers run in a `threading.Thread` to avoid blocking the HTTP request. Job state is tracked in the module-level `_jobs` dict in `views.py` (in-memory, keyed by Django session key — clears on server restart). The frontend polls `GET /status/` every 3 seconds and reloads when the job finishes.

### Django web panel — job state and cancellation

Each job in `_jobs` carries:
```python
{
    "status": "starting" | "running" | "done" | "error" | "cancelled",
    "erros": [...],
    "files": {...},
    "current_site": str,       # e.g. "Site 1"
    "current_page_num": int,   # 1-based index within the site's URL list
    "total_pages": int,
    "cancel_event": threading.Event,
}
```

`_run_scraping` checks `cancel_event.is_set()` before each page URL **and** between each site block. Cancellation takes effect at the next inter-page or inter-site boundary — it cannot interrupt a browser session mid-execution.

### Django web panel — session and state

Session keys used by the application:

| Key | Type | Purpose |
|---|---|---|
| `can_download` | bool | Gates "Consolidate files" and "Clear temp files" buttons |
| `last_site1_xlsx/docx` | str | Filename of most recent output for Site 1 |
| `last_site2_xlsx/docx` | str | Filename of most recent output for Site 2 |
| `last_site3_xlsx/docx` | str | Filename of most recent output for Site 3 |
| `scrape_erros` | list | Error messages consumed on next dashboard GET |
| `scrape_cancelado` | bool | Flag consumed on next dashboard GET |
| `proxy_config` | dict | `{enabled, server, username, password}` — set via `/configuracoes/` |
| `groq_api_key` | str | Groq API key — set via `/configuracoes/` |

`session_reset()` clears `can_download` and all `last_*` keys. It does **not** clear `proxy_config` or `groq_api_key`.

### Static files

Icons (`excel_icon.png`, `word_icon.png`) live in `painel/static/painel/img/`. When adding new image assets for the web panel, copy them to `painel/static/painel/img/` and reference them with `{% static 'painel/img/<filename>' %}`.

### Django URL map (`painel/`)

| Method | Path | View | Purpose |
|---|---|---|---|
| POST | `/` | `dashboard` | Start scraping (background thread) |
| GET | `/` | `dashboard` | Render dashboard |
| GET | `/status/` | `scraping_status` | Polling endpoint (JSON) |
| POST | `/cancelar/` | `cancelar_raspagem` | Signal cancellation (returns JSON) |
| POST | `/unificar/` | `unificar_arquivos` | Run both consolidation scripts |
| GET | `/unificar/planilhas/` | `unificar_planilhas` | Run spreadsheet consolidation only |
| GET | `/unificar/relatorios/` | `unificar_relatorios` | Run report consolidation only |
| POST | `/limpar-tmp/` | `limpar_tmp` | Delete temp dir contents |
| GET | `/download/<filename>/` | `download_tmp` | Copy from temp to Downloads and stream |
| GET/POST | `/configuracoes/` | `configuracoes` | Proxy and Groq API key settings |
