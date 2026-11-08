"""Steps for `pubdoc build`: the shared ones are conftest's and pubkit's plugin's."""

from __future__ import annotations

from pytest_bdd import parsers, scenarios, then

from conftest import calls

scenarios("build.feature")


@then(parsers.parse('npx was run in "{where}" with "{args}"'))
def npx_ran(tmp_path, repo, where, args):
    assert ("npx", str(repo / where), args) in calls(tmp_path), calls(tmp_path)


@then(parsers.parse('typst compiled "{path}"'))
def typst_compiled(tmp_path, repo, path):
    assert any(tool == "typst" and argv == f"compile {repo / path}"
               for tool, _, argv in calls(tmp_path)), calls(tmp_path)
