# Empacotamento do NAVI (Windows)

Como gerar o executável Windows do NAVI a partir do código-fonte.

## Pré-requisitos na máquina de build

- Windows 10/11
- Python 3.10 ou superior, com `python` disponível no `PATH`
- Acesso à internet (direto ou via proxy corporativo)
- ~3 GB livres em disco (venv + builds intermediários)

## Build em uma linha

Numa máquina sem proxy:
```bat
build.bat
```

Numa máquina com proxy corporativo autenticado:
```bat
set HTTP_PROXY=http://usuario:senha@servidor:porta
set HTTPS_PROXY=http://usuario:senha@servidor:porta
build.bat
```

> Caracteres especiais na senha (`@`, `:`, `/`, `#`) precisam ser URL-encoded. Ex.: `p@ss` vira `p%40ss`.

O script faz:

1. Cria venv isolada em `.venv-build/`
2. Instala dependências do `requirements.txt` + `pyinstaller`
3. Baixa o Chromium do Playwright em `.pw-browsers/` (dentro do projeto)
4. Limpa builds antigos
5. Roda `pyinstaller navi.spec`
6. Zipa `dist/NAVI_Web/` em `dist/NAVI_Web.zip`

Tempo total: **5–10 minutos** numa máquina decente.

## O que é entregue

```
dist/
├── NAVI_Web/                 # pasta para distribuir
│   ├── NAVI_Web.exe          # executável
│   ├── python313.dll
│   └── _internal/            # libs, Chromium, templates, etc
└── NAVI_Web.zip              # mesmo conteúdo, pronto para enviar
```

Tamanho esperado:
- `dist/NAVI_Web/` descomprimido: ~300–350 MB
- `dist/NAVI_Web.zip`: ~120–150 MB

## Distribuição para os usuários finais

1. Enviar `NAVI_Web.zip` (e-mail, share, link de download)
2. Usuário descompacta numa pasta com permissão de escrita (Desktop, Documentos, etc — **não** precisa ser Program Files)
3. Duplo clique em `NAVI_Web.exe`
4. Janela de console abre, Django sobe, o navegador padrão abre em `http://127.0.0.1:8000/`
5. Para encerrar: fechar a janela do console

**Não é necessário Python, Playwright, nem qualquer instalação prévia.** Tudo está embutido.

## Dados do usuário

O NAVI cria/usa as seguintes pastas no perfil do usuário (não no `.exe`):

| Pasta | Conteúdo |
|---|---|
| `%LOCALAPPDATA%\NAVI\db.sqlite3` | Banco de dados Django (sessões, etc) |
| `%LOCALAPPDATA%\NAVI\tmp\imobiliario\` | Arquivos temporários de raspagem (limpos a cada execução) |
| `%USERPROFILE%\Downloads\` | Saídas finais (planilhas e relatórios) |

Isso significa que mover/copiar a pasta `NAVI_Web/` para outro local não perde dados — eles ficam no perfil do usuário.

## Troubleshooting

### "ModuleNotFoundError" ao executar o `.exe`

PyInstaller perdeu um import dinâmico. Adicione o módulo em `navi.spec` na lista `hiddenimports`:

```python
hiddenimports += ['nome_do_modulo_faltante']
```

E reconstrua.

### Antivírus bloqueia o `.exe`

Possíveis ações:
- **Adicionar a pasta `dist\NAVI_Web\` à exclusão** do antivírus do usuário (precisa de admin no antivírus, não no Windows)
- **Assinar o executável** com certificado de code-signing (resolve falsos-positivos do Defender / SmartScreen, mas tem custo)
- Verificar que UPX continua **desligado** no `navi.spec` (UPX é a causa mais comum de falso-positivo)

### Falha em baixar o Chromium ("403", "connection timed out")

Confirme as variáveis de proxy estão setadas com sintaxe correta. Teste antes de rodar `build.bat`:

```bat
python -c "import urllib.request; print(urllib.request.urlopen('https://playwright.azureedge.net').status)"
```

Se isso falhar, o build inteiro falha. Resolver o proxy primeiro.

### O executável abre mas o painel não responde no navegador

1. Olhar a janela de console — se houver `[Errno 10048]` ou similar, a porta 8000 está em uso. Encerrar outro processo na porta 8000 ou alterar `PORT` em `navi_launcher.py`.
2. Se aparecer erro de Django (`OperationalError: no such table`), apagar `%LOCALAPPDATA%\NAVI\db.sqlite3` e reabrir o NAVI (será recriado).

### Site 1 scraper does not open a visible window

With headless=False, the bundled Chromium **must** open a window. If it doesn't:
1. Verificar que `.pw-browsers/chromium-*/` foi incluído no bundle. Inspecionar `dist\NAVI_Web\_internal\ms-playwright\` — precisa ter a pasta `chromium-XXXX/chrome-win/chrome.exe`.
2. Se faltar, refazer build a partir do passo 3 do `build.bat`.

### "Failed to load Python DLL"

Falta runtime do Visual C++ na máquina do usuário. Instalar **Microsoft Visual C++ Redistributable 2015–2022 (x64)** uma vez, e o NAVI funciona dali em diante. Esse é um pré-requisito do Python embarcado pelo PyInstaller, não tem como evitar.

## Atualização do NAVI

Quando o código mudar e for preciso reempacotar:

```bat
build.bat
```

O script já limpa builds antigos. Se quiser pular o redownload do Chromium (que é o passo mais demorado), basta **não deletar** a pasta `.pw-browsers/` entre builds — o script detecta e pula.

Para forçar redownload:
```bat
rmdir /S /Q .pw-browsers
build.bat
```
