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

"""Tests for the project translations.

Core's nightly `task_validate_products` fails on any registered workflow without an en-GB workflow
translation; this runs the same lookup, so a new workflow or task cannot ship without one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from orchestrator.core.services.translations import generate_translations
from orchestrator.core.settings import app_settings
from orchestrator.core.workflows import ALL_WORKFLOWS

import workflows  # noqa: F401  # registers this project's workflows in ALL_WORKFLOWS

TRANSLATIONS_DIR = Path(__file__).parent.parent / "translations"


def test_every_workflow_has_a_translation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "TRANSLATIONS_DIR", TRANSLATIONS_DIR)
    translations = generate_translations("en-GB")["workflow"]
    assert isinstance(translations, dict)
    assert sorted(name for name in ALL_WORKFLOWS if name not in translations) == []
