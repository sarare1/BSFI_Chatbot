"""
Shared test settings. pytest loads this file automatically before the tests.
"""

import pytest


@pytest.fixture(autouse=True)
def use_built_in_demo_data(monkeypatch):
    # Remove DATABASE_URL during every test, so tests always use the built-in
    # demo data. They then run offline and give the same result every time.
    monkeypatch.delenv("DATABASE_URL", raising=False)
