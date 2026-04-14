import typer
from nwastdlib.logging import initialise_logging
from orchestrator import app_settings
from orchestrator.cli.main import app as core_cli
from orchestrator.db import init_database
from orchestrator.log_config import LOGGER_OVERRIDES

def init_cli_app() -> typer.Typer:
    initialise_logging(LOGGER_OVERRIDES)
    init_database(app_settings)
    return core_cli()

if __name__ == "__main__":
    init_cli_app()
