@echo off
setlocal

echo ============================================================
echo  NAVI - Instalacao do ambiente
echo ============================================================
echo.

REM 1. Cria ambiente virtual se nao existir
if not exist .venv (
    echo [1/5] Criando ambiente virtual em .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo ERRO: falha ao criar ambiente virtual.
        exit /b 1
    )
) else (
    echo [1/5] Ambiente virtual ja existe, pulando criacao.
)

REM 2. Ativa o venv
echo [2/5] Ativando ambiente virtual ...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERRO: falha ao ativar o ambiente virtual.
    exit /b 1
)

REM 3. Atualiza pip
echo [3/5] Atualizando pip ...
python -m pip install --upgrade pip

REM 4. Instala dependencias Python
echo [4/5] Instalando dependencias do requirements.txt ...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERRO: falha ao instalar dependencias.
    echo Se voce estiver atras de um proxy corporativo, defina as variaveis:
    echo   set HTTP_PROXY=http://usuario:senha@servidor:porta
    echo   set HTTPS_PROXY=http://usuario:senha@servidor:porta
    echo e rode este script novamente.
    exit /b 1
)

REM 5. Baixa os navegadores do Playwright (Chromium)
echo [5/5] Instalando navegador Chromium para Playwright ...
python -m playwright install chromium
if errorlevel 1 (
    echo AVISO: falha ao baixar o Chromium do Playwright.
    echo Provavelmente um problema de proxy. Veja o README.
)

echo.
echo ============================================================
echo  Instalacao concluida.
echo.
echo  Para usar o NAVI, sempre ative o ambiente virtual antes:
echo    .venv\Scripts\activate
echo.
echo  Depois rode:
echo    python manage.py migrate    (so na primeira vez)
echo    python manage.py runserver
echo ============================================================

endlocal