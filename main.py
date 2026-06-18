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

from pathlib import Path

import typer
from nwastdlib.logging import initialise_logging
from orchestrator.core import app_settings
from orchestrator.core.cli.main import app as core_cli
from orchestrator.core.db import init_database
from orchestrator.core.log_config import LOGGER_OVERRIDES

import products  # noqa: F401  Registers subscription models in SUBSCRIPTION_MODEL_REGISTRY
import workflows  # noqa: F401  Registers the topology workflow instances


def init_cli_app() -> typer.Typer:
    initialise_logging(LOGGER_OVERRIDES)
    init_database(app_settings)
    # Serve our project translations from ./translations unless overridden via TRANSLATIONS_DIR.
    if app_settings.TRANSLATIONS_DIR is None:
        app_settings.TRANSLATIONS_DIR = Path("translations")
    return core_cli()  # type: ignore[no-any-return]


if __name__ == "__main__":
    init_cli_app()
