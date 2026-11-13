"""Steps for `pubdoc init`."""

from __future__ import annotations

import os
import re
import shutil
import subprocess

import pytest

from pytest_bdd import given, parsers, scenarios, then, when

from conftest import calls, pubdoc

scenarios("init.feature")


@then(parsers.parse('"{path}" is executable'))
def executable(repo, path):
    assert os.access(repo / path, os.X_OK)


@then(parsers.parse('"{path}" holds "{line}" once'))
def holds_once(repo, path, line):
    assert (repo / path).read_text().splitlines().count(line) == 1


# pubkit's nightly moves a release wheel pin of this form (pubkit's
# nightly.WHEEL_PIN), in a file whose name holds "requirements" and ends .txt.
WHEEL_PIN = re.compile(r"(?P<lead>[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[^\]]*\])?\s*@\s*)https://github\.com/"
                       r"(?P<owner>[A-Za-z0-9][A-Za-z0-9-]*)/(?P<repo>[A-Za-z0-9_.-]+)/releases/download/"
                       r"v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)/(?P<file>[A-Za-z0-9_.+-]+\.whl)")
PIN = "requirements-pubdoc.txt"


@then(parsers.parse('"{path}" is one release wheel pin of pubdoc'))
def wheel_pin(repo, path):
    assert "requirements" in path and path.endswith(".txt")
    lines = (repo / path).read_text().splitlines()
    assert len(lines) == 1, lines
    m = WHEEL_PIN.fullmatch(lines[0])
    assert m, lines[0]
    assert (m["lead"], m["owner"], m["repo"]) == ("pubdoc @ ", "Sustenaut", "pubdoc"), m.groupdict()
    assert m["file"].startswith("pubdoc-")


@given("pubdoc init has run")
def init_ran(repo, run, env):
    assert run(pubdoc(), "init", cwd=repo, env=env).code == 0
    (repo / "cv" / "cv").mkdir(parents=True)


@given(parsers.parse('the pin reads "{text}"'))
def pin_reads(repo, text):
    (repo / PIN).write_text(text + "\n")


@given("the pin is gone")
def pin_gone(repo):
    (repo / PIN).unlink()


@when(parsers.parse('I run the launcher as "{launcher}" in "{where}" with "{args}"'),
      target_fixture="result")
def run_launcher(repo, run, env, launcher, where, args):
    return run(launcher, *args.split(), cwd=repo / where, env=env)


@then(parsers.parse('uvx was run with "{args}"'))
def uvx_ran(tmp_path, args):
    assert any(tool == "uvx" and argv == args for tool, _, argv in calls(tmp_path)), calls(tmp_path)


@then(parsers.parse('shellcheck passes on "{path}"'))
def shellcheck(repo, path):
    found = shutil.which("shellcheck")
    if not found:
        # CI's runner has it; a laptop may not.
        assert not os.environ.get("CI"), "shellcheck is not installed"
        pytest.skip("shellcheck is not installed")
    done = subprocess.run([found, "--severity=style", str(repo / path)], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout
