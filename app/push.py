"""Notifications on the phone when new films arrive in theaters (Web Push, free).

GitHub Actions runs this after the nightly sync, in two steps:

    python -m app.push prepare --out notifica.json [--prova]
    python -m app.push send notifica.json

``prepare`` picks the films that became "in sala" since the last notification, marks
them and writes the message; ``send`` delivers it to the phone through the browser's
push service once the site is published. Nothing personal is sent: the phone itself
puts the user's V films first, since the votes never leave it.

``send`` needs two secrets: ``VAPID_PRIVATE_KEY`` (the key the app's public key pairs
with) and ``PUSH_SUBSCRIPTION`` (the code shown on the phone's "Voti" page). Without
them it does nothing.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from sqlalchemy.orm import Session

from app.db.engine import SessionLocal, init_db
from app.db.models import Film

# Contact for the push service (VAPID "sub"): a site address without a path, as pywebpush requires
VAPID_CONTACT = "https://stardustxyz.github.io"
MAX_FILMS = 10  # a push message holds about 4 KB
TTL_SECONDS = 12 * 3600  # a phone switched off for longer gets nothing: by then the news is old


def _title(film: Film) -> str:
    return film.tmdb_title if film.is_tmdb_confirmed and film.tmdb_title else film.raw_title


def new_in_sala(db: Session) -> list[Film]:
    """Films that became "in sala" and were not notified yet."""
    films = db.query(Film).filter(Film.status == "in_sala", Film.in_sala_pushed.is_(False)).all()
    return sorted(films, key=lambda f: _title(f).lower())


def prepare(db: Session, test: bool = False) -> dict:
    """The message for the films new in theaters (empty: nothing to say). Marks them as notified.

    They are marked even when notifications are not set up, so turning them on later does
    not bring a flood of old news.
    """
    films = new_in_sala(db)
    for film in films:
        film.in_sala_pushed = True
    db.commit()
    if films:
        return {
            "films": [{"id": f.id, "title": _title(f)} for f in films[:MAX_FILMS]],
            "more": max(0, len(films) - MAX_FILMS),
        }
    if test:
        return {"title": "CNV", "body": "Le notifiche funzionano: ti scrivo quando un film nuovo arriva in sala."}
    return {}


def send(payload: dict, subscription: str, private_key: str) -> None:
    """Deliver the message to the phone (raises if the push service refuses it)."""
    from pywebpush import webpush  # only GitHub needs it: pip install -e ".[push]"

    webpush(
        subscription_info=json.loads(subscription),
        data=json.dumps(payload, ensure_ascii=False),
        vapid_private_key=private_key,
        vapid_claims={"sub": VAPID_CONTACT},
        ttl=TTL_SECONDS,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Notifiche di CNV sul telefono")
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="sceglie i film nuovi in sala e scrive il messaggio")
    prep.add_argument("--out", required=True, type=Path)
    prep.add_argument("--prova", action="store_true", help="senza film nuovi, un messaggio di prova")
    snd = commands.add_parser("send", help="invia il messaggio al telefono")
    snd.add_argument("file", type=Path)
    args = parser.parse_args()

    if args.command == "prepare":
        init_db()
        with SessionLocal() as db:
            payload = prepare(db, test=args.prova)
        args.out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"Film nuovi in sala: {len(payload.get('films', []))}" if payload else "Nessuna novità da notificare")
        return 0

    payload = json.loads(args.file.read_text(encoding="utf-8")) if args.file.exists() else {}
    subscription, private_key = os.getenv("PUSH_SUBSCRIPTION", ""), os.getenv("VAPID_PRIVATE_KEY", "")
    if not payload:
        print("Nessuna notifica da inviare")
    elif not (subscription and private_key):
        print("Notifiche non attive: mancano i segreti PUSH_SUBSCRIPTION e VAPID_PRIVATE_KEY")
    else:
        try:
            send(payload, subscription, private_key)
        except Exception as err:  # the site is published anyway: report and go on
            print(f"::warning::Notifica non inviata: {err}. Se hai reinstallato l'app, copia di nuovo il codice dalla pagina Voti.")
            return 0
        print("Notifica inviata")
    return 0


if __name__ == "__main__":
    sys.exit(main())
