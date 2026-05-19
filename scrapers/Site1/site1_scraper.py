import os
import re
import sys
import time
import random
from pathlib import Path

from playwright.sync_api import sync_playwright

from scrapers.common.paths import PASTA_TEMP, DOWNLOADS_DIR, setup_playwright_path
from scrapers.common.files import gerar_nome_lote, copiar_para_downloads
from scrapers.common.images import download_image
from scrapers.common.excel import salvar_planilha
from scrapers.common.word import salvar_relatorio_site1

# Base URL of the target site — used to build absolute listing URLs from relative hrefs.
# Update this constant to point to the site you are scraping.
SITE1_BASE_URL = ""

_SELETORES_DESC = [
    '#longDescription',
    '[data-qa="POSTING_DESCRIPTION"]',
    '[class*="wrapper-description"]',
    '[class*="description-content"]',
    'section.article-section-description',
    'div[class*="description"] p',
]


def _human_sleep(min_s: float = 0.8, max_s: float = 2.5) -> None:
    time.sleep(random.uniform(min_s, max_s))


def _is_bot_challenge(page) -> bool:
    """Detects a bot-verification challenge page by title and known selectors."""
    try:
        title = page.title()
        if "Just a moment" in title or "Attention Required" in title:
            return True
        for sel in ["#challenge-form", "#cf-please-wait",
                    ".cf-browser-verification", "iframe[src*='challenges.cloudflare.com']"]:
            if page.query_selector(sel):
                return True
        return False
    except Exception:
        return False


def _aguardar_desafio(page, timeout: int = 90) -> bool:
    """Waits for the user to solve a bot-verification challenge in the visible browser window."""
    print("Bot challenge detected. Solve it in the browser window that opened...")
    start = time.time()
    while time.time() - start < timeout:
        if not _is_bot_challenge(page):
            print("Challenge solved, continuing...")
            _human_sleep(1.5, 2.5)
            return True
        time.sleep(2)
    print("Timed out waiting for challenge to be solved (90s).")
    return False


def _scroll_humano(page) -> None:
    print("Gradual scroll started...")
    previous_height = 0
    sem_mudanca = 0
    while sem_mudanca < 6:
        page.evaluate(f"window.scrollBy(0, {random.randint(400, 900)})")
        _human_sleep(1.5, 3.5)
        current_height = page.evaluate("document.body.scrollHeight")
        if current_height == previous_height:
            sem_mudanca += 1
        else:
            sem_mudanca = 0
        previous_height = current_height
    print("Scroll finished.")
    _human_sleep(1.0, 2.0)


