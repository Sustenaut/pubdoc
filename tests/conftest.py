"""pubdoc's suite. The steps it does not define here (`it succeeds`, `it
prints ...`) are pubrules's plugin's.

Every scenario runs in a scratch repository, with stand-ins for npx and
typst first on PATH and HOME pointed at the scratch directory, so no real
Curvenote, typst or ~/git/typst build is ever reached.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, then, when

# Each stand-in appends its working directory and arguments to calls.log.
STAND_IN = """#!/bin/sh
echo "$(basename "$0")|$PWD|$*" >> "{log}"
{body}
"""
NPX = 'if [ -n "$PUBDOC_TEST_FAIL" ]; then exit 3; fi\n'
# typst compile [--creation-timestamp N] SOURCE OUTPUT: the output names
# the timestamp, so a scenario can see which one a build asked for.
TYPST = ('last=""; for a; do last="$a"; done\n'
         'for a; do if [ -n "$PUBDOC_TEST_TYPST_FAIL" ] && [ "$a" = "$PUBDOC_TEST_TYPST_FAIL" ]; then exit 4; fi; done\n'
         'mkdir -p "$(dirname "$last")" && echo "%PDF-1.7 typst $*" > "$last"\n')


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    return root


@pytest.fixture
def fakes(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    for name, body in (("npx", NPX), ("typst", TYPST), ("review-builder-preview", ""), ("uvx", "")):
        path = bin_dir / name
        path.write_text(STAND_IN.format(log=log, body=body))
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return bin_dir


@pytest.fixture
def env(tmp_path, fakes):
    node = shutil.which("node")
    path = [str(fakes)] + ([str(Path(node).parent)] if node else []) + ["/usr/bin", "/bin"]
    return {"PATH": os.pathsep.join(path), "HOME": str(tmp_path),
            "PUBDOC_TEST_LOG": str(tmp_path / "calls.log")}


def pubdoc():
    """The `pubdoc` installed beside the Python running this suite."""
    found = shutil.which("pubdoc", path=str(Path(sys.executable).parent))
    assert found, "pubdoc is not installed in this environment; run `make venv`"
    return found


def calls(tmp_path) -> list[tuple[str, str, str]]:
    log = tmp_path / "calls.log"
    lines = log.read_text().splitlines() if log.exists() else []
    return [tuple(line.split("|", 2)) for line in lines]


EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@given("the example project")
def example_project(repo):
    """examples/: job-applications (a letter and a CV starting from a shared
    base CV, two variants; docs acme and globex) and the publets its CV links to."""
    for item in EXAMPLES.iterdir():
        if item.is_dir():
            shutil.copytree(item, repo / item.name, ignore=shutil.ignore_patterns("build", "versions"))
        else:
            shutil.copy(item, repo / item.name)


@given("the repository is a git work tree")
def git_repo(repo):
    subprocess.run(["git", "init", "-q", str(repo)], check=True)


@given(parsers.parse('the file "{path}" reads:'))
def file_reads_block(repo, path, docstring):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(docstring + "\n")


@given(parsers.parse('in "{path}" "{old}" becomes "{new}"'))
def replaced(repo, path, old, new):
    target = repo / path
    text = target.read_text()
    old, new = old.replace("\\n", "\n"), new.replace("\\n", "\n")
    assert old in text, f"{old!r} is not in {path}"
    target.write_text(text.replace(old, new))


@given(parsers.parse('the file "{path}" is gone'))
def gone(repo, path):
    (repo / path).unlink()


@given(parsers.parse('the file "{path}" reads "{text}"'))
def file_reads(repo, path, text):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text.replace("\\n", "\n") + "\n")


@given("no typst is installed")
def no_typst(fakes):
    (fakes / "typst").unlink()


@given("Curvenote fails")
def curvenote_fails(env):
    env["PUBDOC_TEST_FAIL"] = "1"


@when(parsers.re(r'I run pubdoc (?P<args>(?:"[^"]*" ?)+?)(?: in "(?P<where>[^"]*)")?$'),
      target_fixture="result")
def run_pubdoc(repo, run, env, args, where):
    argv = args.strip().strip('"').split('" "')
    return run(pubdoc(), *argv, cwd=repo / (where or ""), env=env)


@then(parsers.parse('"{path}" exists'))
def exists(repo, path):
    assert (repo / path).exists(), f"{path} does not exist"


@then(parsers.parse('"{path}" does not exist'))
def does_not_exist(repo, path):
    assert not (repo / path).exists(), f"{path} exists"


@then(parsers.parse('"{path}" contains "{text}"'))
def contains(repo, path, text):
    assert text in (repo / path).read_text()


@then(parsers.parse('"{path}" does not contain "{text}"'))
def lacks(repo, path, text):
    assert text not in (repo / path).read_text()
