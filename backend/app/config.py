from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    # Only read by the test suite (tests/conftest.py). Must name a separate
    # "*_test" database; the tests drop and recreate it on every run.
    TEST_DATABASE_URL: str | None = None

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
