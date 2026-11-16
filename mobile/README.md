# CNV per Android (Flutter)

L'app di CNV per il telefono, scritta in Flutter. Legge gli stessi dati della versione web (`data.json`, aggiornato ogni notte da GitHub). Per ora è solo per Android.

## Costruire l'APK di prova

Serve Flutter (`flutter doctor` con la riga Android in verde). Dalla cartella `mobile/`:

```bash
flutter build apk --release --target-platform android-arm64
```

L'APK esce in `build/app/outputs/flutter-apk/app-release.apk`. Si copia nella cartella `apk/` del progetto, che git ignora, e si installa sul telefono a mano.

L'APK è firmato con la chiave di CNV, letta da `android/key.properties` (vedi `android/key.properties.example`); senza quel file viene firmato con la chiave di prova del PC e non si installa sopra le versioni pubblicate. Le impronte delle due chiavi sono registrate su Firebase.

## Prove e controlli

```bash
flutter test
```

```bash
flutter analyze
```

## Icona

L'icona (ciak bianco sul viola della versione web) si ridisegna con:

```bash
python tools/crea_icone.py
```

Scrive l'icona classica, i due livelli dell'icona adattiva e la versione a un colore per le icone a tema di Android 13+. Serve Pillow (`pip install pillow`).

## Versione

In `pubspec.yaml`, `version: 0.1.0+1`: il primo numero è quello che vede chi installa, il secondo va aumentato a ogni APK dato agli amici, altrimenti Android non lo installa sopra il vecchio.
