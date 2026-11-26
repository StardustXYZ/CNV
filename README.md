# 🎬 CNV – Chi Ni Vidimu

Cinema tracker personale per **Cosenza / Rende**.

Ogni notte un aggiornamento automatico su GitHub raccoglie le programmazioni dei cinema della zona. L'app (Android e browser) mostra in un'unica pagina cosa c'è in sala oggi (cinema, sala e orari) e cosa sta per uscire. Ogni film si vota con **V** (voglio vederlo), **?** (indeciso) o **✓** (visto). Quando un film segnato V o ? esce da tutte le sale, finisce in una watchlist pronta da importare su **Letterboxd**.

Cinema seguiti: **Andromeda River** (Zumpano), **Citrigno** (Cosenza), **Sale Unical** (Rende), **Teatro Italia / Tieri** (Cosenza), **Garden** (Rende).

## Funzionalità

- **In sala oggi**: per ogni film i cinema, le sale e solo gli spettacoli non ancora iniziati (gli spettacoli dopo mezzanotte contano come parte della serata).
- **In uscita**: film in prevendita o annunciati dai cinema ("prossimamente"), con la data e i cinema che li avranno.
- **Voti V / ? / ✓** con filtri; toccando di nuovo lo stesso voto lo si toglie.
- **Uscita dalle sale automatica**: un film è "uscito" quando non compare più in nessun cinema per 7 giorni (3 per gli eventi), così i buchi di programmazione non creano falsi allarmi.
- **Abbinamento a TMDB**: locandina, titolo ufficiale e anno; i doppioni scritti in modo diverso dai vari cinema (es. "MAMMINA" e "mammina (other mommy)", versioni V.O. o IMAX) vengono uniti in un solo film.
- **Export per Letterboxd**: CSV con l'ID TMDB di ogni film, così Letterboxd sceglie il film esatto; i film già esportati non vengono ripetuti.

## App Android e versione web

Sul telefono CNV è un'app Android (cartella `mobile/`, in Flutter) che legge i dati aggiornati ogni notte da GitHub: film in sala con gli orari, in uscita con il calendario, pagine dei cinema, voti **V / ? / ✓**, watchlist e diario per Letterboxd, statistiche dei film visti.

Con l'**account** (Google, oppure email e password) i voti si salvano anche online e si ritrovano su un altro telefono, e arrivano le **notifiche** dei film nuovi in sala (tutti, solo i propri V, o nessuna; "Esce oggi" se il primo spettacolo è quel giorno) e, a scelta, gli **ultimi giorni** dei film segnati V. L'account è su invito: chi gestisce CNV aggiunge le email ammesse dall'app. Ognuno vede solo i suoi voti. Senza account l'app funziona lo stesso, con i voti solo sul telefono.

### Installarla

1. Apri la pagina [Releases](https://github.com/StardustXYZ/CNV/releases) dal telefono e scarica il file `CNV-….apk` dell'ultima versione.
2. Apri il file scaricato. La prima volta Android chiede di permettere l'installazione di app dal browser (o dall'app File): permettila, poi tocca **Installa**.
3. Apri CNV. Per l'account e le notifiche: pagina **Voti** → **Accedi**.

Quando esce una versione nuova, l'app lo dice in alto: **Scarica**, poi apri il file e tocca **Aggiorna**. I voti restano.

Cosa salva CNV e dove è spiegato nell'app: pagina **Voti** → **Privacy**. Da lì si può anche eliminare l'account.

### Nel browser

La stessa app si apre anche nel browser, per esempio sul PC: https://stardustxyz.github.io/CNV/. Ha le stesse pagine e, con lo stesso account, gli stessi voti del telefono; senza account i voti restano in quel browser. Non ha le notifiche (arrivano sull'app Android) né l'avviso delle versioni nuove (la pagina è sempre l'ultima). La prima volta prende da sola i voti della vecchia versione web salvati nello stesso browser.

## Sul PC (per chi gestisce CNV)

L'aggiornamento dei dati gira su GitHub, non serve tenere acceso il PC. Sul PC servono solo per provare l'aggiornamento o per correggere un abbinamento a TMDB.

