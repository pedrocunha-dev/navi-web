import ast
import json
import re

from groq import Groq

_SYSTEM_PROMPT = """Você é um especialista em análise de anúncios imobiliários brasileiros.
Dado a descrição de um imóvel e a área exibida no card do anúncio, retorne APENAS um JSON válido com:
{"area_construida": <número em m² ou null>, "area_terreno": <número em m² ou null>}

Regras de interpretação:
- Se a descrição mencionar "área construída", "área da casa", "área privativa", "área útil" → area_construida
- Se mencionar "área do terreno", "área do lote", "área total", "terreno de" → area_terreno
- Presunção padrão: a área do card é construída. Se a descrição indicar o contrário (ex: "terreno de Xm²" onde X é igual à área do card), inverta: area_terreno = área do card, area_construida = valor da descrição.
- Extraia somente valores numéricos em m² (ignorando unidades). Retorne null se não houver informação suficiente.
- Retorne somente o JSON numa única linha. Nenhum texto adicional."""


def _extrair_json(text: str) -> dict:
    cleaned = re.sub(r'```(?:json)?\s*', '', text).strip().strip('`').strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    m = re.search(r'\{[^{}]*\}', cleaned, re.DOTALL)
    if m:
        fragment = m.group(0)
        try:
            return json.loads(fragment)
        except json.JSONDecodeError:
            pass
        py_frag = re.sub(r'\bnull\b', 'None', re.sub(r'\btrue\b', 'True', re.sub(r'\bfalse\b', 'False', fragment)))
        try:
            result = ast.literal_eval(py_frag)
            if isinstance(result, dict):
                return result
        except Exception:
            pass
        quoted = re.sub(r'(?<!["\w])([a-zA-Z_]\w*)(?=\s*:)', r'"\1"', fragment)
        try:
            return json.loads(quoted)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Não foi possível extrair JSON da resposta: {text[:200]!r}")


def analisar_descricao(descricao: str, area_card, api_key: str | None = None, proxy: dict | None = None) -> dict:
    if not descricao or not descricao.strip():
        return {'area_construida': None, 'area_terreno': None}

    if not api_key or not api_key.strip():
        return {'area_construida': None, 'area_terreno': None}

    try:
        # Monta cliente Groq com proxy quando configurado
        client_kwargs = {"api_key": api_key.strip()}
        if proxy and proxy.get('server'):
            import httpx
            from urllib.parse import quote
            server = proxy['server'].strip()
            if not server.startswith(('http://', 'https://')):
                server = 'http://' + server
            username = (proxy.get('username') or '').strip()
            password = (proxy.get('password') or '').strip()
            if username and password:
                user_q = quote(username, safe="")
                pass_q = quote(password, safe="")
                scheme, rest = server.split('://', 1)
                proxy_url = f"{scheme}://{user_q}:{pass_q}@{rest}"
            else:
                proxy_url = server
            # verify=False pela Opção A (proxy corporativo com interceptação TLS)
            http_client = httpx.Client(proxy=proxy_url, verify=False, timeout=60.0)
            client_kwargs["http_client"] = http_client

        client = Groq(**client_kwargs)
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Área no card do anúncio: {area_card} m²\n\nDescrição do imóvel:\n{descricao}"},
            ],
            temperature=0.1,
            max_completion_tokens=2048,
            reasoning_effort="medium",
            stream=False,
        )
        msg = response.choices[0].message
        text = (msg.content or getattr(msg, 'reasoning', None) or "").strip()
        if not text:
            return {'area_construida': None, 'area_terreno': None}
        result = _extrair_json(text)
        return {
            'area_construida': float(result['area_construida']) if result.get('area_construida') is not None else None,
            'area_terreno':    float(result['area_terreno'])    if result.get('area_terreno')    is not None else None,
        }
    except Exception as e:
        print(f"[IA] Falha ao analisar descrição: {e}")
        return {'area_construida': None, 'area_terreno': None}
