# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

CNV ("Chi Ni Vidimu") is a personal cinema tracker for Cosenza/Rende. User-facing text, docs, comments in workflow files and commit messages are in Italian; code identifiers and most docstrings are in English. `README.md` and `mobile/README.md` are detailed (film status rules, data sources, config table) — read them before changing behavior.

## Architecture

Two halves joined by a single JSON file, `data.json`:

1. **Python backend (`app/`)** — scrapes cinema sites, matches films to TMDB, keeps state in SQLite (SQLAlchemy, `cinewatch.db`).
   - `app/scrapers/` — one per source (`eighteen_tickets`, `cosenzacinema`, `garden`); cinemas are declared in `config/cinemas.yaml` (also holds `sync_settings`).
   - `app/services/` — `sync.py` (`run_sync` orchestrates the phases: read sites → judge cinemas → store shows → snapshots → TMDB matching → statuses), `film_status.py` (decides in sala/in uscita/uscito and event thresholds), `runner.py` (one full sync with backup + `SyncLog`; a single sync at a time, across processes), `matching.py`/`tmdb.py`/`titles.py` (TMDB matching and duplicate merging), `last_days.py`, `schedule.py`.
   - `app/sync.py` is the CLI sync; `app/export_static.py` writes `data.json` next to the built Flutter web app; `app/push.py` prepares/sends FCM notifications (`prepare`, `send`, `verifica`).
   - `app/abbina.py` (tkinter window + `lista`/`cerca`/`imposta` commands) fixes a TMDB match by hand: it reads the nightly DB from the `dati` branch and writes `config/abbinamenti.yaml`, which `services/overrides.py` applies during the next nightly sync (a correction made on the PC cannot go into the DB directly: that DB lives on GitHub and is rebuilt every night).
   - There is no local web UI any more: votes, Letterboxd export and stats live only in the Flutter app. `cinewatch.db` on the PC is just a local copy for trying the sync. The `films` table has no vote/seen/Letterboxd columns: `init_db()` drops them from older databases (`LEGACY_FILM_COLUMNS`), so the migration runs on the `dati` branch DB at the next nightly sync.
2. **Flutter app (`mobile/`)** — one codebase for Android and the browser (published on GitHub Pages at `/CNV/`). It reads `data.json` (`lib/data/repository.dart`, `dataUrl`), and does today's remaining shows, calendar, votes, Letterboxd export client-side. Platform differences are isolated in conditional-import pairs: `lib/data/storage{,_io,_web}.dart`, `lib/widgets/save_file_{io,web}.dart`, `lib/data/device_words.dart`. Optional accounts/vote sync/push go through Firebase (`lib/data/firebase_*.dart`); Firestore rules live in `firebase/firestore.rules` with emulator tests.

**Nightly pipeline** (`.github/workflows/aggiorna-telefono.yml`): build Flutter web → restore DB from the `dati` branch (single force-pushed commit holding `cnv.db`) → `python -m app.sync` → `app.push prepare` → save DB back to `dati` → `app.export_static --out site` → deploy Pages → `app.push send`. Needs secret `TMDB_API_KEY` (and `FIREBASE_SERVICE_ACCOUNT` for push/rules). Other workflows: `prova-siti.yml` (checks scrapers from GitHub's servers), `test-firebase.yml`, `regole-firebase.yml`.

## Commands

Python (3.11+, venv in `.venv`, needs `TMDB_API_KEY` in `.env`):
```bash
pip install -e ".[dev]"            # add ".[push]" for firebase-admin
python -m app.abbina               # fix a TMDB match by hand (then commit config/abbinamenti.yaml)
python -m app.sync                 # one sync from the terminal
pytest                             # tests use in-memory DB + fake TMDB, no network
pytest tests/test_sync.py::test_name   # single test
python -m app.check_sites          # check live cinema sites
```
`tests/test_real_db.py` depends on the local `cinewatch.db` (git-ignored).

Flutter (from `mobile/`, Flutter at `C:\flutter`, CI uses 3.35.7):
```bash
flutter test                       # all tests
flutter test test/sync_test.dart   # single file
flutter analyze
flutter build apk --release --target-platform android-arm64
flutter build web --release --base-href /CNV/ --pwa-strategy=none
```
Firebase rules tests: `cd firebase && npm ci && npm test` (needs Java for the emulator).

## Gotchas

- Not in git (stay on the PC): `.env`, `*.db`, `mobile/android/google-services.json`, `mobile/android/key.properties` + `cnv-firma.jks`. Without the signing key, new APKs won't install over published ones — never regenerate it.
- The project sits in OneDrive. If the Android build fails with `Cannot snapshot …: not a regular file`, files under `mobile/` are cloud placeholders (reparse points): check for the ReparsePoint attribute, keep the folder pinned (`attrib +P -U /S /D`), rewrite the affected files, delete `mobile/build`, rebuild. Copy the APK to `apk/` only after the build command truly succeeds.
- Bump the build number in `mobile/pubspec.yaml` (`version: x.y.z+N`) for every APK distributed, or Android won't update over the old one.
- "Ultimi giorni": predictions are stored in `last_days`; accounts with `utenti/{uid}.lastDays == true` get a notice for their V films (once per film per week, marked only after a successful send). `python -m app.push verifica` checks past predictions on a copy of the `dati` DB.
