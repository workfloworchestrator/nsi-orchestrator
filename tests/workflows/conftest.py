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

"""Database fixtures for the workflow integration tests.

A real ``nsi-test`` Postgres is created once per session and migrated with the app's own
``db upgrade heads`` (so the core schema + pgvector + all product migrations run exactly as in
production). Each test runs inside a transaction that is rolled back afterward, so tests are
isolated and the database stays at its migrated baseline. These fixtures live under ``tests/workflows``
so the pure-unit tests elsewhere keep running without a database.
"""

# orchestrator-core's `db` is a runtime proxy whose engine/session internals mypy can't see; this
# plumbing mirrors orchestrator-core's own test fixtures.
# mypy: disable-error-code="attr-defined, call-overload"

from __future__ import annotations

import os
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import cast

import pytest
from orchestrator.core.db import db
from orchestrator.core.db.database import ENGINE_ARGUMENTS, SESSION_ARGUMENTS, BaseModel, Database, SearchQuery
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm.scoping import scoped_session
from sqlalchemy.orm.session import close_all_sessions, sessionmaker

import products  # noqa: F401  registers SUBSCRIPTION_MODEL_REGISTRY
import workflows  # noqa: F401  registers the LazyWorkflowInstance entries
from services import dds_proxy

_REPO = Path(__file__).resolve().parents[2]

# A small, internally consistent DDS dataset: topology t1 -> switching service ss1 -> two STPs,
# paired into one SDP. Keys are the camelCase aliases the real proxy returns.
DDS_DATA: dict[str, list[dict[str, object]]] = {
    "/topologies": [{"id": "urn:t1", "name": "Topo 1"}],
    "/switching-services": [{"id": "urn:ss1", "topologyId": "urn:t1"}],
    "/service-termination-points": [
        {
            "id": "urn:stp1",
            "name": "STP 1",
            "capacity": 1_000_000_000,
            "labelGroup": "1000-1999",
            "switchingServiceId": "urn:ss1",
        },
        {
            "id": "urn:stp2",
            "name": "STP 2",
            "capacity": 2_000_000_000,
            "labelGroup": "2000-2999",
            "switchingServiceId": "urn:ss1",
        },
    ],
    "/service-demarcation-points": [{"stpAId": "urn:stp1", "stpZId": "urn:stp2"}],
}

# A three-domain chain A <-> B <-> C with a customer edge at each end, for tests that need real
# NSI URNs (the ids above are deliberately short and have no network part to derive an ERO from).
_A, _B, _C = (f"urn:ogf:network:{name}.example.net:2025:topology" for name in ("a", "b", "c"))
PATH_STPS = {
    "source": f"{_A}:edge",
    "a_to_b": f"{_A}:to-b",
    "b_to_a": f"{_B}:to-a",
    "b_to_c": f"{_B}:to-c",
    "c_to_b": f"{_C}:to-b",
    "destination": f"{_C}:edge",
}
PATH_DDS_DATA: dict[str, list[dict[str, object]]] = {
    "/topologies": DDS_DATA["/topologies"],
    "/switching-services": DDS_DATA["/switching-services"],
    "/service-termination-points": [
        {
            "id": stp_id,
            "name": name,
            "capacity": 1_000_000_000,
            "labelGroup": "1000-1999",
            "switchingServiceId": "urn:ss1",
        }
        for name, stp_id in PATH_STPS.items()
    ],
    "/service-demarcation-points": [
        {"stpAId": PATH_STPS["a_to_b"], "stpZId": PATH_STPS["b_to_a"]},
        {"stpAId": PATH_STPS["b_to_c"], "stpZId": PATH_STPS["c_to_b"]},
    ],
}


def _recreate_database(db_uri: str) -> None:
    url = make_url(db_uri)
    db_name = url.database
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with closing(admin_engine.connect()) as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()


def _run_migrations(db_uri: str) -> None:
    # Use the app's own migration command so the core + product version locations compose exactly
    # as in production (and pgvector / the core schema are created).
    result = subprocess.run(
        [sys.executable, "main.py", "db", "upgrade", "heads"],
        cwd=_REPO,
        env={**os.environ, "DATABASE_URI": db_uri},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"db upgrade heads failed:\n{result.stdout}\n{result.stderr}")


