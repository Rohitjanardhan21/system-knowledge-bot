import logging

from backend.core.cognitive.notifier import _FallbackNotifier


def test_fallback_notifier_logs_alert_without_writing_to_stdout(caplog, capsys):
    with caplog.at_level(logging.WARNING, logger="cvis.notifications"):
        assert _FallbackNotifier().send("System alert", "CPU is high ⚠️")

    assert "System alert" in caplog.text
    assert "CPU is high ⚠️" in caplog.text
    assert capsys.readouterr().out == ""
