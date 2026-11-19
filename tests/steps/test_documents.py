"""Steps for listing projects and previewing a render."""

from __future__ import annotations

from pytest_bdd import parsers, scenarios, then

from conftest import calls

scenarios("documents.feature")


@then(parsers.re(r'review-builder-preview was run in "(?P<where>[^"]*)" with "(?P<args>[^"]*)"'))
def preview_ran(tmp_path, repo, where, args):
    assert ("review-builder-preview", str(repo / where), args) in calls(tmp_path), calls(tmp_path)

