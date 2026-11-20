"""pubdoc's command line: check, build, preview and approve the document projects in a repo.

A document project is a directory holding a project.yml, anywhere in a
repository; each doc in it is a directory of MyST parts beside that file
(projects.py says how). `build` stages a doc's parts and the shared parts
they start from in the doc's build/, writes the MyST configuration for
every variant and layout there from project.yml, runs the pinned
Curvenote, then `typst compile` on each Typst export, and runs each
exporter layout. Everything it writes stays in the doc's build/, which
ignores itself.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile
from importlib import metadata, resources
from pathlib import Path

import yaml

from . import compare, corpus, projects, registry, settings, storage, versions
from .projects import BUILD, VERSIONS, Doc, Problem, Project, Render

CURVENOTE_VERSION = "0.17.2"
LAUNCHER = "pubdoc"
# The distribution: PyPI's "pubdoc" is another project, so pubdoc's is
# pubdocrules. The package, the command and the repository stay pubdoc.
DISTRIBUTION = "pubdocrules"
WHEEL_URL = "https://github.com/Sustenaut/pubdoc/releases/download/v{version}/pubdocrules-{version}-py3-none-any.whl"
# The launcher's pin, one requirement line beside it, where pubrules's nightly
# moves it to pubdoc's latest release like any other release wheel pin.
PIN = "requirements-pubdoc.txt"
# Inside a doc's build/: pubdoc's templates, and the staged sources Curvenote builds.
TEMPLATES, SOURCES = "templates", "src"
IGNORE_ALL = "# Written by pubdoc: everything here is built, never committed.\n*\n"


def version() -> str:
    try:
        return metadata.version(DISTRIBUTION)
    except metadata.PackageNotFoundError:  # a checkout run without installing
        return "0+unknown"


def die(message: str, code: int = 1) -> None:
    print(f"pubdoc: {message}", file=sys.stderr)
    sys.exit(code)


def resolve_typst() -> str:
    """typst on PATH, else a local build at ~/git/typst. Curvenote runs typst
    itself too, so its directory goes onto PATH for child processes."""
    found = shutil.which("typst")
    local = Path.home() / "git/typst/target/release/typst"
    if not found and os.access(local, os.X_OK):
        found = str(local)
    if not found:
        die("no 'typst' on PATH and no build at ~/git/typst/target/release/typst.\n"
            "Install typst (https://typst.app), or build it from ~/git/typst:\n"
            "  cargo build --release -p typst-cli --features typst-kit/vendor-openssl")
    os.environ["PATH"] = f"{Path(found).parent}{os.pathsep}{os.environ.get('PATH', '')}"
    return found


def need(program: str, hint: str) -> str:
    found = shutil.which(program)
    if not found:
        die(f"no '{program}' on PATH; {hint}")
    return found


def write_if_changed(path: Path, data: bytes) -> None:
    """Rewrite only a file that differs, so a running preview sees no churn."""
    if not path.is_file() or path.read_bytes() != data:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def mirror(wanted: dict[Path, bytes], target: Path) -> Path:
    """Make `target` hold exactly `wanted`, rewriting only the files that differ."""
    for rel, data in wanted.items():
        write_if_changed(target / rel, data)
    if target.is_dir():
        for path in sorted(target.rglob("*"), reverse=True):
            rel = path.relative_to(target)
            if (path.is_file() or path.is_symlink()) and rel not in wanted:
                path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    return target


def install_templates(target: Path) -> Path:
    """Make `target` hold exactly this release's templates and plugins."""
    wanted: dict[Path, bytes] = {}
    stack = [(resources.files("pubdoc") / "templates", Path())]
    while stack:
        node, prefix = stack.pop()
        for child in node.iterdir():
            if child.is_dir():
                stack.append((child, prefix / child.name))
            else:
                wanted[prefix / child.name] = child.read_bytes()
    return mirror(wanted, target)


def curvenote(*args: str) -> list[str]:
    return [need("npx", "install Node.js (https://nodejs.org)"), "--yes",
            f"curvenote@{CURVENOTE_VERSION}", *args]


