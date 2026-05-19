from __future__ import annotations

import re
import shutil
import threading
from pathlib import Path
from typing import Optional

from django.contrib import messages
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

# =========================
# Paths
# =========================
TMP_DIR = Path.home() / "AppData" / "Local" / "NAVI" / "tmp" / "imobiliario"
DOWNLOADS_DIR = Path.home() / "Downloads"

# In-memory job state keyed by session key — cleared on server restart.
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def ensure_dirs() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)


def clear_tmp_dir() -> None:
    ensure_dirs()
    for item in TMP_DIR.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)
        except Exception:
            pass


def latest_file(folder: Path, pattern: str) -> Optional[Path]:
    files = list(folder.glob(pattern))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def session_reset(request: HttpRequest) -> None:
    request.session["can_download"] = False
    request.session["last_site1_xlsx"] = ""
    request.session["last_site1_docx"] = ""
    request.session["last_site2_xlsx"] = ""
    request.session["last_site2_docx"] = ""
    request.session["last_site3_xlsx"] = ""
    request.session["last_site3_docx"] = ""
    request.session["last_unified_xlsx"] = ""
    request.session["last_unified_docx"] = ""
    request.session.modified = True


def copy_tmp_to_downloads(src: Path) -> Path:
    ensure_dirs()
    if not src.exists():
        raise FileNotFoundError(str(src))
    dst = DOWNLOADS_DIR / src.name
    shutil.copy2(src, dst)
    return dst


def stream_file(path: Path) -> FileResponse:
    if not path.exists():
        raise Http404(f"File not found: {path.name}")
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name)


def _proxy_from_session(request: HttpRequest) -> dict | None:
    cfg = request.session.get("proxy_config", {})
    if not cfg.get("enabled"):
        return None
    server = (cfg.get("server") or "").strip()
    if not server:
        return None
    if not server.startswith(("http://", "https://")):
        server = "http://" + server
    result: dict = {"server": server}
    username = (cfg.get("username") or "").strip()
    password = (cfg.get("password") or "").strip()
    if username:
        result["username"] = username
    if password:
        result["password"] = password
    return result


def _groq_key_from_session(request: HttpRequest) -> str | None:
    key = request.session.get("groq_api_key", "").strip()
    return key or None


def _int_post(post, name: str, default: int = 1) -> int:
    try:
        return max(1, int(post.get(name) or default))
    except (ValueError, TypeError):
        return default


def build_page_urls(url: str, site: str, start: int, end: int) -> list[str]:
    start = max(1, start)
    end = max(start, end)
    result = []
    if site == "site1":
        # Site 1 uses path-based pagination: base.html -> base-pagina-N.html
        base = re.sub(r'-pagina-\d+\.html$', '.html', url)
        for p in range(start, end + 1):
            if p == 1:
                result.append(base)
            else:
                result.append(base[:-5] + f'-pagina-{p}.html')
    else:
        # Site 2 and Site 3: query param pagination ?pagina=N
        base = re.sub(r'[?&]pagina=\d+', '', url).rstrip('?&')
        for p in range(start, end + 1):
            if p == 1:
                result.append(base)
            else:
                sep = '&' if '?' in base else '?'
                result.append(f'{base}{sep}pagina={p}')
    return result


