"""Steps for `pubdoc init`."""

from __future__ import annotations

import os
import re
import shutil

import pytest
from pytest_bdd import given, parsers, scenarios, then

from conftest import scratch

scenarios("init.feature")

# pubrules's nightly moves a release wheel pin of this form (pubrules's
# nightly.WHEEL_PIN), in a file whose name holds "requirements" and ends .txt.
WHEEL_PIN = re.compile(r"(?P<lead>[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[^\]]*\])?\s*@\s*)https://github\.com/"
                       r"(?P<owner>[A-Za-z0-9][A-Za-z0-9-]*)/(?P<repo>[A-Za-z0-9_.-]+)/releases/download/"
                       r"v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)/(?P<file>[A-Za-z0-9_.+-]+\.whl)")


@then(parsers.parse('"{path}" is one release wheel pin of pubdoc'))
def wheel_pin(pubtest_ctx, path):
    assert "requirements" in path and path.endswith(".txt")
    lines = (scratch(pubtest_ctx) / path).read_text().splitlines()
    assert len(lines) == 1, lines
    m = WHEEL_PIN.fullmatch(lines[0])
    assert m, lines[0]
    assert (m["lead"], m["owner"], m["repo"]) == ("pubdoc @ ", "Sustenaut", "pubdoc"), m.groupdict()
    assert m["file"].startswith("pubdoc-")


@given("pubdoc init has run")
def init_ran(pubtest_ctx, run, binary):
    done = run(binary("pubdoc"), "init", cwd=scratch(pubtest_ctx))
    assert done.code == 0, done.describe()


@given("shellcheck is installed")
def shellcheck_installed():
    if not shutil.which("shellcheck"):
        # CI's runner has it; a laptop may not.
        assert not os.environ.get("CI"), "shellcheck is not installed"
        pytest.skip("shellcheck is not installed")
