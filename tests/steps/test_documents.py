"""Steps for listing documents and approving a variant's PDF."""

from __future__ import annotations

from pytest_bdd import given, parsers, scenarios, then

from conftest import calls, today_pdf

scenarios("documents.feature")


@given(parsers.parse('"{path}" sets version_name "{name}"'))
def version_name(repo, path, name):
    with (repo / path).open("a") as f:
        f.write(f'version_name: "{name}"\n')


@given(parsers.parse('"{path}" is built'))
def built(repo, path):
    (repo / path).write_bytes(b"%PDF-1.7\n")


@then(parsers.parse('it prints today\'s "{prefix}" PDF'))
def prints_pdf(result, prefix):
    assert result.stdout.strip() == today_pdf(prefix), result.stdout


@then(parsers.parse('today\'s "{prefix}" PDF exists'))
def pdf_exists(repo, prefix):
    assert (repo / today_pdf(prefix)).read_bytes() == b"%PDF-1.7\n"


@then(parsers.re(r'review-builder-preview was run in "(?P<where>[^"]*)" with "(?P<args>[^"]*)"'))
def preview_ran(tmp_path, repo, where, args):
    assert ("review-builder-preview", str(repo / where), args) in calls(tmp_path), calls(tmp_path)
