"""Deployment-facing configuration."""

import pytest

from app.config import Settings


def settings(**values) -> Settings:
    return Settings(_env_file=None, DATABASE_URL="postgresql+psycopg://u:p@h/db", **values)


class TestDatabaseUrl:
    @pytest.mark.parametrize("url", ["postgres://u:p@h:5432/db", "postgresql://u:p@h:5432/db"])
    def test_provider_urls_get_the_psycopg_driver(self, url):
        assert Settings(_env_file=None, DATABASE_URL=url).DATABASE_URL == "postgresql+psycopg://u:p@h:5432/db"

    def test_a_correct_url_is_unchanged(self):
        assert settings().DATABASE_URL == "postgresql+psycopg://u:p@h/db"


class TestCorsOrigins:
    def test_defaults_to_local_development(self):
        assert settings().cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]

    def test_parses_a_comma_separated_list(self):
        assert settings(CORS_ORIGINS=" https://a.example , https://b.example,").cors_origins == [
            "https://a.example", "https://b.example",
        ]


class TestHealth:
    def test_reports_ok_when_the_database_answers(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
