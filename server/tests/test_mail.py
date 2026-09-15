import pytest

from ffdraft import mail
from ffdraft.config import Settings


def test_not_configured_is_an_error(tmp_path):
    with pytest.raises(RuntimeError, match="not configured"):
        mail.send(Settings(data_dir=tmp_path), "a@b.co", "s", "b")
    assert Settings(data_dir=tmp_path, resend_api_key="re_x").mail_configured is False  # no sender
    assert Settings(data_dir=tmp_path, resend_api_key="re_x", mail_from="F <f@x.co>").mail_configured is True
    assert Settings(data_dir=tmp_path, smtp_host="h", smtp_from="f@x.co").mail_configured is True


def test_resend_is_preferred_and_errors_are_surfaced(tmp_path, monkeypatch):
    import requests

    calls = []

    class Resp:
        def __init__(self, status, payload):
            self.status_code, self._payload, self.text = status, payload, str(payload)

        def json(self):
            return self._payload

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        return Resp(200, {"id": "1"}) if json["to"] != ["bad@x.co"] else Resp(403, {"message": "The x.co domain is not verified"})

    monkeypatch.setattr(requests, "post", fake_post)
    cfg = Settings(data_dir=tmp_path, resend_api_key="re_test", mail_from="Aljux Fantasy <invites@x.co>", mail_reply_to="me@x.co", smtp_host="ignored")
    assert mail.send(cfg, "friend@x.co", "Subject", "Body") == "1"
    url, payload, headers = calls[-1]
    assert url == mail.RESEND_URL and headers["Authorization"] == "Bearer re_test"
    assert payload == {"from": "Aljux Fantasy <invites@x.co>", "to": ["friend@x.co"], "subject": "Subject", "text": "Body", "reply_to": "me@x.co"}
    with pytest.raises(RuntimeError, match="Resend 403: The x.co domain is not verified"):
        mail.send(cfg, "bad@x.co", "s", "b")