# Projects and docs -------------------------------------------------------

def report(problems: list[Problem]) -> None:
    for problem in problems:
        print(f"pubdoc: {problem}", file=sys.stderr)


def load_checked(file: Path) -> tuple[Project | None, list[Problem], list[str]]:
    problems: list[Problem] = []
    project = projects.load(file, problems)
    notes: list[str] = []
    if project:
        found, notes = projects.check(project)
        problems.extend(found)
    return project, problems, notes


def project_or_die(file: Path) -> Project:
    project, problems, _ = load_checked(file)
    if problems or not project:
        report(problems)
        die(f"{projects.shown(file)} has {len(problems)} problem(s); see `pubdoc check`")
    return project


def target(name: str) -> tuple[Project, list[Doc]]:
    """A project directory (all its docs) or one doc directory of it."""
    path = Path(name).resolve()
    if (path / projects.PROJECT_FILE).is_file():
        project = project_or_die(path / projects.PROJECT_FILE)
        if not project.docs:
            die(f"{name} has no docs")
        return project, project.docs
    if (path.parent / projects.PROJECT_FILE).is_file():
        project = project_or_die(path.parent / projects.PROJECT_FILE)
        for doc in project.docs:
            if doc.path == path:
                return project, [doc]
        die(f"{name} is no doc of {projects.shown(project.path)}: it holds no doc.yml and no part file")
    die(f"{name} is not a doc or a project: no project.yml in it or the directory above")
    raise AssertionError  # pragma: no cover - die exits


def one_doc(name: str) -> Doc:
    _, docs = target(name)
    if len(docs) != 1:
        die(f"{name} is a project; name one of its docs: {', '.join(d.label for d in docs)}")
    return docs[0]


def pick(doc: Doc, variant: str | None, layout: str | None) -> Render:
    """The PDF render named, or the doc's only one where a choice is left out."""
    renders = [r for r in doc.renders(variant, layout) if r.spec["format"] == "pdf"]
    if len(renders) == 1:
        return renders[0]
    if not renders:
        die(f"{doc.label} has no PDF layout for {variant or 'any variant'} and {layout or 'any layout'}")
    choices = sorted({f"{r.variant} {r.layout}" for r in renders})
    die(f"{doc.label} has {len(renders)} PDF renders ({', '.join(choices)}); name the variant and layout")
    raise AssertionError  # pragma: no cover - die exits


# Commands ----------------------------------------------------------------

def cmd_check(args: argparse.Namespace) -> int:
    start = Path(args.path)
    if not start.exists():
        die(f"{args.path} does not exist")
    files = projects.find(start)
    if not files:
        die(f"no project.yml in {args.path} or below it")
    problems: list[Problem] = []
    notes: set[str] = set()
    docs = 0
    roots = set()
    for file in files:
        project, found, said = load_checked(file)
        problems.extend(found)
        notes.update(said)
        docs += len(project.docs) if project else 0
        roots.add(projects.repo_root(file.parent).resolve())
    for root in sorted(roots):
        settings.root_config(root, problems)
    for note in sorted(notes):
        print(f"note: {note}")
    if problems:
        report(problems)
        print(f"{len(problems)} problem(s) in {len(files)} project(s)", file=sys.stderr)
        return 1
    print(f"checked {len(files)} project(s) with {docs} doc(s): no problems")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    for file in projects.find(Path(args.path)):
        problems: list[Problem] = []
        project = projects.load(file, problems)
        if not project:
            print(f"{projects.shown(file.parent)}: does not load; see `pubdoc check`")
            continue
        print(f"{projects.shown(project.path)}: {project.config['purpose']}")
        for doc in project.docs:
            print(f"  {doc.label}  ({', '.join(doc.variants())})")
    return 0


def cmd_variants(args: argparse.Namespace) -> int:
    for variant in one_doc(args.name).variants():
        print(variant)
    return 0


