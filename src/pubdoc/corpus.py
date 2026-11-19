"""`pubdoc corpus init`: the corpus a repository's (or a project's) versions
are signed in, and its key, made once and backed up; or rebuilt around a
key put back from its backup.

    pubdoc corpus init [PROJECT] [--bitwarden-project ID] [--backup-name NAME] [--no-backup]

The corpus is the one the settings name (settings.py): a project's own when
its project.yml names one, else the repository's. Each step is done only
when it is not done yet, so running it again changes nothing:

1. With no key on this machine and no corpus.key in the config: `pub corpus
   init` makes the corpus (corpus.json, and the store .publet/), `pub sign
   --generate-key --principal=human` its key, and corpus.key in the config
   (pubdoc.yml, or the project's project.yml when it names its own corpus)
   then names the key `pubdoc verify` trusts.
2. With corpus.key in the config and no key on this machine: it stops. The
   key is restored with `pubsec signing-key restore`, never made again, or
   the key the config trusts would sign nothing.
3. With a key on this machine and no store around it (one just restored):
   `pub sign --restore-key` rebuilds the store's key object from it, and it
   must come out as the key corpus.key names.
4. pubrules.json's signing_keys declares the key file, under NAME in the
   Bitwarden project ID, where it does not yet (both are needed only then),
   and .gitignore keeps the store out of git.
5. `pubsec signing-key backup` backs every declared key up, asking for a
   Bitwarden token at a hidden prompt: pubsec's pinned wheel, fetched and
   checked against its sha256 first (uvx does not check a URL's #sha256=).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from . import projects, settings, versions

PUBSEC_WHEEL = "https://github.com/Sustenaut/pubsec/releases/download/v0.3.1/pubsec-0.3.1-py3-none-any.whl"
PUBSEC_SHA256 = "e1f5fd270a6af71821a8b41287987ae18ba3af19bb9858c2003a9301805ae967"
STORE = ".publet"
KEY_FILE = "signing.key"
RULES = "pubrules.json"


class CorpusError(Exception):
    pass


def author(corpus: Path) -> str | None:
    config = corpus / STORE / "config"
    if not config.is_file():
        return None
    for line in config.read_text(encoding="utf-8").splitlines():
        if line.startswith("author="):
            return line.split("=", 1)[1].strip()
    return None


def config_file(root: Path, project: projects.Project | None) -> Path:
    """Where corpus.key belongs: the project's project.yml when it names its
    own corpus, else the repository's pubdoc.yml."""
    if project and "corpus" in project.config:
        return project.file
    return root / settings.ROOT_FILE


def write_key(file: Path, corpus_path: str, key: str) -> None:
    """Name `key` as corpus.key in `file`, keeping its other lines (comments
    included): a `corpus:` line in flow style gains or changes its key; a
    file without one gains one."""
    text = file.read_text(encoding="utf-8") if file.is_file() else ""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("corpus:"):
            body = line[len("corpus:"):].strip()
            if not (body.startswith("{") and body.endswith("}")):
                raise CorpusError(f"{projects.shown(file)}: its corpus: is not one line, "
                                  f"{{path: ..}}; add key: {key} to it yourself")
            fields = [f.strip() for f in body[1:-1].split(",") if f.strip() and not f.strip().startswith("key:")]
            lines[i] = f"corpus: {{{', '.join([*fields, f'key: {key}'])}}}"
            break
    else:
        lines.append(f"corpus: {{path: {corpus_path}, key: {key}}}")
    file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def declare(root: Path, key_path: str, name: str | None, project_id: str | None) -> str | None:
    """The Bitwarden name pubrules.json's signing_keys gives the key at
    `key_path`, declaring it when it is not declared yet."""
    rules = root / RULES
    if not rules.is_file():
        return None
    config = json.loads(rules.read_text(encoding="utf-8"))
    for entry in config.get("signing_keys") or []:
        if entry.get("path") == key_path:
            return entry["bitwarden"]["name"]
    if not (name and project_id):
        raise CorpusError(f"{RULES} does not declare {key_path} in signing_keys: give --bitwarden-project "
                          "(the Bitwarden project's id) and --backup-name (the secret's name) to declare it")
    text = rules.read_text(encoding="utf-8")
    entry = json.dumps({"path": key_path, "bitwarden": {"project": {"id": project_id}, "name": name}})
    if '"signing_keys": [' in text:
        text = text.replace('"signing_keys": [', f'"signing_keys": [\n    {entry},', 1)
    else:
        config["signing_keys"] = [json.loads(entry)]
        text = json.dumps(config, indent=2) + "\n"
    json.loads(text)  # still JSON
    rules.write_text(text, encoding="utf-8")
    return name


def ignore(root: Path, store: str) -> bool:
    gitignore = root / ".gitignore"
    text = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    line = f"/{store}/"
    if line in text.splitlines():
        return False
    gap = "" if not text or text.endswith("\n") else "\n"
    gitignore.write_text(f"{text}{gap}# A corpus's signing key and store: only on the approver's machine.\n"
                         f"{line}\n", encoding="utf-8")
    return True


