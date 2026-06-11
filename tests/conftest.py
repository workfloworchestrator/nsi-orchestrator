"""Shared test configuration."""

from __future__ import annotations

import os

# Set required environment variables before any application module is imported.
os.environ.setdefault("DATABASE_URI", "postgresql://nsi:nsi@localhost/nsi-test")
