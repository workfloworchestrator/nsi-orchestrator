from orchestrator.settings import AppSettings


class OrchestratorSettings(AppSettings):
    HOST: str = "127.0.0.1"
    PORT: int = 8080


app_settings = OrchestratorSettings()
