"""Read secrets from the repo's .env file. Never print, log or return them in plain text.

Secrets are read only from .env (not from system environment variables), so swapping
the Anthropic key means editing one line in .env plus ``budget.key_label`` in config.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values
from pydantic import SecretStr

from quantagents.config import REPO_ROOT

SECRET_NAMES = ("ANTHROPIC_API_KEY", "ALPACA_API_KEY", "ALPACA_SECRET_KEY", "SEC_USER_AGENT")
# SEC_USER_AGENT holds an email (personal data) so it is masked too.

_KNOWN_VALUES: set[str] = set()


@dataclass(frozen=True)
class Secrets:
    values: dict[str, SecretStr]

    def get(self, name: str) -> str:
        if name not in self.values:
            raise MissingSecretError(
                f"{name} is not set. Add it to the .env file in the repo folder "
                f"(see .env.example).")
        return self.values[name].get_secret_value()

    def has(self, name: str) -> bool:
        return name in self.values

    def status(self) -> dict[str, str]:
        """{name: 'present' | 'MISSING'} - safe to print."""
        return {n: ("present" if n in self.values else "MISSING") for n in SECRET_NAMES}

    def __repr__(self) -> str:  # never show values
        return f"Secrets({self.status()})"

    __str__ = __repr__


class MissingSecretError(RuntimeError):
    pass


def load_secrets(env_file: str | Path | None = None) -> Secrets:
    env_file = Path(env_file) if env_file else REPO_ROOT / ".env"
    raw = dotenv_values(env_file) if env_file.exists() else {}
    vals: dict[str, SecretStr] = {}
    for name in SECRET_NAMES:
        v = (raw.get(name) or "").strip().strip('"').strip("'")
        if v:
            vals[name] = SecretStr(v)
            if len(v) >= 6:
                _KNOWN_VALUES.add(v)
    return Secrets(vals)


def redact(text: str) -> str:
    """Replace any loaded secret value inside ``text`` with [REDACTED]."""
    for v in sorted(_KNOWN_VALUES, key=len, reverse=True):
        if v in text:
            text = text.replace(v, "[REDACTED]")
    return text


class RedactingFilter(logging.Filter):
    """Logging filter that strips secret values from every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        clean = redact(msg)
        if clean != msg:
            record.msg, record.args = clean, None
        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            exc.args = tuple(redact(str(a)) for a in exc.args)
            record.exc_text = None
        return True
