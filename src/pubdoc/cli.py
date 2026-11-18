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

from . import projects
from .projects import BUILD, VERSIONS, Doc, Problem, Project, Render

CURVENOTE_VERSION = "0.17.2"
LAUNCHER = "pubdoc"
WHEEL_URL = "https://github.com/Sustenaut/pubdoc/releases/download/v{version}/pubdoc-{version}-py3-none-any.whl"
# The launcher's pin, one requirement line beside it, where pubrules's nightly
# moves it to pubdoc's latest release like any other release wheel pin.
PIN = "requirements-pubdoc.txt"
# Inside a doc's build/: pubdoc's templates, and the staged sources Curvenote builds.
TEMPLATES, SOURCES = "templates", "src"
IGNORE_ALL = "# Written by pubdoc: everything here is built, never committed.\n*\n"


def version() -> str:
    try:
        return metadata.version("pubdoc")
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
    for file in files:
        project, found, said = load_checked(file)
        problems.extend(found)
        notes.update(said)
        docs += len(project.docs) if project else 0
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


def stage(doc: Doc, renders: list[Render]) -> Path:
    """Copy the doc's parts, and the shared parts it starts from, into
    build/src/ as they sit in the project, so a part's MyST include of
    ../shared/... still resolves, and write the MyST configuration that
    exports each Typst render there."""
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
    plugins = [str(Path("..") / TEMPLATES / "annotations.mjs")]
    # pub-plugin.mjs needs the repository's publets-local.json, found upwards.
    if any((d / "publets-local.json").is_file() for d in [doc.path, *doc.path.parents]):
        plugins.insert(0, str(Path("..") / TEMPLATES / "pub-plugin.mjs"))
    exports = [{"format": "typst",
                "article": str(r.source.relative_to(project.path)),
                "template": str(Path("..") / TEMPLATES / r.spec["template"]),
                "output": str(Path("..") / r.variant / f"{r.layout}.typ")}
               for r in renders if "template" in r.spec]
    myst = {"version": 1, "project": {"plugins": plugins, "exports": exports}, "site": {"nav": []}}
    wanted[Path("myst.yml")] = ("# Written by pubdoc from project.yml: do not edit.\n"
                                + yaml.safe_dump(myst, sort_keys=False)).encode()
    return mirror(wanted, doc.path / BUILD / SOURCES)


def prepare(doc: Doc) -> Path:
    out = doc.path / BUILD
    write_if_changed(out / ".gitignore", IGNORE_ALL.encode())
    return install_templates(out / TEMPLATES)


def build(doc: Doc, typst: str, variant: str | None = None, layout: str | None = None) -> str | None:
    """Build every render of `doc`, or those named: None when all were
    built, else why one was not."""
    renders = doc.renders(variant, layout)
    if not renders:
        return f"{doc.label} has nothing to build for {variant or 'any variant'} and {layout or 'any layout'}"
    templates = prepare(doc)
    src = stage(doc, renders)
    typst_renders = [r for r in renders if "template" in r.spec]
    if typst_renders:
        if subprocess.call(curvenote("build", "--typst"), cwd=src) != 0:
            return f"curvenote build failed for {doc.label}"
        for r in typst_renders:
            typ = r.output.with_suffix(".typ")
            if subprocess.call([typst, "compile", str(typ), str(r.output)]) != 0:
                return f"typst compile failed for {typ}"
            print(f"built {projects.shown(r.output)}")
    for r in renders:
        if r.spec.get("exporter") == "linkedin":
            node = need("node", "install Node.js (https://nodejs.org)")
            staged = src / r.source.relative_to(doc.project.path)
            r.output.parent.mkdir(parents=True, exist_ok=True)
            with r.output.open("w", encoding="utf-8") as out:
                # In the doc's directory, so pub-plugin.mjs finds the repo's publets.
                if subprocess.call([node, str(templates / "linkedin-text.mjs"), str(staged)],
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
    for doc in docs:
        if failure := build(doc, typst, args.variant, args.layout):
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
    src = stage(doc, doc.renders())
    port = ["--port", args.port] if args.port else []
    os.chdir(src)
    command = curvenote("start", *port)
    os.execv(command[0], command)
    return 0  # pragma: no cover - execv does not return


def review_config(r: Render) -> dict:
    """review-builder's configuration for one render. review-builder serves
    only what is inside its directory, build/, so build/versions links to
    the doc's versions/ for the Accept button's link to resolve."""
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
        "commit_cmd": [*pubdoc, "approve", str(doc.path), r.variant, r.layout],
    }


def cmd_preview(args: argparse.Namespace) -> int:
    r = pick(one_doc(args.name), args.variant, args.layout)
    out = r.doc.path / BUILD
    out.mkdir(exist_ok=True)
    write_if_changed(out / ".gitignore", IGNORE_ALL.encode())
    write_if_changed(out / "review-builder.yaml",
                     ("# Written by pubdoc preview: do not edit.\n"
                      + yaml.safe_dump(review_config(r), sort_keys=False)).encode())
    link = out / VERSIONS
    if not link.is_symlink():
        link.symlink_to(Path("..") / VERSIONS, target_is_directory=True)
    preview = need("review-builder-preview", "install review-builder: pipx install ~/git/review-builder")
    os.chdir(out)
    os.execv(preview, [preview, *([args.port] if args.port else [])])
    return 0  # pragma: no cover - execv does not return


def cmd_approve(args: argparse.Namespace) -> int:
    r = pick(one_doc(args.name), args.variant, args.layout)
    if not r.output.is_file():
        die(f"{projects.shown(r.output)} not built yet; run: pubdoc build {r.doc.label}")
    name = f"{r.doc.name}_{r.variant}_{r.layout}_{datetime.date.today().isoformat()}.pdf"
    (r.doc.path / VERSIONS).mkdir(exist_ok=True)
    shutil.copyfile(r.output, r.doc.path / VERSIONS / name)
    # review-builder's Accept button reads this path, relative to build/,
    # where versions/ links to the doc's; it holds from the doc's directory too.
    print(Path(VERSIONS) / name)
    return 0


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
url="$(sed -n 's/^pubdoc @ //p' "$pin" | head -n 1)"
if [ -z "$url" ]; then
  echo "pubdoc: $pin has no line \"pubdoc @ URL\"; run pubdoc init again" >&2
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
    Path(PIN).write_text(f"pubdoc @ {WHEEL_URL.format(version=release)}\n", encoding="utf-8")
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
        ("--layout", {"help": "only this layout"}))
    add("preview", cmd_preview, "review-builder's watch, build and Accept loop over one PDF render",
        doc, variant, layout, port)
    add("approve", cmd_approve, "copy one PDF render into the doc's versions/, dated", doc, variant, layout)
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
