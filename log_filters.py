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

"""Logging filters for the orchestrator API."""

import logging

# uvicorn logs each request as '%s - "%s %s HTTP/%s" %d' with args
# (client, method, path_with_query, http_version, status), so args[2] is the request path.
_HEALTH_PATH = "/api/health"


class HealthCheckAccessFilter(logging.Filter):
    """Drop the uvicorn access line for the k8s health probe (any status), keep every other request.

    The liveness/readiness probes hit the health endpoint every few seconds and would otherwise bury
    real requests in the access log. A failing health endpoint still surfaces via pod readiness.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not (isinstance(args, tuple) and len(args) >= 3):
            return True
        return str(args[2]).split("?", 1)[0].rstrip("/") != _HEALTH_PATH
