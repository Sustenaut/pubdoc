"""Steps for `pubdoc check` and doc.yml narrowing: all of them conftest's and pubtest's."""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("check.feature")
scenarios("narrowing.feature")
