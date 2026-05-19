"""
Shared scraper for Site 2 and Site 3.

Both sites share the same HTML structure — identical data-cy selectors,
identical carousel structure, and identical scroll behaviour.
"""
import os
import random
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from scrapers.common.paths import PASTA_TEMP, DOWNLOADS_DIR, setup_playwright_path
from scrapers.common.files import gerar_nome_lote, copiar_para_downloads
from scrapers.common.images import download_image
from scrapers.common.excel import salvar_planilha
from scrapers.common.word import salvar_relatorio_shared

_SELETORES_DESC = [
    '[data-testid="description-content"]',
    'p.description__content--text',
    '[data-cy="ldp-TextCollapse"] p',
]


def _human_sleep(min_s: float = 0.8, max_s: float = 2.5) -> None:
    time.sleep(random.uniform(min_s, max_s))


def _scroll_ate_carregar(page) -> None:
    previous_count = 0
    same_count_retries = 0
    print("Scrolling to load all listings...")
    while same_count_retries < 5:
        page.evaluate("window.scrollBy(0, 1500)")
        time.sleep(1)
        page.wait_for_timeout(500)
        current_count = len(page.query_selector_all('a.olx-core-surface'))
        if current_count == previous_count:
            same_count_retries += 1
        else:
            same_count_retries = 0
        previous_count = current_count
    print(f"Scroll finished with {previous_count} listings visible.")
    time.sleep(2)


def _extrair_li(prop, selector: str) -> str:
    el = prop.query_selector(selector)
    if not el:
        return '-'
    prefix = el.query_selector('span.sr-only')
    text = el.inner_text()
    if prefix:
        text = text.replace(prefix.inner_text(), '').strip()
    text = text.replace("²", "")
    return ''.join(filter(str.isdigit, text)) or '-'


def _extrair_card(prop, imovel_num: int, pasta_base_imagens: Path, proxy: dict | None = None) -> dict:
    location_h2 = prop.query_selector('h2[data-cy="rp-cardProperty-location-txt"]')
    street_p    = prop.query_selector('p[data-cy="rp-cardProperty-street-txt"]')

    location = ""
    if location_h2:
        span = location_h2.query_selector('span')
        full = location_h2.inner_text().strip()
        if span:
            full = full.replace(span.inner_text().strip(), '').strip()
        location = full

    street = street_p.inner_text().strip() if street_p else ""
    if street:
        title = f"{street}, {location}" if ',' in location and location not in street else street
    else:
        title = location or 'Address not found'

    price_div = prop.query_selector('div[data-cy="rp-cardProperty-price-txt"]')
    price_p   = price_div.query_selector('p') if price_div else None
    price     = price_p.inner_text() if price_p else 'Price not found'

    area      = _extrair_li(prop, 'li[data-cy="rp-cardProperty-propertyArea-txt"] h3')
    bedrooms  = _extrair_li(prop, 'li[data-cy="rp-cardProperty-bedroomQuantity-txt"] h3')
    bathrooms = _extrair_li(prop, 'li[data-cy="rp-cardProperty-bathroomQuantity-txt"] h3')
    parking   = _extrair_li(prop, 'li[data-cy="rp-cardProperty-parkingSpacesQuantity-txt"] h3')

    href = prop.get_attribute("href")
    link = href or "Link not found"

    pasta_imovel = pasta_base_imagens / f'imovel_{imovel_num}'
    pasta_imovel.mkdir(exist_ok=True)

    carousel = prop.query_selector('div.olx-core-carousel__container')
    carousel_images = carousel.query_selector_all('img') if carousel else []
    for idx_img, img_tag in enumerate(carousel_images, 1):
        img_url = img_tag.get_attribute('src')
        if img_url:
            save_path = str(pasta_imovel / f'foto_{idx_img}.jpg')
            download_image(img_url, save_path, imovel_num, idx_img, proxy=proxy)

    return {
        'ID': str(imovel_num),
        'Endereço': title,
        'Preço': price,
        'Área (m²)': area,
        'Quartos': bedrooms,
        'Banheiros': bathrooms,
        'Vagas de Garagem': parking,
        'Link': link,
        'Caminho na Pasta': str(pasta_imovel),
    }


