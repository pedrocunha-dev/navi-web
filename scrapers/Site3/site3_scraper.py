from scrapers.shared_scraper import scrape_shared


def scrape_site3(url, arquivo_caminho, raspar_descricao: bool = False, proxy: dict | None = None, api_key: str | None = None):
    return scrape_shared(url, 'site3', raspar_descricao=raspar_descricao, proxy=proxy, api_key=api_key)
