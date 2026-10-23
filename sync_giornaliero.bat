@echo off
rem Sync di CNV senza aprire l'app (da usare con un'attivita pianificata di Windows, vedi README)
cd /d "%~dp0"
if not exist logs mkdir logs
".venv\Scripts\python.exe" -m app.sync >> logs\sync_giornaliero.txt 2>&1
