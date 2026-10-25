# 🎬 CNV – Chi Ni Vidimu

Cinema tracker personale per **Cosenza / Rende**.

CNV raccoglie ogni giorno le programmazioni dei cinema della zona e mostra in un'unica pagina cosa c'è in sala oggi (cinema, sala e orari) e cosa sta per uscire. Ogni film si vota con **V** (voglio vederlo), **?** (non so) o **X** (non mi interessa). Quando un film segnato V o ? esce da tutte le sale, finisce in una watchlist pronta da importare su **Letterboxd**.

Cinema seguiti: **Andromeda River** (Zumpano), **Citrigno** (Cosenza), **Sale Unical** (Rende), **Teatro Italia / Tieri** (Cosenza), **Garden** (Rende).

## Funzionalità

- **In sala oggi**: per ogni film i cinema, le sale e solo gli spettacoli non ancora iniziati (gli spettacoli dopo mezzanotte contano come parte della serata). Gli orari passati spariscono da soli se la pagina resta aperta.
- **In uscita**: film in prevendita o annunciati dai cinema ("prossimamente"), con la data e i cinema che li avranno.
- **Voti V / ? / X** con filtri; cliccando di nuovo lo stesso voto lo si toglie.
- **Uscita dalle sale automatica**: un film è "uscito" quando non compare più in nessun cinema per 7 giorni (3 per gli eventi), così i buchi di programmazione non creano falsi allarmi.
- **Abbinamento a TMDB**: locandina, titolo ufficiale e anno; i doppioni scritti in modo diverso dai vari cinema (es. "MAMMINA" e "mammina (other mommy)", versioni V.O. o IMAX) vengono uniti in un solo film.
- **Export per Letterboxd**: CSV con l'ID TMDB di ogni film, così Letterboxd sceglie il film esatto; i film già esportati non vengono ripetuti.
- **Aggiornamento automatico** ogni giorno, con backup del database prima di ogni aggiornamento e una pagina di stato.

## Primo avvio (Windows)

