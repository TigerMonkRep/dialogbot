"""SMS templates: one tone, one signature, one segment, and the connector fills them from approved facts only."""
from __future__ import annotations

from app.modules.integrations import sms_templates as t


def test_every_sms_is_one_segment_signed_by_the_business_and_plain():
    for key, text in t.samples().items():
        assert len(text) <= t.SEGMENT, f"{key}: {len(text)} tegn"
        assert text.endswith("Vh Hansen VVS"), key
        assert "Dialogbot" not in text and "http" not in text and "!" not in text, key


def test_booking_greeting_only_with_a_name():
    assert t.booking("Hansen VVS", "Mette Nielsen", "Besigtigelse", "tirsdag kl. 10").startswith("Hej Mette. Din tid hos Hansen VVS")
    assert t.booking("Hansen VVS", "", "Besigtigelse", "tirsdag kl. 10").startswith("Din tid hos Hansen VVS")  # never "Hej. "


def test_the_connector_uses_the_templates():
    import re

    from app.modules.integrations.connectors import sms

    src = open(sms.__file__, encoding="utf-8").read()
    assert "texts." in src and not re.search(r'f".*Vh \{ws\.name\}"', src)  # no second copy of the wording
