@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM  NAVI - Build do executavel Windows (PyInstaller, onedir)
REM ============================================================
REM
REM Pre-requisitos na maquina de build:
REM   - Python 3.10+ instalado e no PATH
REM   - Acesso a internet (via proxy corporativo, ver abaixo)
REM
REM Para usar proxy corporativo autenticado, antes de rodar este script:
REM   set HTTP_PROXY=http://usuario:senha@servidor:porta
REM   set HTTPS_PROXY=http://usuario:senha@servidor:porta
REM
REM Saida: dist\NAVI\  (pasta com NAVI.exe + dependencias)
REM        dist\NAVI.zip (mesmo conteudo, zipado para distribuicao)
REM ============================================================

echo ============================================================
echo  NAVI - Build do executavel Windows
echo ============================================================
echo.

REM ------------------------------------------------------------
REM 1. Venv limpa (separada da .venv de desenvolvimento)
REM ------------------------------------------------------------
set BUILD_VENV=.venv-build

if exist %BUILD_VENV% (
    echo [1/6] Removendo venv de build anterior...
    rmdir /S /Q %BUILD_VENV%
)

echo [1/6] Criando venv de build em %BUILD_VENV% ...
python -m venv %BUILD_VENV%
if errorlevel 1 (
    echo ERRO: falha ao criar venv. Python esta no PATH?
    exit /b 1
)

call %BUILD_VENV%\Scripts\activate.bat

REM ------------------------------------------------------------
REM 2. pip + dependencias do projeto + pyinstaller
REM ------------------------------------------------------------
echo [2/6] Atualizando pip ...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo ERRO: falha ao atualizar pip. Cheque proxy ^(HTTP_PROXY/HTTPS_PROXY^).
    exit /b 1
)

echo [3/6] Instalando dependencias do requirements.txt + pyinstaller ...
pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo ERRO: falha ao instalar dependencias.
    echo Se estiver atras de proxy:
    echo   set HTTP_PROXY=http://usuario:senha@servidor:porta
    echo   set HTTPS_PROXY=http://usuario:senha@servidor:porta
    exit /b 1
)

REM ------------------------------------------------------------
REM 3. Baixar Chromium do Playwright em pasta LOCAL ao projeto
REM ------------------------------------------------------------
REM Setamos PLAYWRIGHT_BROWSERS_PATH para .pw-browsers/ dentro do projeto.
REM Assim o navi.spec sabe exatamente onde encontrar o Chromium para empacotar.
echo [4/6] Baixando Chromium do Playwright em .pw-browsers\ ...
set PLAYWRIGHT_BROWSERS_PATH=%CD%\.pw-browsers

if exist .pw-browsers (
    echo       (pasta ja existe, pulando download)
) else (
    python -m playwright install chromium
    if errorlevel 1 (
        echo ERRO: falha ao baixar Chromium do Playwright.
        echo Cheque proxy ^(HTTPS_PROXY^) ^- o download e' HTTPS.
        exit /b 1
    )
)

REM ------------------------------------------------------------
REM 4. Limpar builds antigos do PyInstaller
REM ------------------------------------------------------------
echo [5/6] Limpando build/ e dist/ anteriores ...
if exist build rmdir /S /Q build
if exist dist  rmdir /S /Q dist

REM ------------------------------------------------------------
REM 5. PyInstaller
REM ------------------------------------------------------------
echo [6/6] Rodando PyInstaller ^(pode levar 3-8 minutos^)...
pyinstaller --clean --noconfirm navi.spec
if errorlevel 1 (
    echo.
    echo ERRO: PyInstaller falhou. Veja o log acima.
    exit /b 1
)

REM ------------------------------------------------------------
REM 6. Zipar resultado
REM ------------------------------------------------------------
echo.
echo Gerando dist\NAVI_Web.zip para distribuicao ...
cd dist
powershell -NoProfile -Command "Compress-Archive -Path 'NAVI_Web' -DestinationPath 'NAVI_Web.zip' -Force"
cd ..

echo.
echo ============================================================
echo  BUILD CONCLUIDO
echo ============================================================
echo.
echo  Pasta:   dist\NAVI_Web\         ^(rodar NAVI_Web.exe^)
echo  Zip:     dist\NAVI_Web.zip      ^(para distribuicao^)
echo.
echo  Para testar localmente:
echo    cd dist\NAVI_Web
echo    NAVI_Web.exe
echo.
echo ============================================================

endlocal