def pubsec(root: Path, *args: str) -> int:
    """Run pubsec's pinned wheel, checked by its sha256; $PUBDOC_PUBSEC names
    another pubsec to run instead."""
    if os.environ.get("PUBDOC_PUBSEC"):
        return subprocess.call([os.environ["PUBDOC_PUBSEC"], *args], cwd=root)
    uvx = shutil.which("uvx")
    if not uvx:
        raise CorpusError("pubsec runs with uv: curl -LsSf https://astral.sh/uv/install.sh | sh")
    with tempfile.TemporaryDirectory(prefix="pubdoc-pubsec-") as scratch:
        wheel = Path(scratch) / PUBSEC_WHEEL.rsplit("/", 1)[1]
        with urllib.request.urlopen(PUBSEC_WHEEL, timeout=120) as answer:
            wheel.write_bytes(answer.read())
        if hashlib.sha256(wheel.read_bytes()).hexdigest() != PUBSEC_SHA256:
            raise CorpusError(f"{wheel.name} is not the pubsec wheel pubdoc pins")
        return subprocess.call([uvx, "--from", str(wheel), "pubsec", *args], cwd=root)


def init(project: projects.Project | None, root: Path, backup_name: str | None,
         bitwarden_project: str | None, backup: bool) -> list[str]:
    """Make or complete the corpus; what was done, line by line."""
    conf = settings.of(project) if project else root_settings(root)
    corpus, trusted = conf.corpus, conf.key
    key_file = corpus / STORE / KEY_FILE
    key_path = os.path.relpath(key_file, root)
    file = config_file(root, project)
    done: list[str] = []
    versions.require_pub()
    if not key_file.is_file():
        if trusted:
            name = declare(root, key_path, None, None) if (root / RULES).is_file() else None
            raise CorpusError(
                f"{projects.shown(file)} trusts {trusted}, and {projects.shown(key_file)} is not on this "
                f"machine: restore it, never make another: pubsec signing-key restore {name or '<its name>'}, "
                "then run this again")
        corpus.mkdir(parents=True, exist_ok=True)
        if not (corpus / "corpus.json").is_file():
            versions.run_pub(corpus, "corpus", "init")
            done.append(f"made the corpus {projects.shown(corpus)}")
        versions.run_pub(corpus, "sign", "--generate-key", "--principal=human")
        key = author(corpus)
        if not (key and key.startswith("pub:sha2-256:")):
            raise CorpusError(f"pub made a key, and {projects.shown(corpus / STORE / 'config')} names none")
        write_key(file, os.path.relpath(corpus, file.parent), key)
        done.append(f"made its key {key}, trusted in {projects.shown(file)}")
    else:
        before = author(corpus)
        if not (trusted and before == trusted):
            # A key put back from its backup: the store around it is rebuilt
            # (pub init's placeholder author included), and must come out as
            # the key the config trusts.
            if not (corpus / STORE / "config").is_file():
                versions.run_pub(corpus, "init")
            args = ["sign", "--restore-key", "--principal=human"]
            if trusted:
                args.append(f"--expect={trusted}")
            try:
                versions.run_pub(corpus, *args)
            except versions.VersionError as e:
                if "--restore-key" in str(e) and "unknown argument" in str(e):
                    raise CorpusError("rebuilding the store around a restored key needs pub 0.4.1 or later "
                                      "(pub sign --restore-key)") from None
                raise
        key = author(corpus)
        if key != before:
            done.append(f"rebuilt the store around {projects.shown(key_file)}: {key}")
        if not trusted:
            write_key(file, os.path.relpath(corpus, file.parent), key)
            done.append(f"trusted {key} in {projects.shown(file)}")
        elif key != trusted:
            raise CorpusError(f"{projects.shown(key_file)} is the key {key}, and {projects.shown(file)} "
                              f"trusts {trusted}")
    name = declare(root, key_path, backup_name, bitwarden_project) if (root / RULES).is_file() else None
    if name:
        done.append(f"{RULES} declares {key_path} as {name}")
    if ignore(root, os.path.relpath(corpus / STORE, root)):
        done.append(f"ignored {os.path.relpath(corpus / STORE, root)}/ in .gitignore")
    if backup and name:
        if pubsec(root, "signing-key", "backup") != 0:
            raise CorpusError("pubsec signing-key backup failed; the key is not backed up yet")
        done.append(f"backed up as {name}")
    return done


def root_settings(root: Path) -> settings.Settings:
    """The repository's own settings, from its pubdoc.yml alone."""
    base = settings.root_config(root, [])
    storage = base.get("storage", {})
    corpus = base.get("corpus", {})
    return settings.Settings(root=root, tenant=storage.get("tenant"),
                             storage_url=storage.get("url", settings.STORAGE_URL).rstrip("/"),
                             corpus=(root / corpus.get("path", "corpus")).resolve(), key=corpus.get("key"))

