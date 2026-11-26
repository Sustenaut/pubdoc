"""Steps for a doc's versions: approve, versions, fetch, verify, and compare.

`pub`, storage and poppler are stand-ins (standins.py): the suite checks
what pubdoc asks of them and what it records, not publet's signatures or
storage itself.
"""

from __future__ import annotations

import datetime
import json
import stat
import subprocess
import sys

import pytest
import yaml
from pytest_bdd import given, parsers, scenarios, then

from conftest import calls, pubdoc
from standins import POPPLER, PUB, Storage

scenarios("versions.feature")
scenarios("compare.feature")


@pytest.fixture
def storage():
    server = Storage()
    yield server
    server.close()


def executable(path, text):
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@given("publet's pub is installed")
def pub_installed(fakes):
    executable(fakes / "pub", PUB.replace("#!PYTHON", f"#!{sys.executable}"))


@given("poppler is installed")
def poppler_installed(fakes):
    for name, body in POPPLER.items():
        executable(fakes / name, f"#!/bin/sh\n{body}")


@given(parsers.parse('pub says it is "{first_line}"'))
def pub_version(env, first_line):
    env["PUBDOC_TEST_PUB_VERSION"] = first_line


@given(parsers.parse('storage takes the tenant "{tenant}" for the repository'))
def storage_tenant(repo, env, storage, tenant):
    (repo / "pubdoc.yml").write_text(f"storage: {{tenant: {tenant}, url: \"{storage.url}\"}}\n")
    env["PUBDOC_STORAGE_TOKEN"] = Storage.TOKEN


@given(parsers.parse('a corpus at "{path}" with its signing key'))
def corpus(repo, path):
    where = repo / path
    (where / ".publet").mkdir(parents=True)
    (where / "corpus.json").write_text('{"name": "corpus", "label": "corpus", "bound": 67108864, "parents": []}\n')
    (where / ".publet" / "signing.key").write_bytes(b"a test key, not a real one")
    with (repo / ".gitignore").open("a") as f:
        f.write("/corpus/.publet/\n")


@given(parsers.parse('"{who}" approves'))
def who_approves(env, who):
    env["PUBDOC_APPROVER"] = who


GIT = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.org"]


@given("everything is committed")
def committed(repo):
    subprocess.run([*GIT, "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run([*GIT, "-C", str(repo), "commit", "-q", "-m", "change"], check=True, capture_output=True)


@given(parsers.parse('storage serves other bytes for "{layout}" of "{doc}"'))
def storage_tampers(repo, storage, layout, doc):
    index = yaml.safe_load((repo / doc / "versions" / "versions.yml").read_text())
    storage.files[index["versions"][0]["renders"][layout]["sha256"]] = b"%PDF-1.7 something else"


def index(repo, doc):
    return yaml.safe_load((repo / doc / "versions" / "versions.yml").read_text())


@then(parsers.parse('"{doc}" records version {number:d} of "{variant}", approved by "{who}"'))
def records(repo, doc, number, variant, who):
    entry = next(e for e in index(repo, doc)["versions"] if e["variant"] == variant and e["version"] == number)
    assert entry["approved_by"] == who, entry
    assert entry["publet"].startswith("pub:sha2-256:"), entry


@then(parsers.parse('"{doc}"\'s version {number:d} supersedes version {earlier:d}'))
def supersedes(repo, doc, number, earlier):
    versions = {e["version"]: e for e in index(repo, doc)["versions"]}
    assert versions[number]["supersedes"] == versions[earlier]["publet"], versions
    assert [e["version"] for e in index(repo, doc)["versions"]][:2] == [number, earlier]


@then(parsers.parse('"{doc}"\'s renders are in storage with their checksums'))
def renders_stored(repo, storage, doc):
    import hashlib
    for entry in index(repo, doc)["versions"]:
        for render in entry["renders"].values():
            data = storage.files[render["sha256"]]
            assert hashlib.sha256(data).hexdigest() == render["sha256"]
            assert render["url"].startswith(storage.url)


@then(parsers.parse('storage holds {count:d} files'))
def storage_holds(storage, count):
    assert len(storage.files) == count, list(storage.files)


@then(parsers.parse('pub was run in "{where}" with "{args}"'))
def pub_ran(tmp_path, repo, where, args):
    assert ("pub", str(repo / where), args) in calls(tmp_path), calls(tmp_path)


@then(parsers.parse('typst was asked for the creation time {stamp:d}'))
def typst_stamp(tmp_path, stamp):
    assert any(tool == "typst" and f"--creation-timestamp {stamp} " in argv
               for tool, _, argv in calls(tmp_path)), calls(tmp_path)


@given(parsers.parse('the repository\'s corpus is at "{path}"'))
def corpus_at(repo, path):
    with (repo / "pubdoc.yml").open("a") as f:
        f.write(f"corpus: {{path: {path}}}\n")


@given(parsers.parse('the repository trusts the key "{key}"'))
def trusts(repo, key):
    with (repo / "pubdoc.yml").open("a") as f:
        f.write(f"corpus: {{key: \"{key}\"}}\n")


@given(parsers.parse('every object in "{path}" has a byte more'))
def tamper(repo, path):
    for obj in (repo / path).glob("*.cbor"):
        with obj.open("ab") as f:
            f.write(b" ")


@given(parsers.re(r'pubdoc (?P<args>(?:"[^"]*" ?)+?) has run$'))
def pubdoc_ran(repo, run, env, args):
    argv = args.strip().strip('"').split('" "')
    done = run(pubdoc(), *argv, cwd=repo, env=env)
    assert done.code == 0, done


@given(parsers.parse('the newest "{layout}" render of "{doc}" is recorded at "{url}"'), target_fixture="asked")
def recorded_at(repo, storage, layout, doc, url):
    path = repo / doc / "versions" / "versions.yml"
    data = yaml.safe_load(path.read_text())
    host = storage.url.split("://", 1)[1]
    data["versions"][0]["renders"][layout]["url"] = url.replace("{storage}", storage.url).replace("{host}", host)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return storage.requests


@then("storage was asked for nothing more")
def nothing_more(storage, asked):
    assert storage.requests == asked, storage.requests


@given(parsers.parse('the newest version is dropped from "{doc}"\'s versions.yml'))
def drop_newest(repo, doc):
    path = repo / doc / "versions" / "versions.yml"
    data = yaml.safe_load(path.read_text())
    data["versions"] = data["versions"][1:]
    path.write_text(yaml.safe_dump(data, sort_keys=False))


@given(parsers.parse('pub\'s dates are pinned to "{instant}"'))
def dates_pinned(monkeypatch, instant):
    monkeypatch.setenv("PUB_CREATED", instant)


def _publet_created(repo, doc: str) -> str:
    slug = "doc." + doc.replace("/", ".") + ".engineering"
    return json.loads((repo / "corpus" / "publets" / slug / "publet.json").read_text())["created"]


@then(parsers.parse('the version publet of "{doc}" is dated within a minute of now'))
def publet_dated_now(repo, doc):
    created = _publet_created(repo, doc)
    then_ = datetime.datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)
    assert abs((datetime.datetime.now(datetime.UTC) - then_).total_seconds()) < 60, created


@then(parsers.parse('the version publet of "{doc}" is dated "{instant}"'))
def publet_dated(repo, doc, instant):
    assert _publet_created(repo, doc) == instant