def _run_scraping(session_key: str, urls: dict, cancel_event: threading.Event, raspar_descricao: bool = False, proxy: dict | None = None, api_key: str | None = None) -> None:
    erros = []
    session_files: dict[str, str] = {}
    cancelled = False

    def set_status(status: str, current_site: str = "", current_page_num: int = 0, total_pages: int = 0) -> None:
        with _jobs_lock:
            _jobs[session_key]["status"] = status
            _jobs[session_key]["current_site"] = current_site
            _jobs[session_key]["current_page_num"] = current_page_num
            _jobs[session_key]["total_pages"] = total_pages

    set_status("running")

    site1_urls = urls.get("site1", [])
    for i, page_url in enumerate(site1_urls, 1):
        if cancel_event.is_set():
            cancelled = True
            break
        set_status("running", "Site 1", i, len(site1_urls))
        try:
            from scrapers.Site1.site1_scraper import scrape_site1
            scrape_site1(page_url, None, raspar_descricao=raspar_descricao, proxy=proxy, api_key=api_key)
            xlsx = latest_file(TMP_DIR, "site1_lote_*.xlsx")
            docx = latest_file(TMP_DIR, "relatorio_fotografico_site1_lote_*.docx")
            if xlsx is None:
                erros.append(f"Site 1 ({page_url}): no file generated — no listings found or access blocked.")
            else:
                session_files["last_site1_xlsx"] = xlsx.name
                session_files["last_site1_docx"] = docx.name if docx else ""
        except Exception as e:
            erros.append(f"Site 1 ({page_url}): {e}")

    if not cancelled and cancel_event.is_set():
        cancelled = True

    if not cancelled:
        site2_urls = urls.get("site2", [])
        for i, page_url in enumerate(site2_urls, 1):
            if cancel_event.is_set():
                cancelled = True
                break
            set_status("running", "Site 2", i, len(site2_urls))
            try:
                from scrapers.Site2.site2_scraper import scrape_site2
                scrape_site2(page_url, None, raspar_descricao=raspar_descricao, proxy=proxy, api_key=api_key)
                xlsx = latest_file(TMP_DIR, "site2_lote_*.xlsx")
                docx = latest_file(TMP_DIR, "relatorio_fotografico_site2_lote_*.docx")
                if xlsx is None:
                    erros.append(f"Site 2 ({page_url}): no file generated — no listings found or access blocked.")
                else:
                    session_files["last_site2_xlsx"] = xlsx.name
                    session_files["last_site2_docx"] = docx.name if docx else ""
            except Exception as e:
                erros.append(f"Site 2 ({page_url}): {e}")

    if not cancelled and cancel_event.is_set():
        cancelled = True

    if not cancelled:
        site3_urls = urls.get("site3", [])
        for i, page_url in enumerate(site3_urls, 1):
            if cancel_event.is_set():
                cancelled = True
                break
            set_status("running", "Site 3", i, len(site3_urls))
            try:
                from scrapers.Site3.site3_scraper import scrape_site3
                scrape_site3(page_url, None, raspar_descricao=raspar_descricao, proxy=proxy, api_key=api_key)
                xlsx = latest_file(TMP_DIR, "site3_lote_*.xlsx")
                docx = latest_file(TMP_DIR, "relatorio_fotografico_site3_lote_*.docx")
                if xlsx is None:
                    erros.append(f"Site 3 ({page_url}): no file generated — no listings found or access blocked.")
                else:
                    session_files["last_site3_xlsx"] = xlsx.name
                    session_files["last_site3_docx"] = docx.name if docx else ""
            except Exception as e:
                erros.append(f"Site 3 ({page_url}): {e}")

    if cancelled:
        final_status = "cancelled"
    elif erros:
        final_status = "error"
    else:
        final_status = "done"

    with _jobs_lock:
        _jobs[session_key]["status"] = final_status
        _jobs[session_key]["erros"] = erros
        _jobs[session_key]["files"] = session_files


@require_POST
def cancelar_raspagem(request: HttpRequest) -> JsonResponse:
    key = request.session.session_key
    with _jobs_lock:
        job = _jobs.get(key)
    if job and job["status"] in ("starting", "running"):
        job["cancel_event"].set()
    return JsonResponse({"ok": True})


@require_POST
def limpar_tmp(request: HttpRequest) -> HttpResponse:
    clear_tmp_dir()
    session_reset(request)
    messages.success(request, "Temporary folder cleared.")
    return redirect(reverse("dashboard"))


