"""Tests for the phone notifications (app/push.py); Firebase is faked."""

from __future__ import annotations

import json
import sys

from datetime import date, time

from app import push
from app.db.models import Cinema, Film, Showtime


def film(db, title, status="in_sala", pushed=False, **fields):
    f = Film(raw_title=title, normalized_title=title.lower(), status=status, in_sala_pushed=pushed, **fields)
    db.add(f)
    db.flush()
    return f


def test_prepare_notifies_each_new_film_once(db):
    hope = film(db, "HOPE", tmdb_id=1, tmdb_title="Hope", tmdb_match_status="abbinato")
    clay = film(db, "Clayface")
    film(db, "Gia notificato", pushed=True)
    film(db, "Presto", status="in_uscita")
    db.commit()

    payload = push.prepare(db)
    assert payload == {
        "films": [{"id": clay.id, "title": "Clayface"}, {"id": hope.id, "title": "Hope"}],
        "more": 0,
        "ids": [clay.id, hope.id],
    }
    assert not hope.in_sala_pushed and not clay.in_sala_pushed  # marked only once the news went out
    assert push.prepare(db) == payload  # a night that failed announces them again
    assert push.mark_notified(db, payload["ids"]) == 2
    assert hope.in_sala_pushed and clay.in_sala_pushed
    assert push.prepare(db) == {}  # nothing new the next night
    assert push.prepare(db, test=True)["title"] == "CNV"  # manual run with "prova"


def test_prepare_marks_the_films_out_today(db):
    garden = Cinema(slug="garden", name="Garden", url="https://garden.example")
    db.add(garden)
    out_today, back = film(db, "Esce oggi"), film(db, "Ritorna")
    db.flush()
    db.add_all([
        Showtime(film_id=out_today.id, cinema_id=garden.id, date=date(2026, 11, 16), time=time(21, 0), source_url=""),
        Showtime(film_id=back.id, cinema_id=garden.id, date=date(2026, 5, 2), time=time(21, 0), source_url=""),  # shown in May
        Showtime(film_id=back.id, cinema_id=garden.id, date=date(2026, 11, 16), time=time(18, 0), source_url=""),
    ])
    db.commit()
    payload = push.prepare(db, today=date(2026, 11, 16))
    assert payload["films"] == [
        {"id": out_today.id, "title": "Esce oggi", "today": True},
        {"id": back.id, "title": "Ritorna"},
    ]


def test_notification_says_out_today_for_a_single_film():
    payload = {"films": [{"id": 1, "title": "Hope", "today": True}], "more": 0}
    assert push.notification_for(payload, {"1": "V"}, "v") == ("🎬 Esce oggi: Hope", "Hope")
    assert push.notification_for(payload, {}, "all") == ("🎬 Esce oggi: Hope", "Hope")
    back = {"films": [{"id": 1, "title": "Hope"}], "more": 0}
    assert push.notification_for(back, {"1": "V"}, "v")[0] == "🎬 In sala: Hope"
    assert push.notification_for(back, {}, "all")[0] == "🎬 Nuovo in sala: Hope"


def test_prepare_keeps_the_message_small(db):
    for i in range(push.MAX_FILMS + 3):
        film(db, f"Film {i:02d}")
    db.commit()
    payload = push.prepare(db)
    assert len(payload["films"]) == push.MAX_FILMS and payload["more"] == 3
    assert len(payload["ids"]) == push.MAX_FILMS + 3  # all of them get marked, not only the listed ones
    assert len(json.dumps(payload).encode()) < 3000


# ---------------------------------------------------------------------- Android app (FCM)

NEWS = {"films": [{"id": 1, "title": "Clayface"}, {"id": 2, "title": "Hope"}, {"id": 3, "title": "Dune"}], "more": 0}


def test_notification_puts_my_v_films_first():
    title, body = push.notification_for(NEWS, {"2": "V", "3": "?"}, "all")
    assert title == "🎬 In sala: Hope"
    assert body == "Hope · e anche: Clayface, Dune"
    title, body = push.notification_for(NEWS, {"2": "V", "1": "V"}, "v")
    assert title == "🎬 In sala 2 film che volevi vedere" and body == "Clayface, Hope"


def test_notification_without_v_films():
    assert push.notification_for(NEWS, {}, "all") == ("🎬 3 film nuovi in sala", "Clayface, Hope, Dune")
    assert push.notification_for({"films": [{"id": 1, "title": "Hope"}], "more": 0}, {}, "all") == ("🎬 Nuovo in sala: Hope", "Hope")
    assert push.notification_for({**NEWS, "more": 4}, {}, "all") == ("🎬 7 film nuovi in sala", "Clayface, Hope, Dune e altri 4")
    assert push.notification_for(NEWS, {"1": "?"}, "v") is None  # only my V, and none of them


