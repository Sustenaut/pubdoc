"""pubdoc's suite, on pubtest's steps. What it adds is its own domain: the
example project, an edit to one of its files, an approved PDF named for
today, and a stand-in that notes the directory it ran in.

Every scenario runs in pubtest's scratch directory, with pubtest's stand-ins
for npx, typst, uvx and review-builder-preview first on PATH where it runs
them, so no real Curvenote, typst or review-builder is ever reached. pubdoc
is the program under test from PUBDOC_BIN_DIR: the one beside the Python
running this suite (`make venv`'s), unless PUBDOC_BIN_DIR names another.
"""

from __future__ import annotations

import datetime
import os
import shlex
import shutil
import sys
from pathlib import Path

from pubtest.steps.programs import run_command
from pubtest.steps.standins import standins
from pytest_bdd import given, parsers, then, when

os.environ.setdefault("PUBDOC_BIN_DIR", str(Path(sys.executable).parent))

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def scratch(pubtest_ctx) -> Path:
    return pubtest_ctx.directory or Path.cwd()


@given("the example project")
def example_project(pubtest_ctx):
    """examples/: job-applications (a letter and a CV starting from a shared
    base CV, two variants; docs acme and globex) and the publets its CV
    links to, without anything built or approved."""
    root = scratch(pubtest_ctx)
    for item in EXAMPLES.iterdir():
        if item.is_dir():
            shutil.copytree(item, root / item.name, ignore=shutil.ignore_patterns("build", "versions"))
        else:
            shutil.copy(item, root / item.name)


@given(parsers.parse('in "{path}" "{old}" becomes "{new}"'))
def replaced(pubtest_ctx, path, old, new):
    """One edit to a file, `\\n` a newline: pubtest writes whole files only."""
    target = scratch(pubtest_ctx) / path
    text = target.read_text(encoding="utf-8")
    old, new = old.replace("\\n", "\n"), new.replace("\\n", "\n")
    assert old in text, f"{old!r} is not in {path}"
    target.write_text(text.replace(old, new), encoding="utf-8")


@given(parsers.parse('a stand-in "{name}" that notes where it runs'))
def standin_noting(pubtest_ctx, tmp_path, name):
    """pubtest's stand-in, whose log of each run also holds its working
    directory. pubtest has no step for where a program ran."""
    found = standins(pubtest_ctx, tmp_path)
    found.add(name)
    script = found.bin / name
    text = script.read_text(encoding="utf-8")
    noted = text.replace('"input": read}', '"input": read, "cwd": __import__("os").getcwd()}')
    assert noted != text, "pubtest's stand-in no longer logs its runs as this step expects"
    script.write_text(noted, encoding="utf-8")
    os.environ["PATH"] = found.path()


@when(parsers.parse('from "{where}" I run "{command}"'), target_fixture="result")
def run_from(pubtest_ctx, where, command):
    """pubtest's `I run`, in a directory of the scratch directory."""
    pubtest_ctx.acting()
    home = pubtest_ctx.directory
    pubtest_ctx.directory = scratch(pubtest_ctx) / where
    try:
        return run_command(pubtest_ctx, command, None)
    finally:
        pubtest_ctx.directory = home


@then(parsers.re(r'"(?P<name>[^"]+)" ran in "(?P<where>[^"]+)" with (?:"(?P<args>[^"]+)"|no arguments)'))
def ran_in(pubtest_ctx, name, where, args):
    want = (os.path.realpath(scratch(pubtest_ctx) / where), shlex.split(args or ""))
    runs = [(os.path.realpath(e.get("cwd", "")), e["args"]) for e in pubtest_ctx.standins.entries(name)]
    assert want in runs, f"{name} ran {runs}"


def today_pdf(prefix: str) -> str:
    return f"{prefix}_{datetime.date.today().isoformat()}.pdf"