def scraping_status(request: HttpRequest) -> JsonResponse:
    key = request.session.session_key
    with _jobs_lock:
        job = _jobs.get(key)

    if not job:
        return JsonResponse({"status": "idle"})

    if job["status"] in ("done", "error", "cancelled"):
        files = job.get("files", {})
        for k, v in files.items():
            request.session[k] = v
        if files:
            request.session["can_download"] = True
        erros = job.get("erros", [])
        if erros:
            request.session["scrape_erros"] = erros
        if job["status"] == "cancelled":
            request.session["scrape_cancelado"] = True
        request.session.modified = True

    return JsonResponse({
        "status": job["status"],
        "erros": job.get("erros", []),
        "files": job.get("files", {}),
        "current_site": job.get("current_site", ""),
        "current_page_num": job.get("current_page_num", 0),
        "total_pages": job.get("total_pages", 0),
    })


def dashboard(request: HttpRequest) -> HttpResponse:
    ensure_dirs()

    key = request.session.session_key
    with _jobs_lock:
        job = _jobs.get(key) if key else None

    if request.session.get("can_download") and not job:
        session_reset(request)
    elif "can_download" not in request.session:
        session_reset(request)

    if request.method == "POST":
        url_site1 = (request.POST.get("url_site1") or "").strip()
        url_site2 = (request.POST.get("url_site2") or "").strip()
        url_site3 = (request.POST.get("url_site3") or "").strip()

        raspar_descricao = request.POST.get('raspar_descricao') == 'on'

        if not any([url_site1, url_site2, url_site3]):
            messages.error(request, "Enter at least one URL.")
            return redirect(reverse("dashboard"))

        s1_urls = build_page_urls(
            url_site1, "site1",
            _int_post(request.POST, "pagina_inicio_site1"),
            _int_post(request.POST, "pagina_fim_site1"),
        ) if url_site1 else []

        s2_urls = build_page_urls(
            url_site2, "site2",
            _int_post(request.POST, "pagina_inicio_site2"),
            _int_post(request.POST, "pagina_fim_site2"),
        ) if url_site2 else []

        s3_urls = build_page_urls(
            url_site3, "site3",
            _int_post(request.POST, "pagina_inicio_site3"),
            _int_post(request.POST, "pagina_fim_site3"),
        ) if url_site3 else []

        proxy = _proxy_from_session(request)
        api_key = _groq_key_from_session(request)

        clear_tmp_dir()
        session_reset(request)

        if not request.session.session_key:
            request.session.create()

        key = request.session.session_key
        cancel_event = threading.Event()
        with _jobs_lock:
            _jobs[key] = {"status": "starting", "erros": [], "files": {}, "current_site": "", "current_page_num": 0, "total_pages": 0, "cancel_event": cancel_event, "raspar_descricao": raspar_descricao}

        t = threading.Thread(
            target=_run_scraping,
            args=(key, {"site1": s1_urls, "site2": s2_urls, "site3": s3_urls}, cancel_event),
            kwargs={"raspar_descricao": raspar_descricao, "proxy": proxy, "api_key": api_key},
            daemon=True,
        )
        t.start()

        return redirect(reverse("dashboard"))

    if request.session.pop("scrape_cancelado", False):
        messages.warning(request, "Scraping cancelled by user.")
    for erro in request.session.pop("scrape_erros", []):
        messages.error(request, erro)

    scraping_running = bool(job and job["status"] in ("starting", "running"))

    proxy_cfg = request.session.get("proxy_config", {})
    proxy_ativo = bool(proxy_cfg.get("enabled") and proxy_cfg.get("server", "").strip())
    groq_configurada = bool(request.session.get("groq_api_key", "").strip())

    context = {
        "scraping_running": scraping_running,
        "can_download": request.session.get("can_download", False),
        "last_site1_xlsx": request.session.get("last_site1_xlsx", ""),
        "last_site1_docx": request.session.get("last_site1_docx", ""),
        "last_site2_xlsx": request.session.get("last_site2_xlsx", ""),
        "last_site2_docx": request.session.get("last_site2_docx", ""),
        "last_site3_xlsx": request.session.get("last_site3_xlsx", ""),
        "last_site3_docx": request.session.get("last_site3_docx", ""),
        "last_unified_xlsx": request.session.get("last_unified_xlsx", ""),
        "last_unified_docx": request.session.get("last_unified_docx", ""),
        "proxy_ativo": proxy_ativo,
        "groq_configurada": groq_configurada,
    }
    return render(request, "painel/dashboard.html", context)


