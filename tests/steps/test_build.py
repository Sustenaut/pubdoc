"""Steps for `pubdoc build`: the shared ones are conftest's and pubrules's plugin's."""

from __future__ import annotations

from pytest_bdd import given, parsers, scenarios, then

from conftest import calls

scenarios("build.feature")
scenarios("templates.feature")


@then(parsers.parse('npx was run in "{where}" with "{args}"'))
def npx_ran(tmp_path, repo, where, args):
    assert ("npx", str(repo / where), args) in calls(tmp_path), calls(tmp_path)


@then(parsers.parse('typst compiled "{source}" to "{output}"'))
def typst_compiled(tmp_path, repo, source, output):
    assert any(tool == "typst" and argv == f"compile {repo / source} {repo / output}"
               for tool, _, argv in calls(tmp_path)), calls(tmp_path)
    assert (repo / output).exists()


@then("typst compiled only once")
def typst_once(tmp_path):
    assert [tool for tool, _, _ in calls(tmp_path)].count("typst") == 1, calls(tmp_path)


@given(parsers.parse('typst fails on "{path}"'))
def typst_fails(repo, env, path):
    env["PUBDOC_TEST_TYPST_FAIL"] = str(repo / path)