@pytest.fixture(scope="session")
def database() -> object:
    db_uri = os.environ["DATABASE_URI"]
    _recreate_database(db_uri)
    _run_migrations(db_uri)

    db.update(Database(db_uri))
    db.wrapped_database.engine = create_engine(db_uri, **ENGINE_ARGUMENTS)
    try:
        yield
    finally:
        db.wrapped_database.engine.dispose()
        close_all_sessions()


@pytest.fixture(autouse=True)
def db_session(database: object) -> object:
    """Run each test in a transaction that is rolled back afterward (orchestrator-core pattern)."""
    with closing(db.wrapped_database.engine.connect()) as connection:
        db.wrapped_database.session_factory = sessionmaker(**SESSION_ARGUMENTS, bind=connection)
        db.wrapped_database.scoped_session = scoped_session(db.session_factory, db._scopefunc)
        BaseModel.set_query(cast("SearchQuery", db.wrapped_database.scoped_session.query_property()))

        transaction = connection.begin()
        try:
            yield
        finally:
            close_all_sessions()
            if not transaction._deactivated_from_connection:
                transaction.rollback()


@pytest.fixture
def dds(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict[str, object]]]:
    """Mock the single dds-proxy ``_fetch`` so every ``fetch_*`` (in any module) returns DDS_DATA."""
    monkeypatch.setattr(dds_proxy, "_fetch", lambda path: DDS_DATA[path])
    return DDS_DATA


def _create(workflow_key: str, *form_pages: dict[str, object]) -> str:
    """Run a create workflow (product page + the given form pages) and return the new subscription id."""
    from tests.workflows import assert_complete, extract_state, product_id, run_workflow

    product_type = {
        "create_topology": "Topology",
        "create_switchingservice": "SwitchingService",
        "create_stp": "ServiceTerminationPoint",
        "create_sdp": "ServiceDemarcationPoint",
    }[workflow_key]
    result, _, _ = run_workflow(workflow_key, [{"product": product_id(product_type)}, *form_pages, {}])
    assert_complete(result)
    return str(extract_state(result)["subscription_id"])


# Chained seed fixtures: topology -> switching service -> two STPs -> one SDP. A product's workflow
# tests request the level below it; the create tests re-exercise the create workflow themselves.
@pytest.fixture
def topology_subscription(dds: object) -> str:
    return _create("create_topology", {"topology": "urn:t1"})


@pytest.fixture
def switchingservice_subscription(topology_subscription: str) -> str:
    return _create("create_switchingservice", {"switching_service_id": "urn:ss1", "switching_service_name": "SS 1"})


@pytest.fixture
def stp_subscriptions(switchingservice_subscription: str) -> dict[str, str]:
    return {stp_id: _create("create_stp", {"stp_id": stp_id}) for stp_id in ("urn:stp1", "urn:stp2")}


@pytest.fixture
def sdp_subscription(stp_subscriptions: dict[str, str]) -> str:
    return _create("create_sdp", {"service_demarcation_point": "urn:stp1|urn:stp2", "sdp_name": "SDP 1"})


@pytest.fixture
def path_dds(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict[str, object]]]:
    """Like ``dds``, but serving the three-domain chain with real NSI URNs."""
    monkeypatch.setattr(dds_proxy, "_fetch", lambda path: PATH_DDS_DATA[path])
    return PATH_DDS_DATA


@pytest.fixture
def path_subscriptions(path_dds: object) -> dict[str, str]:
    """Subscriptions for the A <-> B <-> C chain; returns the two SDP subscription ids by name."""
    _create("create_topology", {"topology": "urn:t1"})
    _create("create_switchingservice", {"switching_service_id": "urn:ss1", "switching_service_name": "SS 1"})
    for stp_id in PATH_STPS.values():
        _create("create_stp", {"stp_id": stp_id})
    return {
        name: _create(
            "create_sdp",
            {"service_demarcation_point": f"{PATH_STPS[a]}|{PATH_STPS[z]}", "sdp_name": name},
        )
        for name, (a, z) in {"A <-> B": ("a_to_b", "b_to_a"), "B <-> C": ("b_to_c", "c_to_b")}.items()
    }
