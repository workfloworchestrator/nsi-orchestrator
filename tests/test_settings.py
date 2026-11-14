# Copyright 2026 SURF.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Smoke tests for the application settings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_settings import BaseSettings

from settings import Settings, _psycopg_dsn, settings


def test_settings_is_basesettings_subclass() -> None:
    assert issubclass(Settings, BaseSettings)


def test_module_singleton_instantiated() -> None:
    assert isinstance(settings, Settings)


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        pytest.param("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db", id="bare-postgresql-coerced"),
        pytest.param("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db", id="already-psycopg-kept"),
        pytest.param("postgresql+psycopg2://u:p@h/db", "postgresql+psycopg2://u:p@h/db", id="other-driver-kept"),
        pytest.param("sqlite:///x.db", "sqlite:///x.db", id="non-postgres-kept"),
    ],
)
def test_psycopg_dsn(uri: str, expected: str) -> None:
    assert _psycopg_dsn(uri) == expected


@pytest.mark.parametrize(
    "timeout", [pytest.param(0, id="zero-is-not-no-limit"), pytest.param(31_536_001, id="past-a-year")]
)
def test_terminate_confirm_timeout_is_bounded(timeout: int) -> None:
    """A deadline of now, or past what a date can hold, would fail every terminate."""
    with pytest.raises(ValidationError):
        Settings(terminate_confirm_timeout=timeout)
