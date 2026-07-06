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

"""Tests for the uvicorn access-log filters (log_filters.py)."""

from __future__ import annotations

import logging

import pytest

from log_filters import HealthCheckAccessFilter


def _access_record(path: str) -> logging.LogRecord:
    """A uvicorn.access record: args = (client, method, path_with_query, http_version, status)."""
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("10.0.0.1:1234", "GET", path, "1.1", 200),
        exc_info=None,
    )


@pytest.mark.parametrize(
    ("path", "kept"),
    [
        pytest.param("/api/health/", False, id="health-trailing-slash-dropped"),
        pytest.param("/api/health", False, id="health-no-slash-dropped"),
        pytest.param("/api/health/?ready=1", False, id="health-with-query-dropped"),
        pytest.param("/api/subscriptions", True, id="other-path-kept"),
        pytest.param("/api/health-check", True, id="lookalike-path-kept"),
    ],
)
def test_health_check_filter_by_path(path: str, kept: bool) -> None:
    assert HealthCheckAccessFilter().filter(_access_record(path)) is kept


def test_health_check_filter_keeps_non_access_records() -> None:
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="Application startup complete.",
        args=None,
        exc_info=None,
    )
    assert HealthCheckAccessFilter().filter(record) is True
