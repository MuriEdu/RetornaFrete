from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Retorna Frete API"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "sqlite:///./retorna_frete.db"
    jwt_secret_key: str = "change-me"
    jwt_refresh_secret_key: str = "change-me-too"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    cors_origins: str = Field(default="*")
    mapbox_token: str = ""
    mapbox_directions_url: str = "https://api.mapbox.com/directions/v5/mapbox/driving"
    mapbox_geocoding_url: str = "https://api.mapbox.com/search/geocode/v6/reverse"
    osrm_directions_url: str = "https://router.project-osrm.org/route/v1/driving"
    nominatim_reverse_url: str = "https://nominatim.openstreetmap.org/reverse"
    nominatim_user_agent: str = "retorna-frete-fastapi/1.0"

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
