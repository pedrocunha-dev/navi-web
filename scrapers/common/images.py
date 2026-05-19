import os
import requests
from io import BytesIO
from PIL import Image
from urllib.parse import quote

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def _build_proxies(proxy: dict | None) -> dict | None:
    if not proxy:
        return None
    server = proxy.get('server', '').strip()
    if not server:
        return None
    # Garante esquema http:// no início
    if not server.startswith(('http://', 'https://')):
        server = 'http://' + server
    username = (proxy.get('username') or '').strip()
    password = (proxy.get('password') or '').strip()
    if username and password:
        # Escapa caracteres especiais para que a URL do proxy fique válida.
        # safe="" -> escapa tudo, inclusive @ : / # etc.
        user_q = quote(username, safe="")
        pass_q = quote(password, safe="")
        scheme, rest = server.split('://', 1)
        proxy_url = f"{scheme}://{user_q}:{pass_q}@{rest}"
    else:
        proxy_url = server
    return {"http": proxy_url, "https": proxy_url}

def download_image(img_url: str, save_path: str, imovel_idx: int, img_idx: int, timeout: int = 15, proxy: dict | None = None) -> None:
    req_proxies = _build_proxies(proxy)
    try:
        response = requests.get(img_url, proxies=req_proxies, timeout=timeout, verify=False)
        if response.status_code == 200:
            try:
                image = Image.open(BytesIO(response.content)).convert("RGB")
                image.save(save_path, format='JPEG')
                if os.path.exists(save_path) and os.path.getsize(save_path) < 1000:
                    os.remove(save_path)
                    print(f"Imagem removida por tamanho insuficiente: {save_path}")
            except Exception as e:
                print(f"Erro ao processar imagem para {save_path}: {e}")
    except Exception as e:
        print(f"Erro ao baixar imagem {img_idx} do imóvel {imovel_idx}: {e}")
