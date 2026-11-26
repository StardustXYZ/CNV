"""Notifications on the phone when new films arrive in theaters (free).

GitHub Actions runs this after the nightly sync, in two steps:

    python -m app.push prepare --out notifica.json [--prova]
    python -m app.push send notifica.json

``prepare`` picks the films that became "in sala" since the last notification and writes
the message; ``send`` delivers it, once the site is published, to the Android app
(Firebase Cloud Messaging): every admitted account that turned notifications on gets them
on its phones, with its V films first (or only those, if it chose so). A film whose first
show is that very day "esce oggi". Only after a successful ``send`` (or without the
secret) the films are marked as notified in the database; if ``send`` fails it exits with
an error and they are announced again at the next run.

``prepare`` also finds the films in their last days (app/services/last_days.py), keeps the
guesses and adds them to the message: the accounts that turned on "ultimi giorni"
(utenti/{uid}.lastDays) get a separate notice for their V films, once per film. ``python -m
app.push verifica`` compares the past guesses with the shows the films really had.

``send`` needs the secret ``FIREBASE_SERVICE_ACCOUNT``; without it, it does nothing.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import os
from pathlib import Path
import sys

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.engine import SessionLocal, init_db
from app.db.models import Film, LastDays, Showtime
from app.services.last_days import check_guesses, record_leaving

MAX_FILMS = 10  # enough for a notification; the rest is counted ("e altri 3")
LAST_DAYS_REPEAT = timedelta(days=7)  # a film announced as leaving is not announced again within a week
WEEKDAYS = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")


def _title(film: Film) -> str:
    return film.tmdb_title if film.is_tmdb_confirmed and film.tmdb_title else film.raw_title


def new_in_sala(db: Session) -> list[Film]:
    """Films that became "in sala" and were not notified yet."""
    films = db.query(Film).filter(Film.status == "in_sala", Film.in_sala_pushed.is_(False)).all()
    return sorted(films, key=lambda f: _title(f).lower())


def leaving_to_notify(db: Session, today: date) -> list[LastDays]:
    """The guesses of films in their last days still to announce: the latest guess of each
    film in theaters (no events), whose last day has not passed, if it was not announced in
    the last week."""
    recent = {
        film_id
        for (film_id,) in db.query(LastDays.film_id).filter(
            LastDays.notified.is_(True), LastDays.found_on >= today - LAST_DAYS_REPEAT
        )
    }
    rows = (
        db.query(LastDays)
        .join(Film)
        .filter(
            LastDays.notified.is_(False),
            LastDays.last_day >= today,
            LastDays.found_on <= today,
            Film.status == "in_sala",
            Film.is_event.is_(False),
        )
        .order_by(LastDays.found_on.desc(), LastDays.id.desc())
    )
    chosen: dict[int, LastDays] = {}
    for row in rows:
        if row.film_id not in recent and row.film_id not in chosen:
            chosen[row.film_id] = row
    return sorted(chosen.values(), key=lambda r: (r.last_day, _title(r.film).lower()))


def prepare(db: Session, test: bool = False, today: date | None = None) -> dict:
    """The message for the films new in theaters and the films in their last days (empty:
    nothing to say).

    Does not mark them: ``send`` does, once the news has really gone out (``mark_notified``,
    ``mark_last_days``), so a failed night does not swallow them. "ids" lists all the new
    films, also the ones the message only counts. Films shown for the first time today get
    "today".
    """
    today = today or date.today()
    payload: dict = {}
    films = new_in_sala(db)
    if films:
        first_day = dict(
            db.query(Showtime.film_id, func.min(Showtime.date))
            .filter(Showtime.film_id.in_([f.id for f in films]))
            .group_by(Showtime.film_id)
        )
        payload.update({
            "films": [
                {"id": f.id, "title": _title(f), **({"today": True} if first_day.get(f.id) == today else {})}
                for f in films[:MAX_FILMS]
            ],
            "more": max(0, len(films) - MAX_FILMS),
            "ids": [f.id for f in films],
        })
    leaving = leaving_to_notify(db, today)
    if leaving:
        payload.update({
            "last_days": [{"id": r.film_id, "title": _title(r.film), "last_day": r.last_day.isoformat()}
                          for r in leaving[:MAX_FILMS]],
            "last_day_ids": [r.id for r in leaving],
            "today": today.isoformat(),
        })
    if payload:
        return payload
    if test:
        return {"title": "CNV", "body": "Le notifiche funzionano: ti scrivo quando un film nuovo arriva in sala."}
    return {}


def mark_notified(db: Session, ids: list[int]) -> int:
    """Mark the films as notified, so they are not announced again. Returns how many."""
    if not ids:
        return 0
    films = db.query(Film).filter(Film.id.in_(ids)).all()
    for film in films:
        film.in_sala_pushed = True
    db.commit()
    return len(films)


def mark_last_days(db: Session, ids: list[int]) -> int:
    """Mark the guesses of films in their last days as announced. Returns how many."""
    if not ids:
        return 0
    rows = db.query(LastDays).filter(LastDays.id.in_(ids)).all()
    for row in rows:
        row.notified = True
    db.commit()
    return len(rows)


# ---------------------------------------------------------------------- Android app (FCM)

MODES = ("all", "v", "off")  # utenti/{uid}.notify: every new film, only my V ones, none
TTL_FCM = timedelta(hours=12)  # a phone switched off for longer gets nothing: by then the news is old
MAX_BODY = 300


def _join(titles: list[str]) -> str:
    return ", ".join(titles)


def notification_for(payload: dict, votes: dict, mode: str | None) -> tuple[str, str] | None:
    """Title and text for one account, or None when it gets nothing.

    The films it marked V come first; with "only my V" (mode "v") the others are left out.
    """
    mode = mode if mode in MODES else "off"  # nobody gets notifications without asking
    if mode == "off" or not payload:
        return None
    if "body" in payload:  # the test message
        return payload.get("title", "CNV"), payload.get("body", "")
    films = payload.get("films") or []
    if not films:
        return None
    wanted = [f["title"] for f in films if votes.get(str(f["id"])) == "V"]
    others = [f["title"] for f in films if votes.get(str(f["id"])) != "V"]
    out_today = {f["title"] for f in films if f.get("today")}
    more = payload.get("more", 0)

    def one(title: str, new: bool) -> str:
        return f"🎬 Esce oggi: {title}" if title in out_today else (f"🎬 Nuovo in sala: {title}" if new else f"🎬 In sala: {title}")

    if wanted:
        title = one(wanted[0], new=False) if len(wanted) == 1 else f"🎬 In sala {len(wanted)} film che volevi vedere"
        body = _join(wanted)
        if mode == "all" and (others or more):
            body += f" · e anche: {_join(others)}" + (f" e altri {more}" if more else "")
    elif mode == "v":
        return None
    else:
        title = one(others[0], new=True) if len(films) == 1 and not more else f"🎬 {len(films) + more} film nuovi in sala"
        body = _join(others) + (f" e altri {more}" if more else "")
    if len(body) > MAX_BODY:
        body = body[: MAX_BODY - 1].rstrip(", ") + "…"
    return title, body


def last_days_notification(payload: dict, votes: dict, wanted: bool) -> tuple[str, str] | None:
    """Title and text of the "ultimi giorni" notice for one account (only its V films), or None."""
    films = [f for f in payload.get("last_days") or [] if votes.get(str(f["id"])) == "V"]
    if not wanted or not films:
        return None
    today = date.fromisoformat(payload.get("today") or date.today().isoformat())

    def until(f: dict) -> str:
        day = date.fromisoformat(f["last_day"])
        if day <= today:
            return "ultimo giorno oggi"
        if day == today + timedelta(days=1):
            return "fino a domani"
        return f"fino a {WEEKDAYS[day.weekday()]} {day.day}/{day.month}"

    if len(films) == 1:
        f = films[0]
        last = date.fromisoformat(f["last_day"]) <= today
        title = f"⏳ Ultimo giorno: {f['title']}" if last else f"⏳ Ultimi giorni: {f['title']}"
        body = "Oggi è l'ultimo giorno in sala." if last else f"In sala {until(f)}."
    else:
        title = f"⏳ Ultimi giorni per {len(films)} film che volevi vedere"
        body = ", ".join(f"{f['title']} ({until(f)})" for f in films)
    if len(body) > MAX_BODY:
        body = body[: MAX_BODY - 1].rstrip(", ") + "…"
    return title, body


def is_admitted(uid: str, email: str | None, verified: bool, allow: dict) -> bool:
    """The same check as the Firestore rules (firebase/firestore.rules)."""
    if not allow:
        return False
    if uid == allow.get("admin"):
        return True
    return bool(verified and email and email.lower() in allow.get("email", []))


class FirebaseClient:
    """Firestore, accounts and messages, with the service account (it skips the rules)."""

    def __init__(self, service_account: str):
        import firebase_admin  # only GitHub needs it: pip install -e ".[push]"
        from firebase_admin import credentials

        info = json.loads(service_account)
        self._app = firebase_admin.initialize_app(credentials.Certificate(info), name="cnv-push")
        from firebase_admin import firestore

        self._db = firestore.client(self._app)

    def allow_list(self) -> dict:
        snap = self._db.document("config/ammessi").get()
        return (snap.to_dict() or {}) if snap.exists else {}

    def accounts(self):
        """(uid, document) of every account with data."""
        for snap in self._db.collection("utenti").stream():
            yield snap.id, snap.to_dict() or {}

    def email_of(self, uid: str) -> tuple[str | None, bool]:
        from firebase_admin import auth

        try:
            user = auth.get_user(uid, app=self._app)
        except auth.UserNotFoundError:
            return None, False
        return user.email, bool(user.email_verified)

    def devices(self, uid: str) -> list[tuple[str, str]]:
        return [
            (snap.id, (snap.to_dict() or {}).get("token", ""))
            for snap in self._db.collection(f"utenti/{uid}/telefoni").stream()
        ]

    def remove_device(self, uid: str, device: str) -> None:
        self._db.document(f"utenti/{uid}/telefoni/{device}").delete()

    def send(self, tokens: list[str], title: str, body: str, tag: str = "cnv-novita") -> list[str | None]:
        """Send to each phone; for each one None if delivered, "gone" if the phone is no
        longer reachable (app removed), or the error."""
        from firebase_admin import exceptions, messaging

        messages = [
            messaging.Message(
                token=token,
                notification=messaging.Notification(title=title, body=body),
                data={"page": "in_sala"},
                android=messaging.AndroidConfig(
                    priority="high",
                    ttl=TTL_FCM,
                    notification=messaging.AndroidNotification(tag=tag, color="#BB86FC"),
                ),
            )
            for token in tokens
        ]
        result = messaging.send_each(messages, app=self._app)
        outcome: list[str | None] = []
        for response in result.responses:
            err = response.exception
            if err is None:
                outcome.append(None)
            elif isinstance(err, (messaging.UnregisteredError, messaging.SenderIdMismatchError, exceptions.InvalidArgumentError)):
                outcome.append("gone")
            else:
                outcome.append(str(err))
        return outcome


def send_fcm(payload: dict, client) -> dict:
    """Send the news to every admitted account, as each one asked; forget the phones that
    are gone. Returns the counts, without names or e-mails (the log is public)."""
    counts = {"accounts": 0, "phones": 0, "sent": 0, "removed": 0, "errors": 0}
    allow = client.allow_list()
    for uid, doc in client.accounts():
        votes = doc.get("votes") or {}
        messages = [
            (message, tag)
            for message, tag in (
                (notification_for(payload, votes, doc.get("notify")), "cnv-novita"),
                (last_days_notification(payload, votes, doc.get("lastDays") is True), "cnv-ultimi-giorni"),
            )
            if message is not None
        ]
        if not messages:
            continue
        email, verified = client.email_of(uid)
        if not is_admitted(uid, email, verified, allow):
            continue
        devices = [(d, t) for d, t in client.devices(uid) if t]
        if not devices:
            continue
        counts["accounts"] += 1
        counts["phones"] += len(devices)
        for message, tag in messages:
            gone = set()
            for (device, _), outcome in zip(devices, client.send([t for _, t in devices], *message, tag=tag)):
                if outcome is None:
                    counts["sent"] += 1
                elif outcome == "gone":
                    client.remove_device(uid, device)
                    gone.add(device)
                    counts["removed"] += 1
                else:
                    counts["errors"] += 1
                    print(f"::warning::Notifica non consegnata a un telefono: {outcome}")
            devices = [(d, t) for d, t in devices if d not in gone]  # not tried again for the next notice
            if not devices:
                break
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Notifiche di CNV sul telefono")
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="sceglie i film nuovi in sala e scrive il messaggio")
    prep.add_argument("--out", required=True, type=Path)
    prep.add_argument("--prova", action="store_true", help="senza film nuovi, un messaggio di prova")
    snd = commands.add_parser("send", help="invia il messaggio all'app Android")
    snd.add_argument("file", type=Path)
    commands.add_parser("verifica", help="confronta gli ultimi giorni indovinati con gli spettacoli veri")
    args = parser.parse_args()

    if args.command == "prepare":
        init_db()
        with SessionLocal() as db:
            # Today's guesses first, so that the message can announce them
            # (read inside the session: after it closes the films can no longer be read)
            leaving = [(_title(lf.film), lf.last_day) for lf in record_leaving(db, date.today())]
            payload = prepare(db, test=args.prova)
        args.out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"Film nuovi in sala: {len(payload.get('films', []))}")
        print(f"Ultimi giorni: {len(leaving)} film, da annunciare a chi l'ha chiesto: {len(payload.get('last_days', []))}")
        for title, last_day in leaving:
            print(f"   * {title}: ultimo giorno {last_day:%d/%m}")
        return 0

    if args.command == "verifica":
        init_db()
        with SessionLocal() as db:
            checks = check_guesses(db, date.today())
        for c in checks:
            real = f"{c.real_last_day:%d/%m}" if c.real_last_day else "nessuno"
            outcome = "giusto" if c.right else "SBAGLIATO"
            print(f"{outcome:9} {c.title}: visto il {c.found_on:%d/%m}, ultimo giorno {c.last_day:%d/%m}, vero {real}")
        right = sum(c.right for c in checks)
        print(f"Indovinati {right} su {len(checks)}" if checks else "Nessun ultimo giorno da controllare per ora")
        return 0

    payload = json.loads(args.file.read_text(encoding="utf-8")) if args.file.exists() else {}
    if not payload:
        print("Nessuna notifica da inviare")
        return 0

    service_account = os.getenv("FIREBASE_SERVICE_ACCOUNT", "")
    if not service_account:
        # Marked anyway: turning notifications on later must not bring a flood of old news
        print("App Android: notifiche non attive, manca il segreto FIREBASE_SERVICE_ACCOUNT")
    else:
        try:
            counts = send_fcm(payload, FirebaseClient(service_account))
        except Exception as err:
            # The films stay unmarked: the next night announces them again. The site is
            # already published, but the step fails so that the problem is seen.
            print(f"::error::Notifiche dell'app non inviate (riprovo al prossimo giro): {err}")
            return 1
        print(
            f"App Android: {counts['sent']} notifiche consegnate a {counts['accounts']} account "
            f"({counts['removed']} telefoni non più raggiungibili tolti, {counts['errors']} errori)"
        )
    ids = payload.get("ids") or []
    last_ids = payload.get("last_day_ids") or []
    if ids or last_ids:
        init_db()
        with SessionLocal() as db:
            print(f"Film segnati come notificati: {mark_notified(db, ids)}")
            print(f"Ultimi giorni segnati come annunciati: {mark_last_days(db, last_ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
