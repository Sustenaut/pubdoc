"""pubdoc's command line: build, preview and approve the documents in a repo.

A document is a directory holding a myst.yml, directly under the repo's
root. `build` and `open` first copy this release's templates and plugins
into `.pubdoc/templates/` beside the documents, where each myst.yml points
(`../.pubdoc/templates/cv-sidebar`), then run the pinned Curvenote in the
document's directory and `typst compile` on each export it lists.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
from importlib import metadata, resources
from pathlib import Path

CURVENOTE_VERSION = "0.17.2"
TEMPLATES_DIR = Path(".pubdoc") / "templates"
LAUNCHER = "pubdoc"
WHEEL_URL = "https://github.com/Sustenaut/pubdoc/releases/download/v{version}/pubdoc-{version}-py3-none-any.whl"


def version() -> str:
    try:
        return metadata.version("pubdoc")
    except metadata.PackageNotFoundError:  # a checkout run without installing
        return "0+unknown"


def die(message: str, code: int = 1) -> None:
    print(f"pubdoc: {message}", file=sys.stderr)
    sys.exit(code)


def doc_dir(name: str) -> Path:
    path = Path(name)
    if not (path / "myst.yml").is_file():
        die(f"{name} has no myst.yml")
    return path.resolve()


def variant_dir(doc: Path, variant: str) -> Path:
    path = doc / variant
    if not (path / "review-builder.yaml").is_file():
        die(f"{doc.name}/{variant} has no review-builder.yaml")
    return path


def yaml_value(path: Path, key: str) -> list[str]:
    """Every `key: value` line's value, quotes dropped: a plain scan, not a YAML parser."""
    pattern = re.compile(rf"^\s*{key}:\s*[\"']?([^\"']*?)[\"']?\s*$")
    return [m.group(1) for line in path.read_text(encoding="utf-8").splitlines()
            if (m := pattern.match(line))]


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


def install_templates(root: Path) -> Path:
    """Make root/.pubdoc/templates/ hold exactly this release's templates,
    rewriting only the files that differ, so a running preview sees no churn."""
    target = root / TEMPLATES_DIR
    wanted: dict[Path, bytes] = {}
    stack = [(resources.files("pubdoc") / "templates", Path())]
    while stack:
        node, prefix = stack.pop()
        for child in node.iterdir():
            if child.is_dir():
                stack.append((child, prefix / child.name))
            else:
                wanted[prefix / child.name] = child.read_bytes()
    for rel, data in wanted.items():
        path = target / rel
        if not path.is_file() or path.read_bytes() != data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    for path in sorted(target.rglob("*"), reverse=True):
        rel = path.relative_to(target)
        if path.is_file() and rel not in wanted:
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    return target


def curvenote(*args: str) -> list[str]:
    return [need("npx", "install Node.js (https://nodejs.org)"), "--yes",
            f"curvenote@{CURVENOTE_VERSION}", *args]


def cmd_list(_: argparse.Namespace) -> int:
    for myst in sorted(Path().glob("*/myst.yml")):
        print(myst.parent.name)
    return 0


def cmd_variants(args: argparse.Namespace) -> int:
    for spec in sorted(doc_dir(args.name).glob("*/review-builder.yaml")):
        print(spec.parent.name)
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    doc = doc_dir(args.name)
    resolve_typst()
    install_templates(doc.parent)
    port = ["--port", args.port] if args.port else []
    os.chdir(doc)
    command = curvenote("start", *port)
    os.execv(command[0], command)
    return 0  # pragma: no cover - execv does not return


def cmd_build(args: argparse.Namespace) -> int:
    doc = doc_dir(args.name)
    typst = resolve_typst()
    install_templates(doc.parent)
    outputs = yaml_value(doc / "myst.yml", "output")
    if not outputs:
        die(f"{doc}/myst.yml lists no exports with an output:")
    if subprocess.call(curvenote("build", "--typst"), cwd=doc) != 0:
        die(f"curvenote build failed for {doc}")
    for out in outputs:
        if subprocess.call([typst, "compile", str(doc / out)]) != 0:
            die(f"typst compile failed for {doc / out}")
        print(f"built {doc / Path(out).with_suffix('.pdf')}")
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    vdir = variant_dir(doc_dir(args.name), args.variant)
    preview = need("review-builder-preview", "install review-builder: pipx install ~/git/review-builder")
    os.chdir(vdir)
    os.execv(preview, [preview, *([args.port] if args.port else [])])
    return 0  # pragma: no cover - execv does not return


