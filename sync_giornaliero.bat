@echo off
rem Sync di CNV senza aprire l'app (da usare con un'attività pianificata di Windows, vedi README)
cd /d "%~dp0"
call .venv\Scripts\activate.bat
if not exist logs mkdir logs
python -m app.sync >> logs\sync_giornaliero.txt 2>&1
