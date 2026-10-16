# 🎬 CineWatch

Cinema tracker personale per **Cosenza / Rende**.  
Raccoglie le programmazioni, ti fa votare ogni film (V / ? / X) e quando un film esce da tutte le sale lo mette in una watchlist esportabile per **Letterboxd**.

## Requisiti

- Python 3.11+
- (Opzionale) una [TMDB API key](https://www.themoviedb.org/settings/api) per poster e titoli ufficiali

## Avvio rapido

### Windows

```bat
run.bat
```

### Linux / macOS

```bash
chmod +x run.sh
./run.sh
```

Lo script crea un virtualenv, installa le dipendenze e avvia l'app su **http://127.0.0.1:8000**.

### Avvio manuale

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -e ".[dev]"
python -m app.main
```

## Configurazione

1. Copia `.env.example` in `.env` e inserisci la tua TMDB API key.
2. Modifica `config/cinemas.yaml` per aggiungere o rimuovere cinema.

## Test

```bash
pytest
```

## Struttura

```
app/
  scrapers/     # un modulo per sorgente (interfaccia BaseScraper)
  db/           # modelli SQLAlchemy + sessione
  services/     # sync, TMDB matching, export Letterboxd
  web/          # route FastAPI + template Jinja2
config/
  cinemas.yaml  # elenco cinema e URL
tests/
```

## Come funziona

1. **Sync** – scrapa i siti dei cinema configurati e salva le programmazioni nel DB SQLite
2. **Vota** – sulla home page segna ogni film come **V** (voglio andare), **?** (indeciso) o **X** (non vado)
3. **Watchlist** – quando un film V o ? non ha più proiezioni future, appare nella watchlist
4. **Export** – scarica un CSV compatibile con l'import watchlist di Letterboxd

