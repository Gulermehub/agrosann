@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto ready
where py >nul 2>nul
if errorlevel 1 (
    python -m venv .venv
) else (
    py -3 -m venv .venv
)
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
:ready
".venv\Scripts\python.exe" -c "from app import app; from agrosan.db import initialize; ctx=app.app_context(); ctx.push(); initialize() if not app.config['DATABASE_URL'] else None"
if errorlevel 1 goto failed
echo Abra http://127.0.0.1:5001 no navegador.
echo Clique em Criar minha conta para cadastrar seu acesso.
echo A primeira conta de uma instalacao vazia sera administradora.
echo Mantenha esta janela aberta enquanto estiver usando o sistema.
".venv\Scripts\waitress-serve.exe" --listen=127.0.0.1:5001 app:app
goto end
:failed
echo Confira se Python 3.12 ou superior esta instalado e se ha acesso a internet.
pause
:end