def test_notification_needs_to_be_asked_for():
    assert push.notification_for(NEWS, {"2": "V"}, None) is None
    assert push.notification_for(NEWS, {"2": "V"}, "off") is None
    assert push.notification_for(NEWS, {}, "boh") is None
    assert push.notification_for({}, {}, "all") is None
    assert push.notification_for({"title": "CNV", "body": "prova"}, {}, "v") == ("CNV", "prova")


def test_notification_text_stays_short():
    many = {"films": [{"id": i, "title": f"Un titolo molto lungo numero {i}"} for i in range(20)], "more": 0}
    _, body = push.notification_for(many, {}, "all")
    assert len(body) <= push.MAX_BODY and body.endswith("…")


def test_admission_is_the_same_as_the_rules():
    allow = {"admin": "capo", "email": ["amico@example.com"]}
    assert push.is_admitted("capo", None, False, allow)
    assert push.is_admitted("x", "Amico@Example.com", True, allow)
    assert not push.is_admitted("x", "amico@example.com", False, allow)  # e-mail not confirmed
    assert not push.is_admitted("y", "estraneo@example.com", True, allow)
    assert not push.is_admitted("capo", None, False, {})  # no list: nobody


class FakeFirebase:
    def __init__(self):
        self.allow = {"admin": "capo", "email": ["amico@example.com", "zitto@example.com"]}
        self.docs = {
            "capo": {"votes": {"2": "V"}, "notify": "all"},
            "amico": {"votes": {}, "notify": "v"},  # only V: nothing tonight
            "zitto": {"votes": {"1": "V"}},  # never turned them on
            "fuori": {"votes": {"1": "V"}, "notify": "all"},  # removed from the list
            "nuovo": {"votes": {"3": "V"}, "notify": "all"},
        }
        self.users = {"capo": ("capo@gmail.com", True), "amico": ("amico@example.com", True),
                      "zitto": ("zitto@example.com", True), "fuori": ("fuori@example.com", True),
                      "nuovo": ("Amico@example.com", False)}
        self.phones = {"capo": [("a1", "tok-vivo"), ("a2", "tok-morto"), ("a3", "")], "fuori": [("f1", "tok-f")],
                       "nuovo": [("n1", "tok-n")]}
        self.sent, self.removed, self.tags = [], [], []

    def allow_list(self):
        return self.allow

    def accounts(self):
        return iter(self.docs.items())

    def email_of(self, uid):
        return self.users[uid]

    def devices(self, uid):
        return self.phones.get(uid, [])

    def remove_device(self, uid, device):
        self.removed.append((uid, device))

    def send(self, tokens, title, body, tag="cnv-novita"):
        self.sent.append((tokens, title, body))
        self.tags.append(tag)
        return [None if t == "tok-vivo" else "gone" for t in tokens]


def test_send_fcm_to_admitted_accounts_that_asked():
    fake = FakeFirebase()
    counts = push.send_fcm(NEWS, fake)
    assert fake.sent == [(["tok-vivo", "tok-morto"], "🎬 In sala: Hope", "Hope · e anche: Clayface, Dune")]
    assert fake.removed == [("capo", "a2")]  # the app was removed from that phone
    assert counts == {"accounts": 1, "phones": 2, "sent": 1, "removed": 1, "errors": 0}


def test_prepare_command_lists_the_last_days_and_the_check_command_runs(tmp_path, monkeypatch, capsys):
    from datetime import timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'cnv.db'}")
    Base.metadata.create_all(engine)
    make_session = sessionmaker(bind=engine)
    today = date.today()
    with make_session() as db:
        cinema = Cinema(slug="garden", name="Garden", url="https://garden.example")
        db.add(cinema)
        stays, leaves = film(db, "Resta", pushed=True), film(db, "Se ne va", pushed=True)
        for f, days in ((stays, (0, 1, 2)), (leaves, (0, 1))):
            for n in days:
                db.add(Showtime(film_id=f.id, cinema_id=cinema.id, date=today + timedelta(days=n), time=time(21, 0),
                                source_url=""))
        db.commit()
    monkeypatch.setattr(push, "SessionLocal", make_session)
    monkeypatch.setattr(push, "init_db", lambda: None)

    monkeypatch.setattr(sys, "argv", ["app.push", "prepare", "--out", str(tmp_path / "notifica.json")])
    assert push.main() == 0
    out = capsys.readouterr().out
    assert "Ultimi giorni: 1 film, da annunciare a chi l'ha chiesto: 1" in out
    assert f"Se ne va: ultimo giorno {today + timedelta(days=1):%d/%m}" in out

    monkeypatch.setattr(sys, "argv", ["app.push", "verifica"])
    assert push.main() == 0
    assert "Nessun ultimo giorno da controllare per ora" in capsys.readouterr().out
    engine.dispose()