def cmd_approve(args: argparse.Namespace) -> int:
    doc = doc_dir(args.name)
    vdir = variant_dir(doc, args.variant)
    built = vdir / "main.pdf"
    if not built.is_file():
        die(f"{vdir}/main.pdf not built yet; run: pubdoc build {args.name}")
    names = yaml_value(vdir / "review-builder.yaml", "version_name")
    name = names[0] if names and names[0] else f"{doc.name}_{args.variant}"
    target = Path("versions") / f"{name}_{datetime.date.today().isoformat()}.pdf"
    (vdir / "versions").mkdir(exist_ok=True)
    shutil.copyfile(built, vdir / target)
    # review-builder's Accept button reads this path, relative to the variant dir.
    print(target)
    return 0


def cmd_linkedin(args: argparse.Namespace) -> int:
    source = Path(args.index)
    if not source.is_file():
        die(f"{args.index} does not exist")
    script = install_templates(source.resolve().parent.parent) / "linkedin-text.mjs"
    node = need("node", "install Node.js (https://nodejs.org)")
    return subprocess.call([node, str(script), str(source)])


def launcher(release: str) -> str:
    url = WHEEL_URL.format(version=release)
    return f"""#!/usr/bin/env bash
# Written by `pubdoc init` from pubdoc {release}; run `pubdoc init` from
# another release to move this repository to it.
#
# Run this repository's pubdoc from its root:
#
#   ./pubdoc build cv
#
# uvx fetches that release's wheel once and keeps it in uv's cache; nothing
# is installed into the repository or the system.
set -euo pipefail

if ! command -v uvx >/dev/null 2>&1; then
  echo "pubdoc: ./pubdoc runs pubdoc {release} with uv, which is not installed: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 127
fi

exec uvx --from "{url}" pubdoc "$@"
"""


def cmd_init(_: argparse.Namespace) -> int:
    release = version()
    path = Path(LAUNCHER)
    if path.is_dir():
        die(f"./{LAUNCHER} is a directory, such as an old pubdoc submodule; remove it first")
    path.write_text(launcher(release), encoding="utf-8")
    path.chmod(0o755)
    print(f"wrote ./{LAUNCHER}, which runs pubdoc {release}")
    ignore = Path(".gitignore")
    text = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    if "/.pubdoc/" not in text.splitlines():
        gap = "" if not text else "\n" if text.endswith("\n") else "\n\n"
        with ignore.open("a", encoding="utf-8") as f:
            f.write(f"{gap}# pubdoc's templates, copied in by every build.\n/.pubdoc/\n")
        print("ignored /.pubdoc/ (in .gitignore)")
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

    name = ("name", {"help": "a document directory: one holding a myst.yml"})
    variant = ("variant", {"help": "a variant directory of it: one holding a review-builder.yaml"})
    port = ("port", {"nargs": "?", "help": "the port to serve on"})
    add("list", cmd_list, "the documents here")
    add("variants", cmd_variants, "a document's variants", name)
    add("open", cmd_open, "a live Curvenote site of a document", name, port)
    add("build", cmd_build, "every export in a document's myst.yml, to main.typ and main.pdf", name)
    add("preview", cmd_preview, "review-builder's watch, build and Accept loop over one variant", name, variant, port)
    add("approve", cmd_approve, "copy a variant's main.pdf into its versions/, dated", name, variant)
    add("linkedin", cmd_linkedin, "a CV's plain-text export for LinkedIn",
        ("index", {"help": "the CV's index.md"}))
    add("init", cmd_init, "write ./pubdoc, which runs this release with uvx, and ignore .pubdoc/")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