1. Installa **Python 3.11 o più recente** da [python.org](https://www.python.org/downloads/) (spunta *Add python.exe to PATH*).
2. Scarica il progetto e prepara l'ambiente:
   ```bash
   git clone https://github.com/StardustXYZ/CNV.git
   cd CNV
   python -m venv .venv
   # Windows: .venv\Scripts\activate     Linux/macOS: source .venv/bin/activate
   pip install -e ".[dev]"
   ```
3. Crea una chiave API gratuita su [TMDB](https://www.themoviedb.org/settings/api) e mettila in un file `.env` nella cartella del progetto:
   ```
   TMDB_API_KEY=la_tua_chiave
   ```
   Serve la "API Key" corta, non il token lungo. Il file `.env` non va mai condiviso né caricato su GitHub.

## Come vengono decisi gli stati dei film

| Stato | Quando |
|---|---|
| **In uscita** | Ha solo spettacoli futuri (prevendita) oppure è annunciato da un cinema |
| **In sala** | Ha spettacoli oggi o nei giorni passati e compare ancora sui siti dei cinema |
| **Uscito** | Non compare in nessun cinema da almeno 7 giorni (3 per gli eventi). La data di uscita dalle sale è quella del suo ultimo spettacolo. Anche un film annunciato che nessun cinema ha poi proiettato diventa "uscito", 7 giorni dopo l'ultimo annuncio, senza data ("Non è arrivato in sala"): se l'avevi segnato V o ? finisce in Watchlist come gli altri. Se un cinema lo annuncia di nuovo resta "In uscita"; se ricompare in programmazione torna "In sala" |

Un film è un "evento" solo se lo sono tutti i suoi spettacoli attuali: un'anteprima prima della programmazione normale non basta.

**Ultimi giorni**: ogni cinema pubblica la programmazione per qualche giorno; conta come pubblicata fino all'ultimo giorno con almeno metà dei film di oggi (dopo restano solo le prevendite). Un film in sala che in tutti i suoi cinema finisce prima di quel giorno è agli ultimi giorni (gli eventi sono esclusi). Chi ha attivato «Ultimi giorni dei miei V» nell'app riceve un avviso per i film che ha segnato V, una volta per film; di solito arriva l'ultimo giorno o quello prima, perché i cinema pubblicano pochi giorni in anticipo. Le previsioni restano salvate: `python -m app.push verifica` le confronta con gli spettacoli veri (nella prova di novembre 2026: 10 su 10).

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

Ogni aggiornamento legge le programmazioni e le pagine "prossimamente", abbina i nuovi film a TMDB, unisce i doppioni e ricalcola lo stato di ogni film. Il database di riferimento è nel ramo `dati` di GitHub e lo aggiorna il workflow **Aggiorna CNV per il telefono** ogni notte (e a mano da Actions → Run workflow).

Per provarlo sul PC: `python -m app.sync` (stampa un riepilogo di film nuovi, cambi di stato e abbinamenti TMDB; lavora su `cinewatch.db`, una copia locale che non arriva al telefono). Prima viene fatta una copia del database in `backups/`. Ne gira uno alla volta; il log dettagliato è in `logs/cnv.log`.

Se nessun cinema si lascia leggere l'aggiornamento fallisce e il sito resta quello di ieri; se ne manca solo uno è un avviso e i suoi film restano per al massimo 7 giorni.

### Correggere un abbinamento a TMDB

Se un film ha locandina o titolo sbagliati, o CNV non è riuscito ad abbinarlo (`python -m app.sync` li elenca sotto "Da verificare"):

```bash
python -m app.abbina                  # la finestra: film da verificare, ricerca su TMDB, scelta
python -m app.abbina lista [testo]    # film da verificare, o con il testo nel titolo
python -m app.abbina cerca "titolo"   # ricerca su TMDB
python -m app.abbina imposta 123 456  # film 123 -> film TMDB 456
```

I film si leggono dal database notturno su GitHub (senza modificarlo). La scelta si scrive in `config/abbinamenti.yaml`: fai commit e push di quel file e il prossimo aggiornamento notturno la applica.

## Export verso Letterboxd

Letterboxd non ha un'API pubblica, quindi l'export passa da un file CSV con le colonne `tmdbID, Title, Year`, che l'app genera nelle pagine **Voti** (watchlist e diario): importalo su Letterboxd, poi nell'app segna i film come esportati, così non finiranno nel prossimo file. Nel file vanno solo i film con un abbinamento TMDB confermato.

## Configurazione

Tutto in `config/cinemas.yaml`, sezione `sync_settings`:

| Impostazione | Default | Significato |
|---|---|---|
| `days_to_uscito` | 7 | giorni di assenza dopo cui un film è "uscito" |
| `days_to_uscito_evento` | 3 | lo stesso per gli eventi (anteprime, film evento) |
| `backups_keep` | 14 | copie del database da tenere in `backups/` (sync da terminale) |

## Risoluzione dei problemi

- **Mancano locandine e titoli ufficiali**: controlla che il file `.env` contenga `TMDB_API_KEY` (e, su GitHub, il segreto `TMDB_API_KEY`).
- **Un cinema non si aggiorna**: guarda l'avviso nella pagina del workflow su GitHub, `python -m app.check_sites` e `logs/cnv.log`; il sito potrebbe aver cambiato struttura.
- **Un film ha la locandina sbagliata**: vedi "Correggere un abbinamento a TMDB".
- **Serve tornare a un database precedente**: il database dell'app è un solo commit nel ramo `dati`, sovrascritto ogni notte; per quello locale copia uno dei file di `backups/` al posto di `cinewatch.db`.

## Test

```bash
pytest
```

I test usano un database in memoria e un TMDB finto: non toccano `cinewatch.db` e non vanno in rete.

## Costruire e pubblicare l'app

Serve Flutter (`C:\flutter`). Restano sul PC, fuori da git:

- `mobile/android/app/google-services.json`: si scarica da Firebase → Impostazioni progetto → app Android;
- `mobile/android/key.properties` e la chiave `cnv-firma.jks`: firmano le versioni da pubblicare (vedi `mobile/android/key.properties.example`). Senza la chiave le versioni nuove non si installano sopra quelle vecchie: va tenuta con una copia di riserva.

```bash
cd mobile
flutter test
flutter build apk --release --target-platform android-arm64
```

La versione per il browser la costruisce GitHub ogni notte, insieme ai dati (workflow **Aggiorna CNV per il telefono**). Per provarla sul PC:

```bash
cd mobile
flutter build web --base-href /CNV/ --pwa-strategy=none
cd ..
python -m app.export_static --out site
```

La cartella `site/` va servita all'indirizzo `/CNV/` (es. una cartella `CNV` dentro quella servita da `python -m http.server`).

L'APK è in `mobile/build/app/outputs/flutter-apk/app-release.apk`. Per pubblicarlo: GitHub → **Releases** → **Draft a new release**, tag `app-v` più la versione di `pubspec.yaml` (es. `app-v0.11.0`), allega l'APK rinominato `CNV-0.11.0.apk` e pubblica. L'app controlla le release con quel tag e avvisa chi ha una versione più vecchia.

Le regole di accesso di Firestore sono in `firebase/firestore.rules`, con i test sull'emulatore (`cd firebase && npm test`, serve Java). Si pubblicano con il workflow **Regole Firebase** o incollandole in Firebase → Firestore → Regole.

## Struttura del progetto

```
app/
  scrapers/        # 18tickets, Cinema Garden, cosenzacinema.it
  db/              # modelli SQLAlchemy e piccole migrazioni dello schema
  services/        # sync, film in arrivo, matching TMDB e abbinamenti a mano, backup
  sync.py          # aggiornamento da terminale (lo stesso che gira su GitHub)
  abbina.py        # correzione a mano degli abbinamenti TMDB (finestra e comandi)
  export_static.py # scrive data.json per l'app
  push.py          # notifiche sul telefono
config/
  cinemas.yaml     # cinema, fonti dei film in arrivo e impostazioni
  abbinamenti.yaml # abbinamenti a TMDB scelti a mano
tests/             # test automatici e pagine HTML di esempio dei cinema
mobile/            # l'app in Flutter: Android e browser (GitHub Pages)
firebase/          # regole di accesso di Firestore e i loro test
```

---

Dati e locandine da [TMDB](https://www.themoviedb.org/). Questo prodotto usa le API di TMDB ma non è approvato né certificato da TMDB.
