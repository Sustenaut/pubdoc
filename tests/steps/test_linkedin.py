"""Steps for `pubdoc linkedin`."""

from __future__ import annotations

import json

from pytest_bdd import given, parsers, scenarios

scenarios("linkedin.feature")


@given(parsers.parse('a publet "{name}" with id {pid:d} reading "{text}"'))
def publet(repo, name, pid, text):
    (repo / "publets").mkdir(exist_ok=True)
    (repo / "publets" / f"{name}.md").write_text(
        f"---\nid: {pid}\nurl: https://example.org/{name}\ntext: {text}\n---\n\nA synopsis.\n")
    registry = repo / "publets-local.json"
    names = json.loads(registry.read_text()) if registry.exists() else {}
    names[name] = pid
    registry.write_text(json.dumps(names))
