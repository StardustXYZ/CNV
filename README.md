# 🎬 CNV – Chi Ni Vidimu

Cinema tracker personale per **Cosenza / Rende**.
Raccoglie le programmazioni dei cinema della zona, ti fa votare ogni film (V / ? / X) e, quando un film che volevi vedere esce da tutte le sale, lo prepara per la watchlist di **Letterboxd**.

Cinema seguiti: Andromeda River (Zumpano), Citrigno, Sale Unical, Teatro Italia / Tieri, Garden (Rende).

## Requisiti

- Python 3.11+
- Una [chiave API di TMDB](https://www.themoviedb.org/settings/api) (gratuita) per locandine, titoli ufficiali ed export verso Letterboxd

## Avvio

### Windows

```bat
run.bat
```

### Linux / macOS

```bash
chmod +x run.sh
./run.sh
```

Lo script crea il virtualenv, installa le dipendenze, avvia l'app e apre da solo il browser su **http://127.0.0.1:8000**. Se l'app è già accesa apre solo il browser.

### Icona sul Desktop (Windows)

Per avere sul Desktop l'icona **CNV** che avvia l'app con un doppio clic:

```bat
powershell -ExecutionPolicy Bypass -File crea_collegamento.ps1
```

Il collegamento avvia `run.bat` con la finestra ridotta a icona: per chiudere l'app chiudi quella finestra dalla barra delle applicazioni. Dal Desktop puoi anche aggiungerlo alla barra (tasto destro → Mostra altre opzioni → Aggiungi alla barra delle applicazioni).

### Avvio manuale

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -e ".[dev]"
python -m app.main
```

## Configurazione

1. Crea il file `.env` con la tua chiave TMDB:
   ```
   TMDB_API_KEY=la_tua_chiave
   ```
   `.env` non viene mai committato.
2. In `config/cinemas.yaml` trovi i cinema, le fonti delle uscite e le impostazioni del sync:
   - `days_to_uscito` / `days_to_uscito_evento`: giorni di assenza dopo cui un film è "uscito" (7, o 3 per gli eventi)
   - `auto_sync`, `auto_sync_time`: sync automatico giornaliero mentre l'app è aperta (default 08:00)
   - `auto_sync_catchup_hours`: all'avvio, se l'ultimo sync è più vecchio di così, ne parte subito uno
   - `backups_keep`: quante copie del database tenere

## Le pagine

| Pagina | Cosa mostra |
|---|---|
| **In sala** | Film in programmazione, con gli spettacoli rimasti oggi per cinema e sala. In fondo i film spariti dai siti, in attesa di essere segnati come usciti |
| **In uscita** | Film annunciati o in prevendita, con data e cinema |
| **Da verificare** | Film che non sono stato sicuro di abbinare a TMDB: conferma il suggerimento o cerca a mano |
| **Watchlist** | Film usciti da tutte le sale che avevi segnato V o ?: scarica il CSV per Letterboxd e segnali come esportati |
| **Stato** | Ultimi sync, esito per cinema, backup e prossimo sync automatico |

## Sync

Il sync legge le programmazioni e le pagine "prossimamente" dei cinema, abbina i film a TMDB, unisce i doppioni e aggiorna lo stato di ogni film. Prima di ogni sync viene fatto un backup del database in `backups/`.

Parte in tre modi:

- **automatico**, ogni giorno all'orario impostato, finché l'app web è aperta (e all'avvio se i dati sono vecchi);
- dal bottone **🔄 Sync** nell'app;
- da terminale:
  ```bash
  python -m app.sync
  ```

Ne può girare uno alla volta. Il log dettagliato è in `logs/cnv.log`.

### Sync anche ad app chiusa (Windows, facoltativo)

Per aggiornare i dati ogni giorno anche senza aprire l'app, puoi creare un'attività pianificata di Windows che esegua `sync_giornaliero.bat`:

```bat
schtasks /Create /TN "CNV sync giornaliero" /TR "\"%CD%\sync_giornaliero.bat\"" /SC DAILY /ST 08:00
```

(da lanciare nella cartella del progetto; per toglierla: `schtasks /Delete /TN "CNV sync giornaliero"`).

## Export verso Letterboxd

Letterboxd non ha un'API pubblica, quindi l'export passa da un file CSV con le colonne `tmdbID, Title, Year`:

1. pagina **Watchlist** → **Scarica CSV per Letterboxd**;
2. importa il file nella tua watchlist su Letterboxd;
3. torna su CNV e premi **Li ho importati su Letterboxd**: quei film non finiranno nel prossimo file.

Nel file vanno solo i film con un abbinamento TMDB confermato; gli altri sono indicati nella pagina, da sistemare in **Da verificare**.

## Test

```bash
pytest
```

I test usano un database in memoria e un TMDB finto: non toccano `cinewatch.db` e non vanno in rete.

## Struttura

```
app/
  scrapers/     # 18tickets, Cinema Garden, cosenzacinema.it (interfaccia BaseScraper)
  db/           # modelli SQLAlchemy + migrazioni leggere
  services/     # sync, uscite, matching TMDB, export, backup, sync automatico
  web/          # route FastAPI + template Jinja2 + htmx
config/
  cinemas.yaml  # cinema, fonti delle uscite e impostazioni
tests/
```

Dati e locandine da [TMDB](https://www.themoviedb.org/). Questo prodotto usa le API di TMDB ma non è approvato né certificato da TMDB.