def doc_files(doc: Doc) -> dict[Path, bytes]:
    """The doc's files and those of the shared parts it starts from, by
    their path in the project, so a part's MyST include of ../shared/...
    resolves the same when staged."""
    project = doc.project
    wanted: dict[Path, bytes] = {}
    sources = [doc.path] + sorted({project.shared_dir(part) for part in project.config["parts"]
                                  if project.shared_dir(part)})
    for source in sources:
        if not source.is_dir():
            continue
        rel = source.relative_to(project.path)
        for here, dirs, files in os.walk(source):
            dirs[:] = [d for d in dirs if not (Path(here) == doc.path and d in (BUILD, VERSIONS))
                       and not d.startswith(".")]
            for f in files:
                path = Path(here) / f
                wanted[rel / path.relative_to(source)] = path.read_bytes()
    return wanted


def fonts() -> Path:
    """The fonts pubdoc carries (fonts/README.md): typst sees these alone."""
    return Path(str(resources.files("pubdoc") / "fonts"))


def typst_fonts() -> list[str]:
    return ["--ignore-system-fonts", "--font-path", str(fonts())]


def myst_config(doc: Doc, root: Path, toc: list[Path], renders: list[Render],
                date: str | None = None) -> bytes:
    """A myst.yml in `root` whose table of contents is `toc` and which
    exports each render. An export through the table of contents, not one
    naming its `article:`, nests a part's headings under its title (# is a
    level-2 heading), as the templates expect."""
    templates = os.path.relpath(doc.path / BUILD / TEMPLATES, root)
    plugins = [str(Path(templates) / "annotations.mjs")]
    # pub-plugin.mjs needs the repository's publets-local.json, found upwards.
    if any((d / "publets-local.json").is_file() for d in [doc.path, *doc.path.parents]):
        plugins.insert(0, str(Path(templates) / "pub-plugin.mjs"))
    exports = [{"format": "typst",
                "template": (os.path.relpath(local, root)
                             if (local := doc.project.template_dir(r.spec["template"]))
                             else str(Path(templates) / r.spec["template"])),
                "output": os.path.relpath(r.typst_source, root)}
               for r in renders]
    project = {"plugins": plugins, "toc": [{"file": str(f)} for f in toc], "exports": exports}
    if date:
        # The doc's date, which a template prints, unless a part sets its own.
        project["date"] = date
    myst = {"version": 1, "project": project, "site": {"nav": []}}
    return ("# Written by pubdoc from project.yml: do not edit.\n"
            + yaml.safe_dump(myst, sort_keys=False)).encode()


def stage(doc: Doc, renders: list[Render], date: str | None = None) -> dict[Path, list[Render]]:
    """Stage one MyST project per part file the Typst renders use, in
    build/src/<file>/, each holding the doc's files and its shared parts and
    a myst.yml whose table of contents is that one file. Curvenote builds a
    project's exports from its table of contents, so a project per file is
    what lets each render take its own variant of a part."""
    files = doc_files(doc)
    src = doc.path / BUILD / SOURCES
    groups: dict[Path, list[Render]] = {}
    for r in renders:
        if "template" in r.spec:
            groups.setdefault(r.source.relative_to(doc.project.path), []).append(r)
    wanted: dict[Path, bytes] = {}
    staged: dict[Path, list[Render]] = {}
    for article, group in groups.items():
        name = Path(".".join(article.with_suffix("").parts))
        for rel, data in files.items():
            wanted[name / rel] = data
        wanted[name / "myst.yml"] = myst_config(doc, src / name, [article], group, date)
        staged[src / name] = group
    mirror(wanted, src)
    return staged


def stage_site(doc: Doc) -> Path:
    """One MyST project of every part file the doc's renders use, for a live site."""
    site = doc.path / BUILD / "site"
    wanted = doc_files(doc)
    toc = sorted({r.source.relative_to(doc.project.path) for r in doc.renders()})
    wanted[Path("myst.yml")] = myst_config(doc, site, toc, [])
    return mirror(wanted, site)


def prepare(doc: Doc) -> Path:
    out = doc.path / BUILD
    write_if_changed(out / ".gitignore", IGNORE_ALL.encode())
    return install_templates(out / TEMPLATES)


