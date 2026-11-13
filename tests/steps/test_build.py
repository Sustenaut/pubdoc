"""Steps for `pubdoc build`: the shared ones are conftest's and pubkit's plugin's."""

from __future__ import annotations

import shutil

from pytest_bdd import given, parsers, scenarios, then

from conftest import calls

scenarios("build.feature")


@then(parsers.parse('npx was run in "{where}" with "{args}"'))
def npx_ran(tmp_path, repo, where, args):
    assert ("npx", str(repo / where), args) in calls(tmp_path), calls(tmp_path)


@then(parsers.parse('typst compiled "{path}"'))
def typst_compiled(tmp_path, repo, path):
    assert any(tool == "typst" and argv == f"compile {repo / path}"
               for tool, _, argv in calls(tmp_path)), calls(tmp_path)


@given(parsers.parse('typst fails on "{path}"'))
def typst_fails(repo, env, path):
    env["PUBDOC_TEST_TYPST_FAIL"] = str(repo / path)


@given("no documents")
def no_documents(repo):
    for myst in repo.glob("*/myst.yml"):
        shutil.rmtree(myst.parent)
