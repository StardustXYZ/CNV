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