def configuracoes(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        enabled  = request.POST.get("proxy_enabled") == "on"
        server   = (request.POST.get("proxy_server")   or "").strip()
        username = (request.POST.get("proxy_username")  or "").strip()
        password = (request.POST.get("proxy_password")  or "").strip()

        if enabled and not server:
            messages.error(request, "Enter the proxy server address to enable the proxy.")
            return redirect(reverse("configuracoes"))

        # Detect embedded credentials in the server field (common mistake).
        # Expected format: http://host:port — credentials go in the separate fields.
        if enabled and "@" in server.replace("http://", "").replace("https://", ""):
            messages.error(
                request,
                "The 'Server' field should contain only the address and port "
                "(e.g. http://proxy.company.com:8080). "
                "Use the 'Username' and 'Password' fields for credentials."
            )
            return redirect(reverse("configuracoes"))

        request.session["proxy_config"] = {
            "enabled":  enabled,
            "server":   server,
            "username": username,
            "password": password,
        }

        groq_key = (request.POST.get("groq_api_key") or "").strip()
        request.session["groq_api_key"] = groq_key
        request.session.modified = True

        messages.success(request, "Settings saved.")
        return redirect(reverse("dashboard"))

    proxy_cfg = request.session.get("proxy_config", {})
    context = {
        "proxy_enabled":  proxy_cfg.get("enabled", False),
        "proxy_server":   proxy_cfg.get("server", ""),
        "proxy_username": proxy_cfg.get("username", ""),
        "proxy_password": proxy_cfg.get("password", ""),
        "groq_api_key":   request.session.get("groq_api_key", ""),
        "groq_configurada": bool(request.session.get("groq_api_key", "").strip()),
    }
    return render(request, "painel/configuracoes.html", context)


@require_GET
def download_tmp(request: HttpRequest, filename: str) -> FileResponse:
    src = TMP_DIR / Path(filename).name
    if not src.exists():
        raise Http404(f"File not found in temporary folder: {src.name}")
    dst = copy_tmp_to_downloads(src)
    return stream_file(dst)


@require_POST
def unificar_arquivos(request: HttpRequest) -> HttpResponse:
    erros = []

    try:
        from scrapers.imoveis_unificados import executar_unificacao_planilhas
        executar_unificacao_planilhas()
    except Exception as e:
        erros.append(f"Error consolidating spreadsheets: {e}")

    try:
        from scrapers.relatorios_unificados import gerar_relatorio_fotografico
        gerar_relatorio_fotografico()
    except Exception as e:
        erros.append(f"Error consolidating photo reports: {e}")

    if erros:
        for err in erros:
            messages.error(request, err)
    else:
        messages.success(request, "Consolidation complete! Files are available in the Downloads folder.")

    session_reset(request)
    return redirect(reverse("dashboard"))


@require_GET
def unificar_planilhas(request: HttpRequest) -> FileResponse:
    from scrapers.imoveis_unificados import executar_unificacao_planilhas
    executar_unificacao_planilhas()
    out = DOWNLOADS_DIR / "imoveis_unificados.xlsx"
    if not out.exists():
        raise Http404("Unified spreadsheet was not generated.")
    request.session["last_unified_xlsx"] = out.name
    request.session.modified = True
    clear_tmp_dir()
    return stream_file(out)


@require_GET
def unificar_relatorios(request: HttpRequest) -> FileResponse:
    from scrapers.relatorios_unificados import gerar_relatorio_fotografico
    gerar_relatorio_fotografico()
    out = DOWNLOADS_DIR / "relatorio_fotografico_consolidado.docx"
    if not out.exists():
        raise Http404("Consolidated photo report was not generated.")
    request.session["last_unified_docx"] = out.name
    request.session.modified = True
    return stream_file(out)
