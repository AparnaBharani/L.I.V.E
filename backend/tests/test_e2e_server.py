"""Safety tests for the script that recreates the browser-test database."""

import pytest
from sqlalchemy.engine import make_url

from scripts.e2e_server import E2E_DATABASE, check_disposable, e2e_database_url


class TestCheckDisposable:
    @pytest.mark.parametrize("name", ["live_db", "live_db_test", "postgres", "e2e", ""])
    def test_refuses_anything_not_ending_in_e2e(self, name):
        with pytest.raises(SystemExit):
            check_disposable(f"postgresql+psycopg://u:p@localhost/{name}")

    def test_accepts_disposable_database(self):
        assert check_disposable("postgresql+psycopg://u:p@localhost/live_db_e2e") == "live_db_e2e"


class TestE2EDatabaseUrl:
    def test_replaces_only_the_database_name(self):
        url = make_url(e2e_database_url("postgresql+psycopg://u:p%40ss@db:5433/live_db_test"))
        assert url.database == E2E_DATABASE
        assert (url.username, url.password, url.host, url.port) == ("u", "p@ss", "db", 5433)

    def test_requires_test_database_url(self):
        with pytest.raises(SystemExit):
            e2e_database_url(None)
