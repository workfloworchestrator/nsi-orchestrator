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

from pydantic_settings import BaseSettings

from settings import Settings, settings


def test_settings_is_basesettings_subclass() -> None:
    assert issubclass(Settings, BaseSettings)


def test_module_singleton_instantiated() -> None:
    assert isinstance(settings, Settings)