1. Installa **Python 3.11 o più recente** da [python.org](https://www.python.org/downloads/) (spunta *Add python.exe to PATH*).
2. Scarica il progetto:
   ```bash
   git clone https://github.com/StardustXYZ/CNVTrue.git
   cd CNVTrue
   ```
3. Crea una chiave API gratuita su [TMDB](https://www.themoviedb.org/settings/api) e mettila in un file `.env` nella cartella del progetto:
   ```
   TMDB_API_KEY=la_tua_chiave
   ```
   Serve la "API Key" corta, non il token lungo. Il file `.env` non va mai condiviso né caricato su GitHub.
4. Fai doppio clic su **`run.bat`**. La prima volta crea l'ambiente Python e installa le dipendenze; poi avvia l'app e apre il browser su **http://127.0.0.1:8000**.
5. (Facoltativo) Crea l'icona **CNV** sul Desktop:
   ```bat
   powershell -ExecutionPolicy Bypass -File crea_collegamento.ps1
   ```
   Da lì in poi basta un doppio clic sull'icona. Puoi anche aggiungerla alla barra delle applicazioni (tasto destro → Mostra altre opzioni → Aggiungi alla barra delle applicazioni).

Al primo avvio il database è vuoto: parte da solo un aggiornamento (1-2 minuti), oppure premi **🔄 Sync**.

### Uso quotidiano

- **Aprire**: doppio clic sull'icona CNV (o su `run.bat`). Se l'app è già accesa si apre solo il browser.
- **Chiudere**: chiudi la finestra "run.bat" (o premi Ctrl+C dentro).
- Finché l'app è aperta, ogni giorno alle 08:00 si aggiorna da sola.

### Linux / macOS

```bash
chmod +x run.sh
./run.sh
```

### Avvio manuale

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
python -m app.launcher
```

## Le pagine

| Pagina | Cosa mostra |
|---|---|
| **In sala** | Film in programmazione con gli spettacoli rimasti oggi per cinema e sala. In fondo, a parte, i film spariti dai siti dei cinema con la data in cui verranno segnati come usciti |
| **In uscita** | Film annunciati o in prevendita, ordinati per data, con i cinema che li avranno ("data da definire" se il cinema non la indica) |
| **Da verificare** | Film che CNV non è riuscito ad abbinare con certezza a TMDB: si conferma il suggerimento o si cerca a mano. Se un film già abbinato ha locandina o titolo sbagliati, il link **cambia** sulla sua scheda apre la stessa ricerca |
| **Watchlist** | Film usciti da tutte le sale segnati V o ?: si scarica il CSV per Letterboxd e si segnano come esportati |
| **Stato** | Prossimo aggiornamento automatico, cronologia degli aggiornamenti, esito per ogni cinema e backup |

## Come vengono decisi gli stati dei film

| Stato | Quando |
|---|---|
| **In uscita** | Ha solo spettacoli futuri (prevendita) oppure è annunciato da un cinema |
| **In sala** | Ha spettacoli oggi o nei giorni passati e compare ancora sui siti dei cinema |
| **Uscito** | Non compare in nessun cinema da almeno 7 giorni (3 per gli eventi). La data di uscita dalle sale è quella del suo ultimo spettacolo. Se un cinema lo annuncia di nuovo resta "In uscita"; se ricompare in programmazione torna "In sala" |

Un film è un "evento" solo se lo sono tutti i suoi spettacoli attuali: un'anteprima prima della programmazione normale non basta.

Se il sito di un cinema non risponde, i suoi film non vengono considerati spariti, per al massimo 7 giorni. Gli spettacoli che un cinema toglie o sposta spariscono anche da CNV al sync successivo.

Le azioni (voti, sync, export) vengono accettate solo dalle pagine di CNV: un altro sito aperto nel browser non può modificarle.

## Da dove arrivano i dati

| Cinema | Programmazione | Film in arrivo |
|---|---|---|
| Andromeda River | sito 18tickets | pagina "coming soon" di 18tickets (con date) |
| Citrigno, Sale Unical, Teatro Italia / Tieri | siti 18tickets | sezioni "Coming soon" ed "Eventi & Rassegne" di cosenzacinema.it |
| Garden | cinemagarden.net, giorno per giorno | banner "Prossimamente" (titoli dai nomi delle locandine, senza date) |

Titoli, locandine e anni vengono da [TMDB](https://www.themoviedb.org/). Le richieste ai siti sono poche, distanziate e fatte una volta al giorno.

### Aggiungere un cinema

In `config/cinemas.yaml` aggiungi una voce con `slug`, `name`, `url` e lo `scraper` da usare. Se il cinema usa 18tickets basta `scraper: 18tickets`; per un sito diverso serve un nuovo scraper in `app/scrapers/`. Il campo `aliases` contiene i nomi con cui altri siti chiamano quel cinema.

## Aggiornamento dei dati (sync)

Ogni aggiornamento legge le programmazioni e le pagine "prossimamente", abbina i nuovi film a TMDB, unisce i doppioni e ricalcola lo stato di ogni film. Prima viene fatta una copia del database in `backups/`.

Parte in tre modi:

- **automatico**, ogni giorno all'orario impostato finché l'app è aperta, e all'avvio se l'ultimo aggiornamento ha più di 20 ore;
- dal bottone **🔄 Sync** nell'app;
- da terminale: `python -m app.sync` (stampa un riepilogo di film nuovi, cambi di stato e abbinamenti TMDB).

Ne gira uno alla volta. Il log dettagliato è in `logs/cnv.log`.

### Aggiornare anche ad app chiusa (Windows, facoltativo)

Un'attività pianificata di Windows può lanciare `sync_giornaliero.bat` ogni mattina. Nella cartella del progetto:

```bat
schtasks /Create /TN "CNV sync giornaliero" /TR "\"%CD%\sync_giornaliero.bat\"" /SC DAILY /ST 08:00
```

Per toglierla: `schtasks /Delete /TN "CNV sync giornaliero"`.

## Export verso Letterboxd

Letterboxd non ha un'API pubblica, quindi l'export passa da un file CSV con le colonne `tmdbID, Title, Year`:

1. pagina **Watchlist** → **Scarica CSV per Letterboxd**;
2. importa il file nella tua watchlist su Letterboxd;
3. torna su CNV e premi **Li ho importati su Letterboxd**: quei film non finiranno nel prossimo file (si possono rimettere con "Esporta di nuovo").

Nel file vanno solo i film con un abbinamento TMDB confermato; gli altri sono elencati nella pagina e si sistemano in **Da verificare**.

## Configurazione

Tutto in `config/cinemas.yaml`, sezione `sync_settings`:

| Impostazione | Default | Significato |
|---|---|---|
| `days_to_uscito` | 7 | giorni di assenza dopo cui un film è "uscito" |
| `days_to_uscito_evento` | 3 | lo stesso per gli eventi (anteprime, film evento) |
| `auto_sync` | true | aggiornamento automatico mentre l'app è aperta |
| `auto_sync_time` | "08:00" | orario dell'aggiornamento automatico |
| `auto_sync_catchup_hours` | 20 | all'avvio, aggiorna subito se i dati sono più vecchi di così |
| `backups_keep` | 14 | copie del database da tenere in `backups/` |

## Risoluzione dei problemi

- **Il browser dice "Impossibile raggiungere il sito"**: l'app non è accesa. Avviala con l'icona o con `run.bat` e aspetta la riga "Application startup complete".
- **La finestra di `run.bat` mostra un errore**: leggi il messaggio, la finestra resta aperta apposta. Se manca Python, installalo e riprova.
- **Mancano locandine e titoli ufficiali**: controlla che il file `.env` contenga `TMDB_API_KEY`.
- **Un cinema non si aggiorna**: guarda la pagina **Stato** e `logs/cnv.log`; il sito potrebbe aver cambiato struttura.
- **Serve tornare a un database precedente**: chiudi l'app e copia uno dei file di `backups/` al posto di `cinewatch.db`.

## Test

```bash
pytest
```

I test usano un database in memoria e un TMDB finto: non toccano `cinewatch.db` e non vanno in rete.

## Struttura del progetto

```
app/
  scrapers/        # 18tickets, Cinema Garden, cosenzacinema.it
  db/              # modelli SQLAlchemy e piccole migrazioni dello schema
  services/        # sync, film in arrivo, matching TMDB, export, backup, aggiornamento automatico
  web/             # pagine (FastAPI + Jinja2 + htmx), stile e icona
  launcher.py      # avvia l'app e apre il browser
  sync.py          # aggiornamento da terminale
config/
  cinemas.yaml     # cinema, fonti dei film in arrivo e impostazioni
tests/             # test automatici e pagine HTML di esempio dei cinema
run.bat / run.sh   # avvio
crea_collegamento.ps1, sync_giornaliero.bat   # icona sul Desktop e aggiornamento pianificato (Windows)
```

---

Dati e locandine da [TMDB](https://www.themoviedb.org/). Questo prodotto usa le API di TMDB ma non è approvato né certificato da TMDB.
