@echo off
rem Avvia CNV (Chi Ni Vidimu) su http://127.0.0.1:8000
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creo l'ambiente Python .venv ...
    python -m venv .venv
    if errorlevel 1 goto error
)

rem Le dipendenze si installano solo la prima volta o dopo una modifica a pyproject.toml
".venv\Scripts\python.exe" -m app.install_check check
if not errorlevel 1 goto start
echo Installo le dipendenze (serve internet) ...
".venv\Scripts\python.exe" -m pip install -q -e ".[dev]"
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m app.install_check mark

:start
rem Se la cartella e' stata spostata, il collegamento sul Desktop perde l'icona: lo ripara
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0crea_collegamento.ps1" -SoloSeSpostato >nul 2>&1
echo.
echo Avvio CNV (Chi Ni Vidimu): il browser si apre da solo su http://127.0.0.1:8000
echo Lascia aperta questa finestra; per chiudere l'app premi Ctrl+C o chiudila.
echo.
".venv\Scripts\python.exe" -m app.launcher
if errorlevel 1 goto error
goto :eof

:error
echo.
echo Qualcosa non ha funzionato: leggi il messaggio qui sopra.
pause
