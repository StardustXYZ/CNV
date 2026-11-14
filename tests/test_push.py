"""Tests for the phone notifications (app/push.py); the push service is faked."""

from __future__ import annotations

import json
import sys
import types

from app import push
from app.db.models import Film


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
    assert payload == {"films": [{"id": clay.id, "title": "Clayface"}, {"id": hope.id, "title": "Hope"}], "more": 0}
    assert hope.in_sala_pushed and clay.in_sala_pushed
    assert push.prepare(db) == {}  # nothing new the next night
    assert push.prepare(db, test=True)["title"] == "CNV"  # manual run with "prova"


def test_prepare_keeps_the_message_small(db):
    for i in range(push.MAX_FILMS + 3):
        film(db, f"Film {i:02d}")
    db.commit()
    payload = push.prepare(db)
    assert len(payload["films"]) == push.MAX_FILMS and payload["more"] == 3
    assert len(json.dumps(payload).encode()) < 3000


def test_send_uses_the_secrets(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "pywebpush", types.SimpleNamespace(webpush=lambda **kw: calls.append(kw)))
    push.send({"films": [{"id": 1, "title": "Città"}]}, '{"endpoint": "https://push.example/abc", "keys": {}}', "chiave")
    (call,) = calls
    assert call["subscription_info"]["endpoint"] == "https://push.example/abc"
    assert json.loads(call["data"]) == {"films": [{"id": 1, "title": "Città"}]} and "Città" in call["data"]
    assert call["vapid_private_key"] == "chiave" and call["vapid_claims"] == {"sub": push.VAPID_CONTACT}


def test_send_command_without_secrets_does_nothing(tmp_path, monkeypatch, capsys):
    message = tmp_path / "notifica.json"
    message.write_text(json.dumps({"films": [{"id": 1, "title": "Hope"}]}), encoding="utf-8")
    monkeypatch.delenv("PUSH_SUBSCRIPTION", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["app.push", "send", str(message)])
    assert push.main() == 0
    assert "Notifiche non attive" in capsys.readouterr().out


def test_send_command_reports_a_refused_push_without_failing(tmp_path, monkeypatch, capsys):
    message = tmp_path / "notifica.json"
    message.write_text(json.dumps({"films": [{"id": 1, "title": "Hope"}]}), encoding="utf-8")
    monkeypatch.setenv("PUSH_SUBSCRIPTION", "{}")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "chiave")

    def refuse(**kw):
        raise RuntimeError("410 Gone")

    monkeypatch.setitem(sys.modules, "pywebpush", types.SimpleNamespace(webpush=refuse))
    monkeypatch.setattr(sys, "argv", ["app.push", "send", str(message)])
    assert push.main() == 0  # the site is already published: a warning, not a failure
    assert "::warning::Notifica non inviata: 410 Gone" in capsys.readouterr().out


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
        self.sent, self.removed = [], []

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

    def send(self, tokens, title, body):
        self.sent.append((tokens, title, body))
        return [None if t == "tok-vivo" else "gone" for t in tokens]


def test_send_fcm_to_admitted_accounts_that_asked():
    fake = FakeFirebase()
    counts = push.send_fcm(NEWS, fake)
    assert fake.sent == [(["tok-vivo", "tok-morto"], "🎬 In sala: Hope", "Hope · e anche: Clayface, Dune")]
    assert fake.removed == [("capo", "a2")]  # the app was removed from that phone
    assert counts == {"accounts": 1, "phones": 2, "sent": 1, "removed": 1, "errors": 0}


def test_send_command_without_firebase_secret(tmp_path, monkeypatch, capsys):
    message = tmp_path / "notifica.json"
    message.write_text(json.dumps(NEWS), encoding="utf-8")
    for name in ("FIREBASE_SERVICE_ACCOUNT", "PUSH_SUBSCRIPTION", "VAPID_PRIVATE_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sys, "argv", ["app.push", "send", str(message)])
    assert push.main() == 0
    assert "manca il segreto FIREBASE_SERVICE_ACCOUNT" in capsys.readouterr().out


def test_send_command_reports_firebase_problems_without_failing(tmp_path, monkeypatch, capsys):
    message = tmp_path / "notifica.json"
    message.write_text(json.dumps(NEWS), encoding="utf-8")
    monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT", "{non valido")
    monkeypatch.delenv("PUSH_SUBSCRIPTION", raising=False)
    monkeypatch.setattr(push, "FirebaseClient", lambda secret: (_ for _ in ()).throw(ValueError("chiave non valida")))
    monkeypatch.setattr(sys, "argv", ["app.push", "send", str(message)])
    assert push.main() == 0
    assert "::warning::Notifiche dell'app non inviate: chiave non valida" in capsys.readouterr().out
