"""Where a project's versions go: its storage tenant, and the corpus that
signs its version publets.

A repository that collects several projects sets defaults in a pubdoc.yml
at its root; a project's own project.yml overrides them:

    # pubdoc.yml, at the repository's root
    storage: {tenant: documents}
    corpus: {path: corpus, key: pub:sha2-256:...}

    # <project>/project.yml
    storage: {tenant: publet-design}
    corpus: {path: corpus}        # relative to the project: <project>/corpus

A corpus's path in pubdoc.yml is relative to the repository's root, in
project.yml to the project's directory. Without either, the corpus is
corpus/ at the repository's root. `key` is the corpus's signing key, the
one verify trusts; without it, verify says which key signed and accepts it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import projects

ROOT_FILE = "pubdoc.yml"
STORAGE_URL = "https://storage.sustenaut.eu"


@dataclass(frozen=True)
class Settings:
    root: Path
    tenant: str | None
    storage_url: str
    corpus: Path
    key: str | None


def root_config(root: Path, problems: list[projects.Problem]) -> dict:
    file = root / ROOT_FILE
    if not file.is_file():
        return {}
    data = projects.read_yaml(file, problems)
    if data is None:
        return {}
    found = projects.schema_problems("pubdoc", data, file)
    problems.extend(found)
    return {} if found else data


def of(project: projects.Project) -> Settings:
    """The settings `project` versions with: its own, else its repository's pubdoc.yml's."""
    root = projects.repo_root(project.path).resolve()
    base = root_config(root, [])
    storage = {**base.get("storage", {}), **project.config.get("storage", {})}
    corpus_base, corpus_own = base.get("corpus", {}), project.config.get("corpus", {})
    if "path" in corpus_own:
        corpus = project.path / corpus_own["path"]
    else:
        corpus = root / corpus_base.get("path", "corpus")
    return Settings(root=root, tenant=storage.get("tenant"),
                    storage_url=storage.get("url", STORAGE_URL).rstrip("/"),
                    corpus=corpus.resolve(),
                    key=corpus_own.get("key", corpus_base.get("key")))
