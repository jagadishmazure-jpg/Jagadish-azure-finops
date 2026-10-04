from __future__ import annotations

import pytest

from finops.datasets import load_inventory
from finops.pricing import default_book


@pytest.fixture(scope="session")
def book():
    return default_book()


@pytest.fixture(scope="session")
def inventory():
    return load_inventory()


def find(result, name):
    return next(f for f in result.findings if f.resource_name == name)