def _navegar_para_url(page, url: str) -> None:
    """Navigates to the URL, handling paginated paths and bot-verification challenges."""
    pagina_match = re.search(r'-pagina-(\d+)\.html$', url)

    if pagina_match:
        # Paginated URL: load page 1 first to establish session, then click to the target page.
        # Navigating directly to a paginated URL can trigger bot detection on some sites.
        pagina_num = pagina_match.group(1)
        url_p1 = re.sub(r'-pagina-\d+', '', url)
        print("Loading page 1 to establish session...")
        page.goto(url_p1, wait_until="domcontentloaded", timeout=60000)
        if _is_bot_challenge(page):
            _aguardar_desafio(page)
        _human_sleep(3.0, 5.0)

        for _ in range(3):
            page.evaluate(f"window.scrollBy(0, {random.randint(400, 700)})")
            _human_sleep(0.8, 1.5)
        page.mouse.move(random.randint(200, 900), random.randint(150, 500))
        _human_sleep(1.0, 2.0)

        print(f"Clicking pagination link for page {pagina_num}...")
        link_pagina = page.query_selector(f'a[href*="pagina-{pagina_num}"]')
        if link_pagina:
            link_pagina.click()
            try:
                page.wait_for_url(f'*pagina-{pagina_num}*', timeout=15000)
            except Exception:
                print(f"URL did not change after click, navigating directly to: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            _human_sleep(1.5, 2.5)
            if _is_bot_challenge(page):
                _aguardar_desafio(page)
        else:
            print(f"Pagination link for page {pagina_num} not found, navigating directly...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if _is_bot_challenge(page):
                _aguardar_desafio(page)
    else:
        print(f"Navigating to: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if _is_bot_challenge(page):
            _aguardar_desafio(page)


def _baixar_fotos_card(page, prop, i: int, pasta_imovel: Path, proxy: dict | None = None) -> None:
    try:
        prop.hover()
        _human_sleep(0.5, 1.2)
    except Exception as e:
        print(f"Error hovering listing {i}: {e}")

    carousel = prop.query_selector('div.flickity-slider')
    carousel_images = carousel.query_selector_all('img') if carousel else []
    for idx_img, img_tag in enumerate(carousel_images[:8], 1):
        img_url = img_tag.get_attribute('src') or img_tag.get_attribute('data-flickity-lazyload')
        if img_url:
            download_image(img_url, str(pasta_imovel / f'foto_{idx_img}.jpg'), i, idx_img, timeout=15, proxy=proxy)


def _baixar_fotos_pagina_individual(page, i: int, pasta_imovel: Path, proxy: dict | None = None) -> None:
    _SELETORES_FOTOS = [
        'img.imageGrid-module__imgProperty___KJ-2G',
        'img[class*="imageGrid-module__imgProperty"]',
        'div[class*="imageGrid-module__grid"] img',
        'div.flickity-slider img',
        'div[class*="carousel"] img',
        'div[class*="gallery"] img',
        '[data-qa*="PHOTO"] img',
    ]
    for selector in _SELETORES_FOTOS:
        imgs = page.query_selector_all(selector)
        if imgs:
            for idx_img, img_tag in enumerate(imgs[:5], 1):
                img_url = (img_tag.get_attribute('src') or
                           img_tag.get_attribute('data-flickity-lazyload') or
                           img_tag.get_attribute('data-src'))
                if img_url and img_url.startswith('http'):
                    download_image(img_url, str(pasta_imovel / f'foto_{idx_img}.jpg'), i, idx_img, timeout=15, proxy=proxy)
            if any((pasta_imovel / f'foto_{n}.jpg').exists() for n in range(1, 6)):
                return


def _extrair_card(page, prop, i: int, pasta_base_imagens: Path, raspar_descricao: bool = False, proxy: dict | None = None) -> dict:
    address_1 = prop.query_selector('.postingLocations-module__location-address')
    address_2 = prop.query_selector('[data-qa="POSTING_CARD_LOCATION"]')
    part1 = address_1.inner_text().strip() if address_1 else ''
    part2 = address_2.inner_text().strip() if address_2 else ''

    if part1 and part2:
        title = f"{part1}, {part2}"
    else:
        title = part2 or part1 or "Address not found"

    def _extrair_num(selector):
        el = prop.query_selector(selector)
        if not el:
            return None
        m = re.search(r'(\d+)', el.inner_text())
        return int(m.group(1)) if m else None

    price_el = prop.query_selector('[data-qa="POSTING_CARD_PRICE"]')
    price    = price_el.inner_text() if price_el else None
    area     = _extrair_num('[data-qa="POSTING_CARD_FEATURES"] span:nth-child(1)')
    bedrooms = _extrair_num('[data-qa="POSTING_CARD_FEATURES"] span:nth-child(2)')
    bathrooms = _extrair_num('[data-qa="POSTING_CARD_FEATURES"] span:nth-child(3)')
    parking  = _extrair_num('[data-qa="POSTING_CARD_FEATURES"] span:nth-child(4)')

    link_el = prop.query_selector('[data-qa="POSTING_CARD_DESCRIPTION"] a')
    if link_el:
        href = link_el.get_attribute('href')
        link = SITE1_BASE_URL + href if href else "Link not found"
    else:
        link = "Link not found"

    pasta_imovel = pasta_base_imagens / f'imovel_{i}'
    pasta_imovel.mkdir(exist_ok=True)

    if not raspar_descricao:
        _baixar_fotos_card(page, prop, i, pasta_imovel, proxy=proxy)

    return {
        'ID': str(i),
        'Endereço': title,
        'Preço': price,
        'Área (m²)': area,
        'Quartos': bedrooms,
        'Banheiros': bathrooms,
        'Vagas de Garagem': parking,
        'Link': link,
        'Caminho na Pasta': str(pasta_imovel),
    }


def _navegar_para_imovel(page, link: str, listing_url: str) -> bool:
    """
    Navigates to an individual listing page. First tries clicking the card link
    (simulates human behaviour). If the click does not cause navigation (e.g. opened
    a new tab), falls back to direct navigation. Returns True if the individual page
    was reached.
    """
    expected_path = link.replace(SITE1_BASE_URL, "").split('?')[0]

    if listing_url not in page.url:
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        if _is_bot_challenge(page):
            _aguardar_desafio(page)
        _human_sleep(2.0, 3.0)

    # Try partial href match — tracking params appended after go_back() break exact matching.
    link_el = page.query_selector(f'a[href*="{expected_path}"]')
    if link_el:
        link_el.scroll_into_view_if_needed()
        _human_sleep(0.5, 1.0)
        link_el.click()
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        _human_sleep(1.0, 1.5)

    # Verify navigation actually happened (click may have opened a new tab).
    if expected_path not in page.url:
        print(f"  → Click did not navigate, accessing directly...")
        page.goto(link, wait_until="domcontentloaded", timeout=40000)
        _human_sleep(1.0, 2.0)

    if _is_bot_challenge(page):
        _aguardar_desafio(page)

    return expected_path in page.url


def _enriquecer_com_descricao(data: list, page, listing_url: str, proxy: dict | None = None, api_key: str | None = None) -> None:
    from scrapers.common.ai_descricao import analisar_descricao
    total = len(data)
    for idx, item in enumerate(data, 1):
        link = item.get('Link', '')
        if not link.startswith('http'):
            item['Área Construída (m²)'] = item.pop('Área (m²)', None)
            item['Área Terreno (m²)'] = None
            item['Descrição'] = ''
            continue

        print(f"[{idx}/{total}] Fetching individual listing for description...")

        descricao = ""
        navegou_individual = False

        try:
            navegou_individual = _navegar_para_imovel(page, link, listing_url)

            if not navegou_individual:
                print(f"  → Could not reach the individual listing page.")
            else:
                page.evaluate("window.scrollBy(0, 600)")
                _human_sleep(0.5, 1.0)

                for selector in _SELETORES_DESC:
                    el = page.query_selector(selector)
                    if el:
                        text = el.inner_text().strip()
                        if text:
                            descricao = text
                            print(f"  → Description extracted ({len(descricao)} chars).")
                            break

                if not descricao:
                    print(f"  → No description found in known selectors.")

                pasta_imovel = Path(item.get('Caminho na Pasta', ''))
                if pasta_imovel.exists():
                    _baixar_fotos_pagina_individual(page, idx, pasta_imovel, proxy=proxy)

        except Exception as e:
            print(f"[Site1] Error accessing {link}: {e}")

        area_card = item.pop('Área (m²)', None)
        analise = analisar_descricao(descricao, area_card, api_key=api_key, proxy=proxy)
        item['Área Construída (m²)'] = analise['area_construida'] if analise['area_construida'] is not None else area_card
        item['Área Terreno (m²)']    = analise['area_terreno']
        item['Descrição']            = descricao
        _human_sleep(0.5, 1.0)

        if navegou_individual:
            try:
                page.go_back(wait_until="domcontentloaded", timeout=30000)
                if _is_bot_challenge(page):
                    _aguardar_desafio(page)
                _human_sleep(1.0, 2.0)
            except Exception:
                pass


def scrape_site1(url, arquivo_caminho, raspar_descricao: bool = False, proxy: dict | None = None, api_key: str | None = None):
    setup_playwright_path()
    PASTA_TEMP.mkdir(parents=True, exist_ok=True)

    arquivo_caminho, lote_numero = gerar_nome_lote('site1')
    pasta_base_imagens = PASTA_TEMP / f"imagens_site1_lote_{lote_numero}"
    pasta_base_imagens.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        print("Starting Chromium browser (visible window)...")
        browser = p.chromium.launch(
            headless=False,
            proxy=proxy,
            args=["--disable-blink-features=AutomationControlled", "--ignore-certificate-errors"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            ignore_https_errors=True,
        )
        page = context.new_page()

        _navegar_para_url(page, url)

        _human_sleep(1.5, 3.0)
        page.mouse.move(random.randint(200, 900), random.randint(150, 500))
        _human_sleep(0.4, 1.0)
        page.mouse.move(random.randint(200, 900), random.randint(150, 500))
        _human_sleep(0.3, 0.8)

        _scroll_humano(page)

        try:
            page.wait_for_selector(
                'div.postingsList-module__card-container div[data-qa="posting PROPERTY"]',
                timeout=15000
            )
        except Exception:
            print("No listings found on page.")
            browser.close()
            return None

        properties = page.query_selector_all(
            'div.postingsList-module__card-container div[data-qa="posting PROPERTY"]'
        )
        print(f"{len(properties)} listings found on page.")

        data = []
        for i, prop in enumerate(properties, 1):
            data.append(_extrair_card(page, prop, i, pasta_base_imagens, raspar_descricao=raspar_descricao, proxy=proxy))

        if raspar_descricao and data:
            print(f"Description mode active: visiting {len(data)} listings individually...")
            _enriquecer_com_descricao(data, page, url, proxy=proxy, api_key=api_key)

        browser.close()

    print(f"Scraping done: {len(data)} listings found.")

    salvar_planilha(data, arquivo_caminho, lote_numero, raspar_descricao=raspar_descricao)
    copiar_para_downloads(Path(arquivo_caminho))

    nome_docx = str(PASTA_TEMP / f"relatorio_fotografico_site1_lote_{lote_numero}.docx")
    salvar_relatorio_site1(data, nome_docx, lote_numero, raspar_descricao=raspar_descricao)
    copiar_para_downloads(Path(nome_docx))

    return (
        str(DOWNLOADS_DIR / Path(arquivo_caminho).name),
        str(DOWNLOADS_DIR / Path(nome_docx).name),
    )
