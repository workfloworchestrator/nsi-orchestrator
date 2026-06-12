import typer
from nwastdlib.logging import initialise_logging
from orchestrator.core import app_settings
from orchestrator.core.cli.main import app as core_cli
from orchestrator.core.db import init_database
from orchestrator.core.log_config import LOGGER_OVERRIDES


def init_cli_app() -> typer.Typer:
    initialise_logging(LOGGER_OVERRIDES)
    init_database(app_settings)
    return core_cli()  # type: ignore[no-any-return]


if __name__ == "__main__":
    init_cli_app()
