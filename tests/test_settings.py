"""Smoke tests for the application settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings

from settings import Settings, settings


def test_settings_is_basesettings_subclass() -> None:
    assert issubclass(Settings, BaseSettings)


def test_module_singleton_instantiated() -> None:
    assert isinstance(settings, Settings)
