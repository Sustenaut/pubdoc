"""Steps for listing projects, and previewing and approving a render."""

from __future__ import annotations

import os

from pytest_bdd import parsers, scenarios, then

from conftest import scratch, today_pdf

scenarios("documents.feature")


@then(parsers.parse('it prints today\'s "{prefix}" PDF'))
def prints_pdf(result, prefix):
    """The whole of stdout is the path, with today's date in it: pubtest's
    steps have no date to put in a value."""
    assert result.stdout.strip() == today_pdf(prefix), result.stdout


@then(parsers.parse('today\'s "{prefix}" PDF holds "{text}"'))
def pdf_holds(pubtest_ctx, prefix, text):
    path = scratch(pubtest_ctx) / today_pdf(prefix)
    assert path.read_text(encoding="utf-8") == text + "\n", path


@then(parsers.parse('the file "{path}" links to "{target}"'))
def links_to(pubtest_ctx, path, target):
    """A symbolic link and what it names: pubtest has no step for links."""
    assert os.readlink(scratch(pubtest_ctx) / path) == target
