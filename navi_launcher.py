"""
NAVI - Launcher do executavel empacotado pelo PyInstaller.

Responsabilidades:
1. Configurar PYTHONPATH para que Django encontre 'naviweb' e 'painel'
2. Rodar 'migrate' silenciosamente se o banco nao existir
3. Subir o servidor de desenvolvimento Django em thread separada
4. Abrir o navegador padrao do usuario na URL do painel
5. Manter o console aberto para o usuario ver logs e poder cancelar

Em modo dev (sem PyInstaller) este arquivo tambem funciona: roda igual ao
'python manage.py runserver', so que ja abre o browser sozinho.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Forca Python unbuffered o mais cedo possivel: garante que prints, logs do Django
# e mensagens de scrapers aparecem no console em tempo real, em vez de ficarem
# presos no buffer ate o app fechar. Util para debug remoto com usuarios.
os.environ['PYTHONUNBUFFERED'] = '1'
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass


# ============================================================
# Setup de paths
# ============================================================
# Em PyInstaller, sys._MEIPASS aponta para a pasta de recursos extraidos.
# Em dev, usamos o diretorio onde este script vive.
if hasattr(sys, '_MEIPASS'):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent

# Garante que 'naviweb' e 'painel' estao no PYTHONPATH antes do Django importar
sys.path.insert(0, str(BASE_DIR))

# Aponta DJANGO_SETTINGS_MODULE antes de qualquer import do Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'naviweb.settings')

# Forca encoding utf-8 no stdout/stderr para evitar UnicodeEncodeError
# no console do Windows (cp1252 e' default em PT-BR)
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass


# ============================================================
# Constantes
# ============================================================
HOST = '127.0.0.1'
PORT = 8000
URL = f'http://{HOST}:{PORT}/'


def _print_banner() -> None:
    print('=' * 60)
    print(' NAVI - Navegador de Imoveis')
    print('=' * 60)
    print(f' Painel: {URL}')
    print(' Para encerrar: feche esta janela ou Ctrl+C')
    print('=' * 60)
    print()


def _aplicar_migracoes() -> None:
    """Aplica migracoes sempre. E' idempotente -- migracoes ja aplicadas sao no-op
    e custam ~500ms. Mais robusto que checar 'arquivo existe?' porque o runserver
    cria o arquivo vazio na primeira request, deixando a checagem inutil."""
    print('[NAVI] Verificando banco de dados...')
    from django.core.management import call_command
    try:
        call_command('migrate', verbosity=0, interactive=False)
        print('[NAVI] Banco pronto.')
    except Exception as exc:
        print(f'[NAVI] AVISO: falha ao aplicar migracoes: {exc}')


def _abrir_browser_quando_pronto() -> None:
    """Espera o servidor responder antes de abrir o navegador."""
    import urllib.request
    import urllib.error

    for _ in range(40):  # ate ~8s
        try:
            urllib.request.urlopen(URL, timeout=0.5)
            break
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            time.sleep(0.2)

    try:
        webbrowser.open(URL)
    except Exception:
        pass


def main() -> int:
    _print_banner()

    # Setup Django (precisa antes de qualquer import de painel/scrapers)
    import django
    django.setup()

    _aplicar_migracoes()

    # Abre o browser em background depois que o servidor estiver de pe
    threading.Thread(target=_abrir_browser_quando_pronto, daemon=True).start()

    # Sobe o runserver no main thread (bloqueante).
    # use_reloader=False: o reloader spawna subprocesso e quebra no PyInstaller.
    # use_threading=True: permite requisicoes paralelas (status polling + dashboard).
    from django.core.management import call_command
    try:
        call_command(
            'runserver',
            f'{HOST}:{PORT}',
            use_reloader=False,
            use_threading=True,
            verbosity=1,
        )
    except KeyboardInterrupt:
        print('\n[NAVI] Encerrado pelo usuario.')
        return 0
    except Exception as exc:
        print(f'\n[NAVI] ERRO ao subir o servidor: {exc}')
        input('\nPressione ENTER para fechar...')
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
