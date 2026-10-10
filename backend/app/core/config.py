from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "FSP-Talent Platform"
    PROJECT_VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Security & Auth
    SECRET_KEY: str = "fsp-talent-super-secret-key-change-in-production-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    AUTH_PROVIDER: str = "internal"  # "internal" or "keycloak"

    # Keycloak settings (if keycloak is used)
    KEYCLOAK_URL: str = "http://localhost:8080"
    KEYCLOAK_REALM: str = "fsp-realm"
    KEYCLOAK_CLIENT_ID: str = "fsp-backend"

    # Database
    DATABASE_URL: str = "sqlite:///./fsp_talent.db"

    # FSP Mock Registry
    FSP_REGISTRY_URL: str = "http://localhost:8001"

    # Public address of the platform: the QR code in the PDF profile links to its verification endpoint
    PUBLIC_BASE_URL: str = "http://193.32.188.135"

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:80"
    ]

    # CAT & Assessment settings
    CAT_MIN_ITEMS: int = 12
    CAT_MAX_ITEMS: int = 25
    CAT_TARGET_SE: float = 0.30
    MAX_FAMILY_EXPOSURE_RATE: float = 0.25

    # LLM & AI Engine (152-FZ Compliant, GigaChat / YandexGPT / Offline)
    LLM_PROVIDER: str = "gigachat"  # "gigachat", "yandex", "offline"
    GIGACHAT_CREDENTIALS: str | None = "MDFhMTIwOTItY2IwMC03MGM4LWIwODQtYTA3YzZkYTIzNWVkOjhkMGE5NzMyLTM1MDYtNGU1NC1hZDgxLTgyZTJlMzU1YWQ2Yg=="
    GIGACHAT_SCOPE: str = "GIGACHAT_API_PERS"
    GIGACHAT_MODEL: str = "GigaChat"
    GIGACHAT_VERIFY_SSL: bool = False

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