def build(doc: Doc, typst: str, variant: str | None = None, layout: str | None = None,
          timestamp: int | None = None, date: str | None = None) -> str | None:
    """Build every render of `doc`, or those named: None when all were
    built, else why one was not. With `timestamp`, each PDF says it was made
    then, so the same sources and tools make the same bytes."""
    renders = doc.renders(variant, layout)
    if not renders:
        return f"{doc.label} has nothing to build for {variant or 'any variant'} and {layout or 'any layout'}"
    templates = prepare(doc)
    for src, group in stage(doc, renders, date).items():
        if subprocess.call(curvenote("build", "--typst"), cwd=src) != 0:
            return f"curvenote build failed for {doc.label}"
        for r in group:
            typ = r.typst_source
            stamp = ["--creation-timestamp", str(timestamp)] if timestamp is not None else []
            if subprocess.call([typst, "compile", *typst_fonts(), *stamp, str(typ), str(r.output)]) != 0:
                return f"typst compile failed for {typ}"
            print(f"built {projects.shown(r.output)}")
    for r in renders:
        if r.spec.get("exporter") == "linkedin":
            node = need("node", "install Node.js (https://nodejs.org)")
            r.output.parent.mkdir(parents=True, exist_ok=True)
            with r.output.open("w", encoding="utf-8") as out:
                # In the doc's directory, so pub-plugin.mjs finds the repo's publets.
                if subprocess.call([node, str(templates / "linkedin-text.mjs"), str(r.source)],
                                   cwd=doc.path, stdout=out) != 0:
                    return f"the linkedin exporter failed for {r.source}"
            print(f"built {projects.shown(r.output)}")
    return None


def cmd_build(args: argparse.Namespace) -> int:
    if args.all == (args.name is not None):
        die("build takes a doc or a project, or --all for every doc here", 2)
    if args.all:
        return build_all()
    _, docs = target(args.name)
    if (args.variant or args.layout) and len(docs) != 1:
        die("--variant and --layout need one doc")
    typst = resolve_typst()
    timestamp = None
    if args.date:
        try:
            timestamp = versions.Approval("", args.date, "", "", "").timestamp
        except ValueError:
            die(f"--date {args.date} is not a date, YYYY-MM-DD", 2)
    for doc in docs:
        if failure := build(doc, typst, args.variant, args.layout, timestamp=timestamp, date=args.date):
            die(failure)
    return 0


