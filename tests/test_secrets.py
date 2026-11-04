import logging

import pytest

from quantagents.env_secrets import MissingSecretError, RedactingFilter, load_secrets, redact

FAKE_KEY = "sk-ant-api03-FAKEFAKEFAKE1234567890"


@pytest.fixture
def env_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text(f"ANTHROPIC_API_KEY={FAKE_KEY}\nALPACA_API_KEY=PKFAKE12345\n"
                 "SEC_USER_AGENT=QuantAgents research someone@example.com\n", encoding="utf-8")
    return f


def test_values_loaded_but_never_shown(env_file):
    s = load_secrets(env_file)
    assert s.get("ANTHROPIC_API_KEY") == FAKE_KEY
    assert FAKE_KEY not in repr(s) and FAKE_KEY not in str(s)
    assert s.status()["ANTHROPIC_API_KEY"] == "present"
    assert s.status()["ALPACA_SECRET_KEY"] == "MISSING"


def test_missing_secret_message_has_no_values(env_file):
    s = load_secrets(env_file)
    with pytest.raises(MissingSecretError) as e:
        s.get("ALPACA_SECRET_KEY")
    assert FAKE_KEY not in str(e.value)


def test_only_dotenv_is_read(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-system-environment")
    s = load_secrets(tmp_path / "missing.env")
    assert not s.has("ANTHROPIC_API_KEY")


def test_log_records_redacted(env_file, caplog):
    load_secrets(env_file)
    logger = logging.getLogger("t")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO):
        logger.info("calling with key %s", FAKE_KEY)
        try:
            raise ValueError(f"bad key {FAKE_KEY}")
        except ValueError:
            logger.exception("failed")
    assert FAKE_KEY not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_redact_email(env_file):
    load_secrets(env_file)
    assert "someone@example.com" not in redact("UA=QuantAgents research someone@example.com")
