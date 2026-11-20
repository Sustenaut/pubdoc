"""Steps for `pubdoc corpus init`, against stand-ins for pub and pubsec."""

from __future__ import annotations

import re
import shutil
import stat
import sys

import pytest
from pytest_bdd import given, parsers, scenarios, then

from conftest import calls, pubdoc
from standins import PUB, PUBSEC

scenarios("corpus.feature")


def executable(path, text):
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@given("publet's pub is installed")
def pub_installed(fakes):
    executable(fakes / "pub", PUB.replace("#!PYTHON", f"#!{sys.executable}"))


@given("pubsec is a stand-in")
def pubsec_stand_in(fakes, env):
    executable(fakes / "pubsec", PUBSEC)
    env["PUBDOC_PUBSEC"] = str(fakes / "pubsec")


@given(parsers.re(r'pubdoc (?P<args>(?:"[^"]*" ?)+?) has run$'))
def pubdoc_ran(repo, run, env, args):
    argv = args.strip().strip('"').split('" "')
    done = run(pubdoc(), *argv, cwd=repo, env=env)
    assert done.code == 0, done


def trusted(repo) -> str:
    return re.search(r"key: (pub:sha2-256:\S+?)}", (repo / "pubdoc.yml").read_text()).group(1)


@pytest.fixture
def remembered():
    return {}


@given("the trusted key is remembered")
def remember(repo, remembered):
    remembered["key"] = trusted(repo)


@then("the trusted key is the one remembered")
def same_key(repo, remembered):
    assert trusted(repo) == remembered["key"]


@given("the corpus's store is gone from this machine")
def store_gone(repo):
    shutil.rmtree(repo / "corpus" / ".publet")


@given("the corpus has committed its key object")
def key_committed(repo):
    # pub commits it in objects/ at the corpus's first publish; only that it
    # is there matters to pubdoc.
    objects = repo / "corpus" / "objects"
    objects.mkdir(exist_ok=True)
    (objects / (trusted(repo).replace(":", "_") + ".cbor")).write_bytes(b"the key object")


@given("the corpus's store is gone from this machine, its key put back")
def key_put_back(repo):
    secret = (repo / "corpus" / ".publet" / "signing.key").read_bytes()
    shutil.rmtree(repo / "corpus" / ".publet")
    (repo / "corpus" / ".publet").mkdir()
    (repo / "corpus" / ".publet" / "signing.key").write_bytes(secret)


@given("the corpus's store is gone from this machine, another key put in its place")
def other_key(repo):
    shutil.rmtree(repo / "corpus" / ".publet")
    (repo / "corpus" / ".publet").mkdir()
    (repo / "corpus" / ".publet" / "signing.key").write_text("another key\n")


@then(parsers.parse('pubsec was asked to "{args}"'))
def pubsec_asked(tmp_path, args):
    assert any(tool == "pubsec" and argv == args for tool, _, argv in calls(tmp_path)), calls(tmp_path)


@then(parsers.parse('pub was run in "{where}" with "{args}"'))
def pub_ran(tmp_path, repo, remembered, where, args):
    wanted = args.replace("{trusted}", remembered.get("key", ""))
    assert ("pub", str(repo / where), wanted) in calls(tmp_path), calls(tmp_path)
