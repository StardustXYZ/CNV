#!/usr/bin/env bash
# Salva dati/cnv.db nel ramo "dati": un solo commit, sovrascritto ogni volta.
# Usato due volte dal workflow "Aggiorna CNV per il telefono": prima della pubblicazione
# (gli id dei film nuovi non devono andare persi) e dopo l'invio delle notifiche (i film
# segnati come notificati). Serve GITHUB_TOKEN e GITHUB_REPOSITORY nell'ambiente.
set -euo pipefail

cp dati/cnv.db "$RUNNER_TEMP/cnv.db"
cd "$RUNNER_TEMP"
rm -rf ramo-dati
mkdir ramo-dati && mv cnv.db ramo-dati/ && cd ramo-dati
git init --quiet --initial-branch=dati
git add cnv.db
git -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
  commit --quiet -m "Database CNV del $(date +%d/%m/%Y)"
git push --quiet --force "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" dati
