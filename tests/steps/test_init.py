"""Steps for `pubdoc init`."""

from __future__ import annotations

import os

from pytest_bdd import parsers, scenarios, then

scenarios("init.feature")


@then(parsers.parse('"{path}" is executable'))
def executable(repo, path):
    assert os.access(repo / path, os.X_OK)


@then(parsers.parse('"{path}" holds "{line}" once'))
def holds_once(repo, path, line):
    assert (repo / path).read_text().splitlines().count(line) == 1
