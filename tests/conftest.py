"""pubdoc's suite. The steps it does not define here (`it succeeds`, `it
prints ...`) are pubkit's plugin's.

Every scenario runs in a scratch repository, with stand-ins for npx and
typst first on PATH and HOME pointed at the scratch directory, so no real
Curvenote, typst or ~/git/typst build is ever reached.
"""

from __future__ import annotations

import datetime
import os
import shutil
import stat
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
TYPST = 'touch "$(dirname "$2")/main.pdf"\n'


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
    for name, body in (("npx", NPX), ("typst", TYPST)):
        path = bin_dir / name
        path.write_text(STAND_IN.format(log=log, body=body))
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return bin_dir


@pytest.fixture
def env(tmp_path, fakes):
    node = shutil.which("node")
    path = [str(fakes)] + ([str(Path(node).parent)] if node else []) + ["/usr/bin", "/bin"]
    return {"PATH": os.pathsep.join(path), "HOME": str(tmp_path)}


def pubdoc():
    """The `pubdoc` installed beside the Python running this suite."""
    found = shutil.which("pubdoc", path=str(Path(sys.executable).parent))
    assert found, "pubdoc is not installed in this environment; run `make venv`"
    return found


def calls(tmp_path) -> list[tuple[str, str, str]]:
    log = tmp_path / "calls.log"
    lines = log.read_text().splitlines() if log.exists() else []
    return [tuple(line.split("|", 2)) for line in lines]


@given(parsers.parse('a document "{name}" exporting "{output}"'))
def document(repo, name, output):
    doc = repo / name
    variant = Path(output).parts[0]
    (doc / variant).mkdir(parents=True, exist_ok=True)
    (doc / "myst.yml").write_text(
        "version: 1\nproject:\n  exports:\n    - format: typst\n"
        f"      template: ../.pubdoc/templates/cv-sidebar\n      output: {output}\n")
    (doc / "index.md").write_text("---\ntitle: Jane Doe\n---\n")
    (doc / variant / "review-builder.yaml").write_text(
        f'title: "{name}"\nbuild_cmd: ["../../pubdoc", "build", ".."]\npdf_path: "main.pdf"\n')


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


def today_pdf(prefix: str) -> str:
    return f"{prefix}_{datetime.date.today().isoformat()}.pdf"
