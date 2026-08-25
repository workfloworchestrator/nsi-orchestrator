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

"""Guard the wheel's top-level module list.

The tests run from the repo root, where every root module imports whether or not it is packaged, so
a module missing from ``py-modules`` only fails in the container — and, because ``main.py`` imports
them at module scope, it fails every CLI entry point at once, including ``db upgrade heads``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def test_every_root_module_is_packaged() -> None:
    packaged = set(tomllib.loads((_REPO / "pyproject.toml").read_text())["tool"]["setuptools"]["py-modules"])
    on_disk = {path.stem for path in _REPO.glob("*.py")}

    assert on_disk - packaged == set(), "add these to [tool.setuptools] py-modules in pyproject.toml"
    assert packaged - on_disk == set(), "these are packaged but no longer exist"
