"""A doc's versions: each one a signed publet, its renders in storage.

Approving a doc's variant builds every layout of it, uploads each render
to the project's storage tenant (named there by its SHA-256), writes the
version publet's source into the corpus (corpus/publets/<slug>/publet.json)
and has `pub` sign and publish it, then records the version in
<doc>/versions/versions.yml, the index people read. Each doc and variant is
one lineage, slug doc.<project>.<doc>.<variant>: a new version supersedes
the one before. Its claims:

    #identity  which doc, variant and version; who approved it, when; the
               pubdoc that built it and the commit it was built from
    #sources   every file it was built from, by path and SHA-256
    #renders   every render: layout, format, SHA-256, size, address

Renders are outputs, not publets, so a publet holds their checksums and
addresses, never the files. Signed objects are committed in the corpus's
objects/; the key is in its untracked .publet/, on the approver's machine.

verify checks every versions.yml against the corpus's signed objects:
`pub` verifies the corpus as the parent of a scratch corpus, which checks
every generation record's signature and every object's hash, and each
version's claims must state what versions.yml says.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import projects, settings, storage
from .projects import VERSIONS, Doc, Render

INDEX = "versions.yml"
LOCK = "corpus.lock"
PUB_SUPPORTED = ("0.4.",)
PUB_INSTALL = ("cargo install --locked --git https://github.com/Sustenaut/publet "
               "--tag v0.4.0 publet-cli")
IDENTITY = ["doc", "variant", "version", "approved", "approved_by", "pubdoc", "commit", "rebuilt_from"]
SOURCES = ["path", "sha256"]
RENDERS = ["layout", "format", "sha256", "bytes", "url"]


class VersionError(Exception):
    pass


# pub ---------------------------------------------------------------------

def pub_program() -> str:
    return os.environ.get("PUB", "pub")


def require_pub() -> str:
    program = shutil.which(pub_program())
    if not program:
        raise VersionError(f"no `{pub_program()}` on PATH: pubdoc signs and verifies versions with "
                           f"publet's pub 0.4; install it: {PUB_INSTALL}")
    first = subprocess.run([program, "--version"], capture_output=True, text=True).stdout.split("\n")[0]
    if not any(first.startswith(f"pub {v}") for v in PUB_SUPPORTED):
        raise VersionError(f"pubdoc drives pub 0.4, and `{program} --version` says {first!r}; "
                           f"install it: {PUB_INSTALL}")
    return program


def run_pub(where: Path, *args: str) -> str:
    done = subprocess.run([require_pub(), *args], cwd=where, capture_output=True, text=True)
    if done.returncode != 0:
        raise VersionError(f"pub {' '.join(args)} failed in {projects.shown(where)}:\n"
                           f"{done.stdout}{done.stderr}".rstrip())
    return done.stdout


def lock(corpus: Path) -> dict:
    path = corpus / LOCK
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def locked(corpus: Path, slug: str) -> str | None:
    for row in lock(corpus).get("publets", []):
        if row.get("slug") == slug:
            return row.get("cid")
    return None


def read_object(corpus: Path, cid: str) -> dict:
    return json.loads(run_pub(corpus, "read", "--dir=objects", "--json", cid))["object"]


# Naming ------------------------------------------------------------------

def slug(doc: Doc, variant: str) -> str:
    return f"doc.{doc.project.name}.{doc.name}.{variant}"


def tag(name: str, date: str, taken: set[str]) -> str:
    """A Section 9.1 citation tag for a new lineage: DOC-<six letters>-MM-YYYY,
    the letters from the doc's name and variant (acme, research: ACMERE),
    else, when those are taken, from a hash of the slug."""
    _, project, doc, variant = name.split(".", 3)
    alpha = lambda s: re.sub(r"[^A-Za-z]", "", s).upper()  # noqa: E731
    letters = (alpha(doc)[:4] + alpha(variant)[:2] + alpha(project))
    year, month = date[:4], date[5:7]
    candidates = [letters[:6]] if len(letters) >= 6 else []
    digest = hashlib.sha256(name.encode()).digest()
    candidates.append("".join(chr(65 + b % 26) for b in digest[:6]))
    for word in candidates:
        found = f"DOC-{word}-{month}-{year}"
        if found not in taken:
            return found
    raise VersionError(f"no free citation tag for {name}")


def taken_tags(corpus: Path) -> set[str]:
    return {row["tag"] for row in lock(corpus).get("publets", []) if row.get("tag")}


# The index ---------------------------------------------------------------

def index_path(doc: Doc) -> Path:
    return doc.path / VERSIONS / INDEX


def read_index(doc: Doc) -> dict:
    path = index_path(doc)
    if not path.is_file():
        return {"doc": doc.label, "versions": []}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("versions", [])
    return data


def write_index(doc: Doc, data: dict) -> Path:
    path = index_path(doc)
    path.parent.mkdir(exist_ok=True)
    path.write_text("# Written by `pubdoc approve` from the signed version publets: never edit.\n"
                    + yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def latest(index: dict, variant: str) -> dict | None:
    return next((v for v in index["versions"] if v.get("variant") == variant), None)


# Approving ---------------------------------------------------------------

CREATED_VAR = "PUB_CREATED"


def now() -> str:
    """When a version is approved: $PUB_CREATED, which pins pub's dates too,
    else the current instant, RFC 3339 UTC to the second."""
    pinned = os.environ.get(CREATED_VAR)
    if pinned:
        return pinned
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Approval:
    approver: str
    date: str          # YYYY-MM-DD
    commit: str
    rebuilt_from: str  # "" unless rebuilt from an earlier commit's sources
    pubdoc: str
    signed: str = ""   # when it was approved, RFC 3339 UTC: the publet's created

    @property
    def timestamp(self) -> int:
        """The renders' creation time: midnight UTC of the approval date, so a
        rebuild of the same sources with the same tools is the same bytes."""
        day = datetime.date.fromisoformat(self.date)
        return int(datetime.datetime(day.year, day.month, day.day, tzinfo=datetime.timezone.utc).timestamp())


def source_rows(doc: Doc, files: dict[Path, bytes]) -> list[list[str]]:
    root = projects.repo_root(doc.project.path).resolve()
    rows = {}
    for path in [doc.project.file, doc.path / projects.DOC_FILE]:
        if path.is_file():
            rows[os.path.relpath(path.resolve(), root)] = storage.sha256(path.read_bytes())
    for rel, data in files.items():
        rows[os.path.relpath((doc.project.path / rel).resolve(), root)] = storage.sha256(data)
    return [[path, rows[path]] for path in sorted(rows)]


def columns(names: list[str]) -> list[dict]:
    return [{"name": n} for n in names]


def publet_source(doc: Doc, variant: str, number: int, approval: Approval, the_tag: str,
                  sources: list[list[str]], renders: list[list]) -> dict:
    who = f"{doc.label} ({variant})"
    scope = f"version {number} of the doc {doc.label}, variant {variant}"
    evidence = [{"ref": doc.project.name, "revision": approval.commit}]
    rebuilt = (f", rebuilt from the sources of commit {approval.rebuilt_from}"
               if approval.rebuilt_from else "")
    return {
        "slug": slug(doc, variant), "tag": the_tag, "title": who,
        # When the version was approved, not the doc's date: `created` is
        # the signer's claim of when it signed. The doc's date is in the
        # identity claim's sentence and data row.
        "created": approval.signed or now(),
        "claims": {
            "identity": {
                "class": "archival", "scope": scope,
                "content": (f"Version {number} of {who} was approved by {approval.approver} on "
                            f"{approval.date}, built by pubdoc {approval.pubdoc} from commit "
                            f"{approval.commit}{rebuilt}."),
                "data": {"columns": columns(IDENTITY),
                         "rows": [[doc.label, variant, str(number), approval.date, approval.approver,
                                   approval.pubdoc, approval.commit, approval.rebuilt_from]]},
                "sources": evidence,
            },
            "sources": {
                "class": "archival", "scope": scope, "depends": ["#identity"],
                "content": f"Version {number} of {who} was built from these files.",
                "data": {"columns": columns(SOURCES), "rows": sources},
                "sources": evidence,
            },
            "renders": {
                "class": "archival", "scope": scope, "depends": ["#identity"],
                "content": f"Version {number} of {who} is rendered as these files, kept in storage.",
                "data": {"columns": columns(RENDERS), "rows": renders},
                "sources": evidence,
            },
        },
        "sections": [{"heading": h, "items": [{"ref": f"#{c}"}]}
                     for h, c in (("Identity", "identity"), ("Sources", "sources"), ("Renders", "renders"))],
    }


def publish(doc: Doc, variant: str, approval: Approval, renders: list[Render],
            files: dict[Path, bytes]) -> dict:
    """Upload `renders` (built), sign the version publet, and record it in
    versions.yml. Returns the new index entry."""
    conf = settings.of(doc.project)
    if not conf.tenant:
        raise VersionError(f"{projects.shown(doc.project.path)} names no storage tenant: set "
                           "storage: {tenant: ...} in its project.yml, or in "
                           f"{settings.ROOT_FILE} at the repository's root")
    corpus = conf.corpus
    if not (corpus / "corpus.json").is_file():
        raise VersionError(f"no corpus at {projects.shown(corpus)}: make it with `pub corpus init` there, "
                           "and its signing key with `pub sign --generate-key --principal=human`")
    require_pub()
    index = read_index(doc)
    before = latest(index, variant)
    number = int(before["version"]) + 1 if before else 1
    rows, addresses = [], {}
    for r in renders:
        data = r.output.read_bytes()
        name = f"{doc.name}-{variant}-{r.layout}-v{number}.{r.extension}"
        url = storage.upload(conf.storage_url, conf.tenant, name, data,
                             f"{doc.label} {variant} {r.layout}, version {number}")
        rows.append([r.layout, r.spec["format"], storage.sha256(data), len(data), url])
        addresses[r.layout] = {"url": url, "sha256": storage.sha256(data)}
    the_slug = slug(doc, variant)
    source_file = corpus / "publets" / the_slug / "publet.json"
    if source_file.is_file():
        the_tag = json.loads(source_file.read_text(encoding="utf-8"))["tag"]
    else:
        the_tag = tag(the_slug, approval.date, taken_tags(corpus))
    source = publet_source(doc, variant, number, approval, the_tag, source_rows(doc, files), rows)
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(json.dumps(source, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    run_pub(corpus, "build")
    run_pub(corpus, "publish", the_slug)
    identity = locked(corpus, f"{the_slug}#identity")
    key = lock(corpus).get("corpus", {}).get("key")
    if conf.key and key != conf.key:
        raise VersionError(f"the corpus at {projects.shown(corpus)} signed with {key}, "
                           f"and the project trusts {conf.key}")
    entry = {
        "version": number, "variant": variant, "approved": approval.date,
        "approved_by": approval.approver,
        "publet": identity,
        "objects": {c: locked(corpus, f"{the_slug}#{c}") for c in ("identity", "sources", "renders")},
        "supersedes": before["publet"] if before else None,
        "pubdoc": approval.pubdoc, "commit": approval.commit,
    }
    if approval.rebuilt_from:
        entry["rebuilt_from"] = approval.rebuilt_from
    entry["renders"] = addresses
    write_index(doc, {"doc": doc.label, "corpus": os.path.relpath(corpus, index_path(doc).parent),
                      "key": key, "versions": [entry] + index["versions"]})
    return entry


# Verifying ---------------------------------------------------------------

def tenant_base(conf: settings.Settings) -> str:
    return f"{conf.storage_url}/{conf.tenant}/"


def source_problems(doc: Doc, where: str, commit: str, rows: list[list]) -> list[str]:
    """Each source row against the file at `commit`, so a version approved
    with uncommitted changes shows. A commit this clone lacks (a shallow
    CI checkout) is a note, not a problem."""
    root = projects.repo_root(doc.project.path)
    known = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{commit}^{{commit}}"],
                           capture_output=True)
    if known.returncode != 0:
        return [f"note: {where}: commit {commit} is not in this clone; its sources are not checked"]
    found = []
    for path, digest in rows:
        shown = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{path}"], capture_output=True)
        if shown.returncode != 0:
            found.append(f"{where}: {path} is not in commit {commit}")
        elif storage.sha256(shown.stdout) != digest:
            found.append(f"{where}: {path} at commit {commit} is not the file it was built from")
    return found


def verify_corpus(corpus: Path) -> None:
    """Every generation of `corpus` signed by its key, every object its hash:
    pub checks a parent so whenever a corpus names one, so a scratch corpus
    naming this one as its parent has pub check it, without a key store."""
    with tempfile.TemporaryDirectory(prefix="pubdoc-verify-") as scratch:
        (Path(scratch) / "corpus.json").write_text(json.dumps({
            "name": "verify", "label": "verify", "bound": 67108864,
            "parents": [{"alias": "checked", "path": str(corpus)}]}), encoding="utf-8")
        run_pub(Path(scratch), "corpus", "status")


def claim_rows(corpus: Path, cid: str, names: list[str]) -> list[list]:
    body = read_object(corpus, cid).get("body", {})
    stated = [c.get("name") for c in body.get("data", {}).get("columns", [])]
    if stated != names:
        raise VersionError(f"{cid} has columns {stated}, not {names}")
    return body["data"]["rows"]


def verify_doc(doc: Doc, remote: bool) -> list[str]:
    """Why this doc's versions.yml does not hold, if it does not."""
    problems = []
    path = index_path(doc)
    index = read_index(doc)
    conf = settings.of(doc.project)
    # The corpus is the one the project's settings name, the one verify_corpus
    # checked: a versions.yml naming any other is not taken at its word.
    corpus = conf.corpus
    named = (path.parent / index.get("corpus", "")).resolve() if index.get("corpus") else None
    if named != corpus:
        problems.append(f"{projects.shown(path)}: names the corpus {index.get('corpus')!r}, "
                        f"and the project's is {projects.shown(corpus)}")
    signer = lock(corpus).get("corpus", {}).get("key")
    if index.get("key") != signer:
        problems.append(f"{projects.shown(path)}: key {index.get('key')} is not the corpus's, {signer}")
    if conf.key and signer != conf.key:
        problems.append(f"{projects.shown(corpus)}: signed by {signer}, and the project trusts {conf.key}")
    numbers: dict[str, list[int]] = {}
    for entry in index["versions"]:
        where = f"{projects.shown(path)}: version {entry.get('version')} ({entry.get('variant')})"
        numbers.setdefault(entry.get("variant"), []).append(int(entry.get("version", 0)))
        objects = entry.get("objects", {})
        try:
            identity = claim_rows(corpus, objects.get("identity", ""), IDENTITY)[0]
            rendered = claim_rows(corpus, objects.get("renders", ""), RENDERS)
            sourced = claim_rows(corpus, objects.get("sources", ""), SOURCES)
        except (VersionError, KeyError, IndexError, json.JSONDecodeError) as e:
            problems.append(f"{where}: its publet cannot be read: {e}")
            continue
        stated = dict(zip(IDENTITY, identity, strict=False))
        for field, value in (("doc", doc.label), ("variant", entry.get("variant")),
                             ("version", str(entry.get("version"))), ("approved", entry.get("approved")),
                             ("approved_by", entry.get("approved_by")), ("commit", entry.get("commit"))):
            if stated.get(field) != value:
                problems.append(f"{where}: says {field} {value!r}, its publet {stated.get(field)!r}")
        problems.extend(source_problems(doc, where, stated.get("commit", ""), sourced))
        renders = {row[0]: {"url": row[4], "sha256": row[2]} for row in rendered}
        if renders != entry.get("renders"):
            problems.append(f"{where}: its renders are not the ones its publet records")
        if remote:
            for layout, render in renders.items():
                try:
                    storage.download(render["url"], render["sha256"], tenant_base(conf))
                except storage.StorageError as e:
                    problems.append(f"{where}: {layout}: {e}")
    for variant in numbers:
        head = locked(corpus, f"{slug(doc, variant)}#identity")
        newest = latest(index, variant)
        if newest and head != newest["objects"].get("identity"):
            problems.append(f"{projects.shown(path)}: {variant}'s newest version is not the corpus's, "
                            f"{head}: a version is missing from versions.yml")
    for variant, seen in numbers.items():
        if seen != sorted(seen, reverse=True) or sorted(seen) != list(range(1, len(seen) + 1)):
            problems.append(f"{projects.shown(path)}: {variant}'s versions are {seen}, not newest first from 1")
    return problems
