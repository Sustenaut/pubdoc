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
    assert any(tool == "typst" and argv.startswith("compile ") and argv.endswith(f" {repo / source} {repo / output}")
               for tool, _, argv in calls(tmp_path)), calls(tmp_path)
    assert (repo / output).exists()


@then("typst compiled only once")
def typst_once(tmp_path):
    assert [tool for tool, _, _ in calls(tmp_path)].count("typst") == 1, calls(tmp_path)


@given(parsers.parse('typst fails on "{path}"'))
def typst_fails(repo, env, path):
    env["PUBDOC_TEST_TYPST_FAIL"] = str(repo / path)


@then("typst saw pubdoc's fonts alone")
def fonts_alone(tmp_path):
    import pubdoc.cli
    fonts = pubdoc.cli.fonts()
    runs = [argv for tool, _, argv in calls(tmp_path) if tool == "typst"]
    assert runs and all(f"--ignore-system-fonts --font-path {fonts} " in argv for argv in runs), runs
    assert (fonts / "DejaVuSans.ttf").is_file() and (fonts / "LICENCE-Ubuntu.txt").is_file()


@then(parsers.parse('typst was asked for the creation time {stamp:d}'))
def typst_stamp(tmp_path, stamp):
    assert any(tool == "typst" and f"--creation-timestamp {stamp} " in argv
               for tool, _, argv in calls(tmp_path)), calls(tmp_path)