def test_send_command_without_firebase_secret(tmp_path, monkeypatch, capsys):
    message = tmp_path / "notifica.json"
    message.write_text(json.dumps(NEWS), encoding="utf-8")
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT", raising=False)
    monkeypatch.setattr(sys, "argv", ["app.push", "send", str(message)])
    assert push.main() == 0
    assert "manca il segreto FIREBASE_SERVICE_ACCOUNT" in capsys.readouterr().out


def _session_with_new_film(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'cnv.db'}")
    Base.metadata.create_all(engine)
    make_session = sessionmaker(bind=engine)
    with make_session() as db:
        new = film(db, "Hope")
        db.commit()
        film_id = new.id
    monkeypatch.setattr(push, "SessionLocal", make_session)
    monkeypatch.setattr(push, "init_db", lambda: None)
    return engine, make_session, film_id


def test_send_command_failure_fails_the_step_and_keeps_films_unmarked(tmp_path, monkeypatch, capsys):
    engine, make_session, film_id = _session_with_new_film(tmp_path, monkeypatch)
    message = tmp_path / "notifica.json"
    message.write_text(json.dumps({**NEWS, "ids": [film_id]}), encoding="utf-8")
    monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT", "{non valido")
    monkeypatch.setattr(push, "FirebaseClient", lambda secret: (_ for _ in ()).throw(ValueError("chiave non valida")))
    monkeypatch.setattr(sys, "argv", ["app.push", "send", str(message)])
    assert push.main() == 1
    assert "::error::Notifiche dell'app non inviate (riprovo al prossimo giro): chiave non valida" in capsys.readouterr().out
    with make_session() as db:
        assert db.get(Film, film_id).in_sala_pushed is False  # announced again next time
    engine.dispose()


def test_send_command_marks_the_films_once_sent(tmp_path, monkeypatch, capsys):
    engine, make_session, film_id = _session_with_new_film(tmp_path, monkeypatch)
    message = tmp_path / "notifica.json"
    message.write_text(json.dumps({**NEWS, "ids": [film_id]}), encoding="utf-8")
    monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT", "{}")
    monkeypatch.setattr(push, "FirebaseClient", lambda secret: FakeFirebase())
    monkeypatch.setattr(sys, "argv", ["app.push", "send", str(message)])
    assert push.main() == 0
    with make_session() as db:
        assert db.get(Film, film_id).in_sala_pushed is True
    engine.dispose()


# ------------------------------------------------------------------ ultimi giorni

LEAVING = {
    "last_days": [{"id": 1, "title": "Clayface", "last_day": "2026-11-26"},
                  {"id": 2, "title": "Hope", "last_day": "2026-11-27"},
                  {"id": 3, "title": "Dune", "last_day": "2026-11-29"}],
    "last_day_ids": [10, 11, 12],
    "today": "2026-11-26",
}


def test_last_days_notice_only_for_my_v_films_and_only_if_asked():
    assert push.last_days_notification(LEAVING, {"1": "V"}, True) == ("⏳ Ultimo giorno: Clayface", "Oggi è l'ultimo giorno in sala.")
    assert push.last_days_notification(LEAVING, {"2": "V"}, True) == ("⏳ Ultimi giorni: Hope", "In sala fino a domani.")
    assert push.last_days_notification(LEAVING, {"3": "V"}, True) == ("⏳ Ultimi giorni: Dune", "In sala fino a dom 29/11.")
    assert push.last_days_notification(LEAVING, {"1": "V", "3": "V", "2": "?"}, True) == (
        "⏳ Ultimi giorni per 2 film che volevi vedere", "Clayface (ultimo giorno oggi), Dune (fino a dom 29/11)")
    assert push.last_days_notification(LEAVING, {"1": "V"}, False) is None  # switch off
    assert push.last_days_notification(LEAVING, {"2": "?"}, True) is None  # not a V
    assert push.last_days_notification(NEWS, {"1": "V"}, True) is None  # nothing leaving tonight


def test_a_message_with_only_last_days_is_not_the_test_message():
    assert push.notification_for(LEAVING, {"1": "V"}, "all") is None


def test_send_fcm_sends_the_last_days_apart_to_who_asked():
    fake = FakeFirebase()
    fake.docs["capo"]["lastDays"] = True
    fake.docs["amico"] = {"votes": {"2": "V"}, "notify": "off", "lastDays": True}  # only the last days
    fake.phones["amico"] = [("b1", "tok-vivo")]
    counts = push.send_fcm({**NEWS, **LEAVING}, fake)
    assert fake.sent[:2] == [
        (["tok-vivo", "tok-morto"], "🎬 In sala: Hope", "Hope · e anche: Clayface, Dune"),
        (["tok-vivo"], "⏳ Ultimi giorni: Hope", "In sala fino a domani."),  # the phone that is gone is not tried again
    ]
    assert fake.tags[:2] == ["cnv-novita", "cnv-ultimi-giorni"]
    assert (["tok-vivo"], "⏳ Ultimi giorni: Hope", "In sala fino a domani.") in fake.sent[2:]  # amico
    assert counts["removed"] == 1


def test_prepare_announces_each_leaving_film_once(db):
    from datetime import timedelta

    from app.db.models import LastDays

    today = date(2026, 11, 26)
    hope = film(db, "Hope", pushed=True)
    clay = film(db, "Clayface", pushed=True)
    event = film(db, "Concerto", pushed=True, is_event=True)
    gone = film(db, "Uscito", status="uscito", pushed=True)
    told = film(db, "Gia detto", pushed=True)
    db.add_all([
        LastDays(film_id=hope.id, last_day=today + timedelta(days=1), found_on=today - timedelta(days=1)),
        LastDays(film_id=hope.id, last_day=today + timedelta(days=2), found_on=today),  # the latest guess counts
        LastDays(film_id=clay.id, last_day=today, found_on=today),
        LastDays(film_id=clay.id, last_day=today - timedelta(days=3), found_on=today - timedelta(days=4)),  # past
        LastDays(film_id=event.id, last_day=today, found_on=today),
        LastDays(film_id=gone.id, last_day=today, found_on=today),
        LastDays(film_id=told.id, last_day=today + timedelta(days=1), found_on=today - timedelta(days=2), notified=True),
        LastDays(film_id=told.id, last_day=today + timedelta(days=3), found_on=today),  # told 2 days ago: not again
    ])
    db.commit()
    payload = push.prepare(db, today=today)
    assert payload["last_days"] == [
        {"id": clay.id, "title": "Clayface", "last_day": "2026-11-26"},
        {"id": hope.id, "title": "Hope", "last_day": "2026-11-28"},
    ]
    assert payload["today"] == "2026-11-26"
    assert "films" not in payload
    assert push.mark_last_days(db, payload["last_day_ids"]) == 2
    assert push.prepare(db, today=today) == {}  # the second run of the night: nothing new


def test_send_command_marks_the_last_days_once_sent(tmp_path, monkeypatch, capsys):
    from app.db.models import LastDays

    engine, make_session, film_id = _session_with_new_film(tmp_path, monkeypatch)
    with make_session() as db:
        row = LastDays(film_id=film_id, last_day=date(2026, 11, 27), found_on=date(2026, 11, 26))
        db.add(row)
        db.commit()
        row_id = row.id
    message = tmp_path / "notifica.json"
    message.write_text(json.dumps({**LEAVING, "last_day_ids": [row_id]}), encoding="utf-8")
    monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT", "{}")
    monkeypatch.setattr(push, "FirebaseClient", lambda secret: FakeFirebase())
    monkeypatch.setattr(sys, "argv", ["app.push", "send", str(message)])
    assert push.main() == 0
    assert "Ultimi giorni segnati come annunciati: 1" in capsys.readouterr().out
    with make_session() as db:
        assert db.get(LastDays, row_id).notified is True
    engine.dispose()


def test_send_command_without_secret_still_marks_the_films(tmp_path, monkeypatch, capsys):
    engine, make_session, film_id = _session_with_new_film(tmp_path, monkeypatch)
    message = tmp_path / "notifica.json"
    message.write_text(json.dumps({**NEWS, "ids": [film_id]}), encoding="utf-8")
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT", raising=False)
    monkeypatch.setattr(sys, "argv", ["app.push", "send", str(message)])
    assert push.main() == 0  # turning notifications on later must not bring old news
    with make_session() as db:
        assert db.get(Film, film_id).in_sala_pushed is True
    engine.dispose()
