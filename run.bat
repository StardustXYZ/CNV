@echo off
rem Avvia CNV (Chi Ni Vidimu) su http://127.0.0.1:8000
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creo l'ambiente Python .venv ...
    python -m venv .venv
    if errorlevel 1 goto error
)

echo Controllo le dipendenze ...
".venv\Scripts\python.exe" -m pip install -q -e ".[dev]"
if errorlevel 1 goto error

echo.
echo Avvio CNV (Chi Ni Vidimu): apri http://127.0.0.1:8000 nel browser.
echo Lascia aperta questa finestra; per chiudere l'app premi Ctrl+C.
echo.
".venv\Scripts\python.exe" -m app.main
if errorlevel 1 goto error
goto :eof

:error
echo.
echo Qualcosa non ha funzionato: leggi il messaggio qui sopra.
pause
