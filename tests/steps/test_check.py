"""Steps for `pubdoc check` and doc.yml narrowing: all shared, in conftest and pubrules's plugin."""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("check.feature")
scenarios("narrowing.feature")