def build_all() -> int:
    """Build every doc of every project here, going on past a failure so
    one run reports them all."""
    files = projects.find(projects.repo_root(Path.cwd()))
    if not files:
        die("no projects here: no project.yml in this repository")
    typst = resolve_typst()
    total, failed = 0, []
    for file in files:
        project, problems, _ = load_checked(file)
        if problems or not project:
            report(problems)
            total += 1
            failed.append(f"{projects.shown(file.parent)} (does not check)")
            continue
        for doc in project.docs:
            total += 1
            if failure := build(doc, typst):
                print(f"pubdoc: {failure}", file=sys.stderr)
                failed.append(doc.label)
    print(f"built {total - len(failed)} of {total} docs"
          + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


def cmd_open(args: argparse.Namespace) -> int:
    doc = one_doc(args.name)
    resolve_typst()
    prepare(doc)
    src = stage_site(doc)
    port = ["--port", args.port] if args.port else []
    os.chdir(src)
    command = curvenote("start", *port)
    os.execv(command[0], command)
    return 0  # pragma: no cover - execv does not return


def review_config(r: Render) -> dict:
    """review-builder's configuration for one render. Its Accept button runs
    approve, which prints the approved render's address in storage."""
    doc, out = r.doc, r.doc.path / BUILD
    watched = [f for d in [doc.path] + [doc.project.shared_dir(p) for p in doc.project.config["parts"]]
               if d and d.is_dir() for f in sorted(d.iterdir())
               if f.is_file() and f.suffix in (".md", ".yml", ".bib")]
    watched.append(doc.project.file)
    pubdoc = [sys.executable, "-m", "pubdoc"]
    return {
        "title": f"{doc.label}: {r.variant} {r.layout}",
        "watched_files": [os.path.relpath(f, out) for f in watched],
        "build_cmd": [*pubdoc, "build", str(doc.path), "--variant", r.variant, "--layout", r.layout],
        "pdf_path": str(r.output.relative_to(out)),
        "preview_dirname": str(Path("preview") / r.variant / r.layout),
        "commit_cmd": [*pubdoc, "approve", str(doc.path), "--variant", r.variant, "--show", r.layout],
    }


def cmd_preview(args: argparse.Namespace) -> int:
    r = pick(one_doc(args.name), args.variant, args.layout)
    out = r.doc.path / BUILD
    out.mkdir(exist_ok=True)
    write_if_changed(out / ".gitignore", IGNORE_ALL.encode())
    write_if_changed(out / "review-builder.yaml",
                     ("# Written by pubdoc preview: do not edit.\n"
                      + yaml.safe_dump(review_config(r), sort_keys=False)).encode())
    preview = need("review-builder-preview", "install review-builder: pipx install ~/git/review-builder")
    os.chdir(out)
    os.execv(preview, [preview, *([args.port] if args.port else [])])
    return 0  # pragma: no cover - execv does not return


def git(where: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True)
    if done.returncode != 0:
        die(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout.strip()


def approver(doc: Doc) -> str:
    """Who approves: $PUBDOC_APPROVER, else the GitHub login gh is signed in
    as. When the project names reviewers, it must be one of them."""
    who = os.environ.get("PUBDOC_APPROVER")
    if not who and shutil.which("gh"):
        done = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True)
        who = done.stdout.strip() if done.returncode == 0 else None
    if not who:
        die("cannot tell who approves: sign in with `gh auth login`, or set PUBDOC_APPROVER")
    reviewers = doc.project.config.get("roles", {}).get("reviewers")
    if reviewers and who not in reviewers:
        die(f"{who} is not one of {projects.shown(doc.project.file)}'s reviewers ({', '.join(reviewers)})")
    return who


def cmd_approve(args: argparse.Namespace) -> int:
    """Build, upload, sign and record a version of each variant asked for."""
    doc = one_doc(args.name)
    variants = [args.variant] if args.variant else doc.variants()
    for v in variants:
        if v not in doc.variants():
            die(f"{doc.label} has no variant {v} ({', '.join(doc.variants())})")
    conf = settings.of(doc.project)
    root = conf.root
    if not args.allow_dirty:
        dirty = git(root, "status", "--porcelain", "--untracked-files=all", "--",
                    str(doc.project.path), str(conf.corpus))
        if dirty:
            die(f"commit these first, so the version names the sources it was built from:\n{dirty}")
    for step in doc.review():
        for checker in step.get("automatic", []):
            if checker != "build" and not registry.CHECKERS[checker].implemented:
                print(f"note: checker {checker!r} is not implemented yet; approving without it")
    date = args.date or datetime.date.today().isoformat()
    approval = versions.Approval(approver=approver(doc), date=date, commit=git(root, "rev-parse", "HEAD"),
                                 rebuilt_from=args.rebuilt_from or "", pubdoc=version())
    typst = resolve_typst()
    shown = None
    for v in variants:
        renders = doc.renders(v)
        if failure := build(doc, typst, v, timestamp=approval.timestamp, date=approval.date):
            die(failure)
        try:
            entry = versions.publish(doc, v, approval, renders, doc_files(doc))
        except (versions.VersionError, storage.StorageError) as e:
            die(str(e))
        print(f"approved version {entry['version']} of {doc.label} ({v}): {entry['publet']}")
        for layout, render in entry["renders"].items():
            print(f"  {layout}: {render['url']}")
            if layout == args.show or (shown is None and not args.show):
                shown = render["url"]
    print(f"commit {projects.shown(versions.index_path(doc))} and {projects.shown(conf.corpus)}")
    # review-builder's Accept button links to the last line printed.
    if shown:
        print(shown)
    return 0


def cmd_versions(args: argparse.Namespace) -> int:
    doc = one_doc(args.name)
    index = versions.read_index(doc)
    if not index["versions"]:
        print(f"{doc.label} has no versions yet")
        return 0
    for entry in index["versions"]:
        rebuilt = f", rebuilt from {entry['rebuilt_from']}" if entry.get("rebuilt_from") else ""
        print(f"{entry['variant']} v{entry['version']}  {entry['approved']}  by {entry['approved_by']}"
              f"  {entry['publet']}{rebuilt}")
        for layout, render in entry["renders"].items():
            print(f"    {layout}: {render['url']}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    doc = one_doc(args.name)
    entries = [e for e in versions.read_index(doc)["versions"]
               if (not args.variant or e["variant"] == args.variant)
               and (args.version is None or int(e["version"]) == args.version)]
    if not entries:
        die(f"{doc.label} has no such version")
    entry = entries[0]
    layouts = [args.layout] if args.layout else list(entry["renders"])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for layout in layouts:
        render = entry["renders"].get(layout)
        if not render:
            die(f"version {entry['version']} of {doc.label} has no {layout} render "
                f"({', '.join(entry['renders'])})")
        name = Path(render["url"]).name
        try:
            target = storage.save(render["url"], render["sha256"],
                                  versions.tenant_base(settings.of(doc.project)), out / name)
        except storage.StorageError as e:
            die(str(e))
        print(target)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    files = projects.find(Path(args.path))
    problems, checked, corpora, seen = [], 0, set(), []
    for file in files:
        project, found, _ = load_checked(file)
        if not project:
            problems.extend(str(p) for p in found)
            continue
        seen.append(project)
        for doc in project.docs:
            if not versions.index_path(doc).is_file():
                continue
            corpus = settings.of(project).corpus
            try:
                if corpus not in corpora:
                    versions.verify_corpus(corpus)
                    corpora.add(corpus)
                problems.extend(versions.verify_doc(doc, args.remote))
            except versions.VersionError as e:
                problems.append(f"{doc.label}: {e}")
            checked += 1
    for corpus in sorted(corpora):
        signer = versions.lock(corpus).get("corpus", {}).get("key")
        trusted = next((settings.of(p).key for p in seen if settings.of(p).corpus == corpus), None)
        if not trusted:
            print(f"note: {projects.shown(corpus)} is signed by {signer}; no corpus.key names the key "
                  "to trust, so that one is accepted")
    notes = [p for p in problems if p.startswith("note: ")]
    problems = [p for p in problems if not p.startswith("note: ")]
    for note in notes:
        print(note)
    for problem in problems:
        print(f"pubdoc: {problem}", file=sys.stderr)
    if problems:
        return 1
    print(f"verified {checked} doc(s)' versions against {len(corpora)} signed corpus(es)"
          + (", and every render in storage" if args.remote else ""))
    return 0


def cmd_corpus(args: argparse.Namespace) -> int:
    project = None
    if args.project:
        file = Path(args.project) / projects.PROJECT_FILE
        if not file.is_file():
            die(f"{args.project} is not a project: it holds no {projects.PROJECT_FILE}")
        project = project_or_die(file)
        root = projects.repo_root(project.path).resolve()
    else:
        root = projects.repo_root(Path.cwd()).resolve()
    try:
        done = corpus.init(project, root, args.backup_name, args.bitwarden_project, not args.no_backup)
    except (corpus.CorpusError, versions.VersionError) as e:
        die(str(e))
    for line in done or ["nothing to do: the corpus, its key and its backup are in place"]:
        print(line)
    print("commit the corpus's corpus.json and the config naming its key, if either changed")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    try:
        report = compare.compare(Path(args.first), Path(args.second))
    except compare.CompareError as e:
        die(str(e))
    for line in report.lines():
        print(line)
    return 0 if report.same else 1


def cmd_linkedin(args: argparse.Namespace) -> int:
    source = Path(args.index)
    if not source.is_file():
        die(f"{args.index} does not exist")
    node = need("node", "install Node.js (https://nodejs.org)")
    with tempfile.TemporaryDirectory(prefix="pubdoc-") as scratch:
        script = install_templates(Path(scratch)) / "linkedin-text.mjs"
        return subprocess.call([node, str(script), str(source)])


NEW_PROJECT = """\
# A document project: see https://github.com/Sustenaut/pubdoc#document-projects
project: {name}
purpose: {purpose}
parts:
  main: {{required: true}}
variants:
  default: {{audience: Everyone}}
layouts:
  main-pdf: {{part: main, template: lapreprint-typst, format: pdf}}
review:
  - step: checks
    automatic: [build]
"""

NEW_DOC = """\
---
title: {name}
---

# Introduction

Write here.
"""


def cmd_new_project(args: argparse.Namespace) -> int:
    path = Path(args.path)
    name = path.resolve().name
    if (path / projects.PROJECT_FILE).exists():
        die(f"{args.path}/{projects.PROJECT_FILE} exists already")
    if not re.fullmatch(projects.NAME_PATTERN, name):
        die(f"{name!r} is not a project name: use lowercase letters, digits and hyphens")
    (path / "draft").mkdir(parents=True, exist_ok=True)
    (path / projects.PROJECT_FILE).write_text(
        NEW_PROJECT.format(name=name, purpose=args.purpose), encoding="utf-8")
    if not (path / "draft" / "main.md").exists():
        (path / "draft" / "main.md").write_text(NEW_DOC.format(name=name), encoding="utf-8")
    print(f"wrote {args.path}/{projects.PROJECT_FILE} and a first doc, {args.path}/draft/main.md")
    return 0


def launcher() -> str:
    return f"""#!/usr/bin/env bash
# Written by `pubdoc init`. It names no release: it runs the pubdoc that
# {PIN}, beside it, pins. Change that line, or let pubrules's nightly
# move it, to move this repository to another release.
#
# Run this repository's pubdoc from its root, or from anywhere through this
# script's path:
#
#   ./pubdoc check
#   ./pubdoc build job-applications/veriff
#
# uvx fetches that release's wheel once and keeps it in uv's cache; nothing
# is installed into the repository or the system.
set -euo pipefail

pin="$(dirname "${{BASH_SOURCE[0]}}")/{PIN}"
if [ ! -f "$pin" ]; then
  echo "pubdoc: no $pin, which pins the pubdoc ./pubdoc runs; run pubdoc init again" >&2
  exit 1
fi
# The requirement is named by the distribution: pubdocrules, or pubdoc for a
# release from before the name changed.
url="$(sed -n 's/^[A-Za-z0-9_.-]* @ //p' "$pin" | head -n 1)"
if [ -z "$url" ]; then
  echo "pubdoc: $pin has no line \"pubdocrules @ URL\"; run pubdoc init again" >&2
  exit 1
fi

if ! command -v uvx >/dev/null 2>&1; then
  echo "pubdoc: ./pubdoc runs pubdoc with uv, which is not installed: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 127
fi

exec uvx --from "$url" pubdoc "$@"
"""


def cmd_init(_: argparse.Namespace) -> int:
    release = version()
    path = Path(LAUNCHER)
    if path.is_dir():
        die(f"./{LAUNCHER} is a directory, such as an old pubdoc submodule; remove it first")
    path.write_text(launcher(), encoding="utf-8")
    path.chmod(0o755)
    Path(PIN).write_text(f"{DISTRIBUTION} @ {WHEEL_URL.format(version=release)}\n", encoding="utf-8")
    print(f"wrote ./{LAUNCHER}, which runs the pubdoc ./{PIN} pins: {release}")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pubdoc", description=__doc__.splitlines()[0])
    p.add_argument("--version", action="version", version=f"pubdoc {version()}")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def add(name, func, help_text, *params):
        cmd = sub.add_parser(name, help=help_text, description=help_text)
        for param, kwargs in params:
            cmd.add_argument(param, **kwargs)
        cmd.set_defaults(func=func)

    doc = ("name", {"help": "a doc's directory, <project>/<doc>"})
    where = ("path", {"nargs": "?", "default": ".",
                      "help": "where to look: every project.yml git knows of below it, "
                              "or the project it is in (default: here)"})
    variant = ("variant", {"nargs": "?", "help": "a variant; optional when only one is left"})
    layout = ("layout", {"nargs": "?", "help": "a PDF layout; optional when only one is left"})
    port = ("--port", {"help": "the port to serve on"})
    add("check", cmd_check, "check every project.yml and doc.yml: the schema, and every "
        "name they refer to", where)
    add("list", cmd_list, "the projects and their docs", where)
    add("variants", cmd_variants, "a doc's variants", doc)
    add("open", cmd_open, "a live Curvenote site of a doc", doc, port)
    add("build", cmd_build, "every variant x layout of a doc (or of each doc of a project) into "
        "<doc>/build/<variant>/<layout>.<ext>; --all builds every doc here, reporting each that fails",
        ("name", {"nargs": "?", "help": "a doc, <project>/<doc>, or a project"}),
        ("--all", {"action": "store_true", "help": "every doc of every project in this repository"}),
        ("--variant", {"help": "only this variant"}),
        ("--layout", {"help": "only this layout"}),
        ("--date", {"help": "the doc's date, YYYY-MM-DD, as approve gives it: printed by the template "
                    "unless a part sets its own, and the PDFs' creation time"}))
    add("preview", cmd_preview, "review-builder's watch, build and Accept loop over one PDF render",
        doc, variant, layout, port)
    add("approve", cmd_approve, "build each variant of a doc, upload its renders to storage, sign a version "
        "publet for it and record it in <doc>/versions/versions.yml", doc,
        ("--variant", {"help": "only this variant"}),
        ("--show", {"metavar": "LAYOUT", "help": "print this layout's address last, for review-builder"}),
        ("--date", {"help": "the approval date, YYYY-MM-DD (default: today)"}),
        ("--rebuilt-from", {"metavar": "COMMIT", "help": "the commit whose sources an earlier approved "
                            "version was built from, for one rebuilt to replace it"}),
        ("--allow-dirty", {"action": "store_true", "help": "approve with uncommitted changes"}))
    add("versions", cmd_versions, "a doc's versions, newest first", doc)
    add("fetch", cmd_fetch, "download a version's renders, checked against its publet", doc,
        ("version", {"nargs": "?", "type": int, "help": "a version number (default: the latest)"}),
        ("--variant", {"help": "this variant's versions"}),
        ("--layout", {"help": "only this layout"}),
        ("--out", {"default": ".", "help": "the directory to save into (default: here)"}))
    add("verify", cmd_verify, "check every versions.yml against its corpus's signed publets", where,
        ("--remote", {"action": "store_true", "help": "and that every render in storage has its checksum"}))
    add("corpus", cmd_corpus, "make the corpus versions are signed in, and its key, once (or rebuild its "
        "store around a key restored with pubsec signing-key restore), and back the key up",
        ("action", {"choices": ["init"], "help": "init: make what is missing"}),
        ("project", {"nargs": "?", "help": "a project that names its own corpus (default: the repository's)"}),
        ("--bitwarden-project", {"metavar": "ID", "help": "the Bitwarden project the key is backed up to, "
                                 "when pubrules.json does not declare the key yet"}),
        ("--backup-name", {"metavar": "NAME", "help": "the backup's name there, when not declared yet"}),
        ("--no-backup", {"action": "store_true", "help": "do not run pubsec signing-key backup"}))
    add("compare", cmd_compare, "whether two PDFs are the same document: pages, text, pixels",
        ("first", {"help": "a PDF"}), ("second", {"help": "another PDF"}))
    add("linkedin", cmd_linkedin, "a CV's plain-text export for LinkedIn",
        ("index", {"help": "the CV's Markdown file"}))
    add("init", cmd_init, f"write ./pubdoc and {PIN}, which pins this release for it to run with uvx")
    add("new-project", cmd_new_project, "start a document project: a project.yml and a first doc",
        ("path", {"help": "the project's directory; its name is the project's"}),
        ("--purpose", {"default": "Say what this project is for", "help": "the project's purpose"}))
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