def _enriquecer_com_descricao(data: list, listing_url: str, proxy: dict | None = None, api_key: str | None = None) -> None:
    from scrapers.common.ai_descricao import analisar_descricao
    total = len(data)

    with sync_playwright() as p_cf:
        cf_browser = p_cf.chromium.launch(
            headless=False,
            proxy=proxy,
            args=["--disable-blink-features=AutomationControlled", "--ignore-certificate-errors"],
        )
        cf_context = cf_browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            ignore_https_errors=True,
        )
        cf_page = cf_context.new_page()

        # Load the search results page first to establish a session with the domain.
        print("  [Chromium] Loading search results page to establish session...")
        cf_page.goto(listing_url, timeout=60000, wait_until="domcontentloaded")
        _human_sleep(2.0, 3.0)

        for idx, item in enumerate(data, 1):
            link = item.get('Link', '')
            if not link.startswith('http'):
                item['Área Construída (m²)'] = item.pop('Área (m²)', '-')
                item['Área Terreno (m²)'] = None
                item['Descrição'] = ''
                continue

            print(f"[{idx}/{total}] Fetching listing for description: {link[:60]}...")

            descricao = ""
            try:
                cf_page.goto(link, timeout=30000, wait_until="domcontentloaded")
                _human_sleep(1.5, 2.5)
                cf_page.evaluate("window.scrollBy(0, 600)")

                print(f"  → Page loaded: {cf_page.url[:70]}")

                combined = ", ".join(_SELETORES_DESC)
                try:
                    cf_page.wait_for_selector(combined, timeout=8000)
                except Exception:
                    pass

                for selector in _SELETORES_DESC:
                    el = cf_page.query_selector(selector)
                    if el:
                        try:
                            text = el.inner_text().strip()
                            if text:
                                descricao = text
                                print(f"  → Description extracted ({len(descricao)} chars).")
                                break
                        except Exception:
                            continue

                if not descricao:
                    print(f"  → No description found.")

            except Exception as e:
                print(f"[Scraper] Error accessing {link}: {e}")

            area_card = item.pop('Área (m²)', '-')
            analise = analisar_descricao(descricao, area_card, api_key=api_key, proxy=proxy)
            item['Área Construída (m²)'] = analise['area_construida'] if analise['area_construida'] is not None else area_card
            item['Área Terreno (m²)']    = analise['area_terreno']
            item['Descrição']            = descricao

        cf_browser.close()


def scrape_shared(url: str, site_slug: str, raspar_descricao: bool = False, proxy: dict | None = None, api_key: str | None = None) -> tuple[str, str] | None:
    """
    Scrapes a search results page.

    Args:
        url:              Search results page URL.
        site_slug:        Site identifier ('site2' or 'site3').
        raspar_descricao: When True, visits each listing individually to extract
                          the description for AI-based area analysis.

    Returns:
        Tuple (xlsx_path_in_downloads, docx_path_in_downloads) or None on failure.
    """
    setup_playwright_path()
    PASTA_TEMP.mkdir(parents=True, exist_ok=True)

    arquivo_caminho, lote_numero = gerar_nome_lote(site_slug)
    pasta_base_imagens = PASTA_TEMP / f"imagens_{site_slug}_lote_{lote_numero}"
    pasta_base_imagens.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        print("Starting Chromium browser...")
        browser = p.chromium.launch(
            headless=True,
            proxy=proxy,
            args=["--ignore-certificate-errors"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/119.0.0.0 Safari/537.36"
            ),
            ignore_https_errors=True,
        )
        page = context.new_page()

        print(f"Navigating to: {url}")
        page.goto(url, timeout=60000, wait_until="domcontentloaded")

        _scroll_ate_carregar(page)

        page.wait_for_selector('a.olx-core-surface', timeout=10000)
        properties = page.query_selector_all('a.olx-core-surface')

        data = []
        imovel_num = 0
        for prop in properties:
            if not prop.query_selector('h2[data-cy="rp-cardProperty-location-txt"]') and \
               not prop.query_selector('p[data-cy="rp-cardProperty-street-txt"]'):
                continue
            imovel_num += 1
            data.append(_extrair_card(prop, imovel_num, pasta_base_imagens, proxy=proxy))

        browser.close()

    print(f"Scraping done: {imovel_num} listings found.")

    if raspar_descricao and data:
        print(f"Description mode active: visiting {len(data)} listings individually...")
        _enriquecer_com_descricao(data, url, proxy=proxy, api_key=api_key)

    salvar_planilha(data, arquivo_caminho, lote_numero, raspar_descricao=raspar_descricao)
    copiar_para_downloads(Path(arquivo_caminho))

    nome_docx = str(PASTA_TEMP / f"relatorio_fotografico_{site_slug}_lote_{lote_numero}.docx")
    salvar_relatorio_shared(data, nome_docx, lote_numero)
    copiar_para_downloads(Path(nome_docx))

    return (
        str(DOWNLOADS_DIR / Path(arquivo_caminho).name),
        str(DOWNLOADS_DIR / Path(nome_docx).name),
    )
