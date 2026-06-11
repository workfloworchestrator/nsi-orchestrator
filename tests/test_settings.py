"""Smoke tests for the orchestrator settings."""

from __future__ import annotations

import pytest

from settings import OrchestratorSettings


def test_default_host_and_port() -> None:
    settings = OrchestratorSettings()
    assert settings.HOST == "127.0.0.1"
    assert settings.PORT == 8080


def test_port_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "9090")
    assert OrchestratorSettings().PORT == 9090
