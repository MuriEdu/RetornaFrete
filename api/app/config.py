from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Retorna Frete API", validation_alias="APP_NAME")
    api_host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    api_port: int = Field(default=8000, validation_alias="API_PORT")
    database_url: str = Field(default="sqlite:///./retorna_frete.db", validation_alias="DATABASE_URL")
    jwt_secret_key: str = Field(default="change-me", validation_alias="JWT_SECRET_KEY")
    jwt_refresh_secret_key: str = Field(default="change-me-too", validation_alias="JWT_REFRESH_SECRET_KEY")
    access_token_expire_minutes: int = Field(default=60, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=30, validation_alias="REFRESH_TOKEN_EXPIRE_DAYS")
    cors_origins: str = Field(default="*", validation_alias="CORS_ORIGINS")
    mapbox_token: str = Field(default="", validation_alias="MAPBOX_TOKEN")
    mapbox_directions_url: str = Field(
        default="https://api.mapbox.com/directions/v5/mapbox/driving",
        validation_alias="MAPBOX_DIRECTIONS_URL",
    )
    mapbox_geocoding_url: str = Field(
        default="https://api.mapbox.com/search/geocode/v6/reverse",
        validation_alias="MAPBOX_GEOCODING_URL",
    )
    osrm_directions_url: str = Field(
        default="https://router.project-osrm.org/route/v1/driving",
        validation_alias="OSRM_DIRECTIONS_URL",
    )
    nominatim_reverse_url: str = Field(
        default="https://nominatim.openstreetmap.org/reverse",
        validation_alias="NOMINATIM_REVERSE_URL",
    )
    nominatim_search_url: str = Field(
        default="https://nominatim.openstreetmap.org/search",
        validation_alias="NOMINATIM_SEARCH_URL",
    )
    nominatim_user_agent: str = Field(
        default="retorna-frete-fastapi/1.0",
        validation_alias="NOMINATIM_USER_AGENT",
    )
    mercado_pago_access_token: str = Field(default="APP_USR-4428337865113108-021510-245fe2fc42f998af9b3092e1d781b724-3202143207", validation_alias="MERCADO_PAGO_ACCESS_TOKEN")
    mercado_pago_base_url: str = Field(
        default="https://api.mercadopago.com",
        validation_alias="MERCADO_PAGO_BASE_URL",
    )
    mercado_pago_notification_url: str = Field(default="", validation_alias="MERCADO_PAGO_NOTIFICATION_URL")
    mercado_pago_success_url: str = Field(default="", validation_alias="MERCADO_PAGO_SUCCESS_URL")
    mercado_pago_pending_url: str = Field(default="", validation_alias="MERCADO_PAGO_PENDING_URL")
    mercado_pago_failure_url: str = Field(default="", validation_alias="MERCADO_PAGO_FAILURE_URL")

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
