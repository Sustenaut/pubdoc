"""Document projects: finding them in a repository, loading and checking
their project.yml and doc.yml, and resolving which file holds each part.

A project is a directory holding a project.yml. Its docs are the
directories beside that file holding a doc.yml or a file for one of its
parts:

    <project>/project.yml
    <project>/shared/<name>/<part>.md       a shared part docs start from
    <project>/<doc>/<part>.md               a doc's part, MyST Markdown
    <project>/<doc>/<part>.<variant>.md     replaces <part>.md for that variant
    <project>/<doc>/doc.yml                 optional, only narrows project.yml
    <project>/<doc>/refs.bib                optional bibliography
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from . import registry

PROJECT_FILE = "project.yml"
DOC_FILE = "doc.yml"
SHARED = "shared"
BUILD = "build"
VERSIONS = "versions"
# Directories inside a project that are never docs.
NOT_DOCS = {SHARED, BUILD, VERSIONS, "node_modules"}
# Directories a search without git never enters.
SKIPPED = {BUILD, "node_modules", ".git", ".venv", "_build"}
NAME_PATTERN = "^[a-z0-9][a-z0-9-]*$"
TEMPLATE_PATTERN = "^(?:[a-z0-9][a-z0-9-]*|[^/].*/.*)$"
READERS = ("named", "signed-in", "public")  # narrowest first


@dataclass(frozen=True)
class Problem:
    path: Path
    message: str

    def __str__(self) -> str:
        return f"{shown(self.path)}: {self.message}"


def shown(path: Path) -> str:
    """A path as the user would type it: relative to here when it is below here."""
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve())) or "."
    except ValueError:
        return str(path)


@dataclass
class Doc:
    project: "Project"
    path: Path
    config: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def label(self) -> str:
        return shown(self.path)

    def variants(self) -> list[str]:
        everything = list(self.project.config["variants"])
        chosen = self.config.get("variants")
        return [v for v in everything if v in chosen] if chosen else everything

    def layouts(self) -> list[str]:
        everything = list(self.project.config["layouts"])
        chosen = self.config.get("layouts")
        return [layout for layout in everything if layout in chosen] if chosen else everything

    def review(self) -> list[dict]:
        return self.config.get("review", self.project.config.get("review", []))

    def publish(self) -> list[dict]:
        return self.config.get("publish", self.project.config.get("publish", []))

    def source(self, part: str, variant: str) -> Path | None:
        """The file that holds `part` for `variant`: the doc's own override,
        its own part, then the shared part's override and the shared part."""
        places = [self.path]
        if shared := self.project.shared_dir(part):
            places.append(shared)
        for place in places:
            for candidate in (place / f"{part}.{variant}.md", place / f"{part}.md"):
                if candidate.is_file():
                    return candidate
        return None

    def template(self, layout: str) -> str | None:
        """The template doc.yml's `templates` gives `layout`, as project.yml
        would name it: a name pubdoc carries, or a path relative to the
        project's directory (a doc.yml's path is relative to the doc's)."""
        template = self.config.get("templates", {}).get(layout)
        if not template or not is_path(template):
            return template
        relative = os.path.relpath((self.path / template).resolve(), self.project.path.resolve())
        return relative if "/" in relative else f"./{relative}"

    def layout_spec(self, layout: str) -> dict:
        """The project's `layout`, with the template doc.yml gives it, if any."""
        spec = self.project.config["layouts"][layout]
        template = self.template(layout)
        return {**spec, "template": template} if template else spec

    def renders(self, variant: str | None = None, layout: str | None = None) -> list["Render"]:
        """Every variant x layout this doc builds, or just those named; a
        layout whose (optional) part the doc does not supply is left out."""
        found = []
        for v in self.variants():
            if variant and v != variant:
                continue
            for name in self.layouts():
                if layout and name != layout:
                    continue
                spec = self.layout_spec(name)
                source = self.source(spec["part"], v)
                if source:
                    found.append(Render(self, v, name, spec, source))
        return found


@dataclass(frozen=True)
class Render:
    doc: Doc
    variant: str
    layout: str
    spec: dict
    source: Path

    @property
    def extension(self) -> str:
        return {"pdf": "pdf", "text": "txt", "html": "html"}[self.spec["format"]]

    @property
    def output(self) -> Path:
        return self.doc.path / BUILD / self.variant / f"{self.layout}.{self.extension}"

    @property
    def typst_source(self) -> Path:
        """Where Curvenote writes a template layout's Typst, in a directory of
        its own: a template's support files land beside it, and a layout named
        like one of them (lapreprint, beside lapreprint.typ) would otherwise
        overwrite it, or import itself."""
        return self.doc.path / BUILD / self.variant / self.layout / "main.typ"


@dataclass
class Project:
    path: Path
    config: dict
    docs: list[Doc] = field(default_factory=list)

    @property
    def file(self) -> Path:
        return self.path / PROJECT_FILE

    @property
    def name(self) -> str:
        return self.config.get("project", self.path.name)

    def template_dir(self, template: str) -> Path | None:
        """A local template's directory, or None for a template pubdoc carries."""
        return (self.path / template).resolve() if is_path(template) else None

    def shared_dir(self, part: str) -> Path | None:
        spec = self.config.get("parts", {}).get(part, {})
        return self.path / spec["starts-from"] if "starts-from" in spec else None


def is_path(template: str) -> bool:
    """A layout's template is a path in the repository when it holds a /,
    and the name of a template pubdoc carries when it does not."""
    return "/" in template


# Finding projects --------------------------------------------------------

def git_root(start: Path) -> Path | None:
    """The git work tree holding `start`, if it is in one."""
    done = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True)
    return Path(done.stdout.strip()).resolve() if done.returncode == 0 else None


def repo_root(start: Path) -> Path:
    """The git work tree holding `start`, else `start` itself."""
    return git_root(start) or start


def project_files(start: Path) -> list[Path]:
    """Every project.yml at or below `start`: the ones git tracks or would
    (git ls-files, so ignored build output never counts), or, outside a
    git work tree, every one on disk outside build output."""
    start = start.resolve()
    done = subprocess.run(["git", "-C", str(start), "ls-files", "-z", "--cached", "--others",
                           "--exclude-standard", "--", "."], capture_output=True, text=True)
    if done.returncode == 0:
        found = {start / line for line in done.stdout.split("\0")
                 if line == PROJECT_FILE or line.endswith("/" + PROJECT_FILE)}
        return sorted(path for path in found if path.is_file())
    found = []
    for here, dirs, files in os.walk(start):
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED and not d.startswith("."))
        if PROJECT_FILE in files:
            found.append(Path(here) / PROJECT_FILE)
    return sorted(found)


def enclosing_project(path: Path) -> Path | None:
    """The project.yml in `path` or the nearest directory above it."""
    for here in [path.resolve(), *path.resolve().parents]:
        if (here / PROJECT_FILE).is_file():
            return here / PROJECT_FILE
    return None


def find(start: Path) -> list[Path]:
    """The project files a command given `start` acts on: every one below
    it, else the one it is inside."""
    found = project_files(start)
    if not found and (inside := enclosing_project(start)):
        found = [inside]
    return found


# Loading -----------------------------------------------------------------

def read_yaml(path: Path, problems: list[Problem]) -> dict | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        problems.append(Problem(path, f"is not valid YAML: {e}"))
        return None
    if data is None:
        data = {}
    if not isinstance(data, dict):
        problems.append(Problem(path, "must be a YAML mapping"))
        return None
    return data


@cache
def validators() -> dict[str, Draft202012Validator]:
    schemas = {name: json.loads((resources.files("pubdoc") / "schema" / f"{name}.schema.json")
                                .read_text(encoding="utf-8"))
               for name in ("project", "doc", "pubdoc")}
    store = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values())
    return {name: Draft202012Validator(schema, registry=store) for name, schema in schemas.items()}


def schema_problems(kind: str, data: dict, path: Path) -> list[Problem]:
    errors = sorted(validators()[kind].iter_errors(data), key=lambda e: list(map(str, e.absolute_path)))
    return [Problem(path, describe(e)) for e in errors]


def describe(error) -> str:
    where = ".".join(str(p) for p in error.absolute_path)
    if error.validator == "oneOf":
        message = "needs a template or an exporter, and not both"
    elif error.validator == "anyOf":
        message = "needs automatic checkers, a human sign-off, or both"
    elif error.validator == "pattern" and error.validator_value == NAME_PATTERN:
        message = f"{error.instance!r} is not a name: use lowercase letters, digits and hyphens"
    elif error.validator == "pattern" and error.validator_value == TEMPLATE_PATTERN:
        message = (f"{error.instance!r} is neither a template name nor a path relative to the "
                   "project (a path holds a /, and does not start with one)")
    elif error.validator == "pattern" and str(error.validator_value).startswith("^shared/"):
        message = f"{error.instance!r} is not shared/<name>"
    elif error.validator == "propertyNames":
        message = f"{error.instance!r} is not a name: use lowercase letters, digits and hyphens"
    else:
        message = error.message
    return f"{where}: {message}" if where else message


def load(file: Path, problems: list[Problem]) -> Project | None:
    """The project in `file`, with its docs, or None when project.yml is
    unreadable or breaks the schema (those problems are added)."""
    data = read_yaml(file, problems)
    if data is None:
        return None
    found = schema_problems("project", data, file)
    if found:
        problems.extend(found)
        return None
    project = Project(file.parent.resolve(), data)
    parts = set(data["parts"])
    for child in sorted(project.path.iterdir()):
        if (not child.is_dir() or child.name in NOT_DOCS or child.name[0] in "._"
                or (child / PROJECT_FILE).exists()):
            continue
        if not ((child / DOC_FILE).is_file() or any(
                f.name.split(".")[0] in parts for f in child.glob("*.md"))):
            continue
        config = {}
        if (child / DOC_FILE).is_file():
            config = read_yaml(child / DOC_FILE, problems)
            if config is not None:
                if found := schema_problems("doc", config, child / DOC_FILE):
                    problems.extend(found)
                    config = None
            config = config or {}
        project.docs.append(Doc(project, child.resolve(), config))
    return project


# Checking ----------------------------------------------------------------

def missing(kind: str, name: str, known) -> str:
    return f"no {kind} {name!r} ({', '.join(sorted(known)) or 'none'})"


def check(project: Project) -> tuple[list[Problem], list[str]]:
    """Every cross-reference in a loaded project and its docs: problems,
    and notes about names pubdoc knows but does not implement yet."""
    problems: list[Problem] = []
    notes: set[str] = set()
    file, config = project.file, project.config
    parts, variants, layouts = config["parts"], config["variants"], config["layouts"]

    for part, spec in parts.items():
        if "starts-from" in spec:
            shared = project.path / spec["starts-from"]
            if not (shared / f"{part}.md").is_file():
                problems.append(Problem(file, f"parts.{part}.starts-from: no {spec['starts-from']}/{part}.md"))
            else:
                problems.extend(overrides(shared, {part}, variants))

    templates = registry.templates()
    for name, spec in layouts.items():
        where = f"layouts.{name}"
        if spec["part"] not in parts:
            problems.append(Problem(file, f"{where}.part: {missing('part', spec['part'], parts)}"))
        if "template" in spec and is_path(spec["template"]):
            if found := local_template_problem(project, spec["template"]):
                problems.append(Problem(file, f"{where}.template: {found}"))
            elif spec["format"] not in registry.TEMPLATE_FORMATS:
                problems.append(Problem(file, f"{where}.format: {spec['template']} makes "
                                        f"{', '.join(registry.TEMPLATE_FORMATS)}, not {spec['format']}"))
        elif "template" in spec and spec["template"] not in templates:
            problems.append(Problem(file, f"{where}.template: {missing('template', spec['template'], templates)}"))
        elif "exporter" in spec and spec["exporter"] not in registry.EXPORTERS:
            problems.append(Problem(file, f"{where}.exporter: "
                                    f"{missing('exporter', spec['exporter'], registry.EXPORTERS)}"))
        elif spec["format"] not in registry.formats(spec):
            maker = spec.get("template") or spec.get("exporter")
            problems.append(Problem(file, f"{where}.format: {maker} makes "
                                    f"{', '.join(registry.formats(spec))}, not {spec['format']}"))

    reviewers = config.get("roles", {}).get("reviewers", [])
    problems.extend(review_problems(file, "review", config.get("review", []), reviewers, notes))
    for i, entry in enumerate(config.get("publish", [])):
        problems.extend(publication_problems(file, f"publish[{i}]", entry, layouts, variants, notes))

    for doc in project.docs:
        problems.extend(doc_problems(doc, notes))
    return problems, sorted(notes)


def local_template_problem(project: Project, template: str) -> str | None:
    """Why a local template directory cannot be built with, if it cannot:
    it must be inside the repository (outside a git work tree, anywhere), hold a template.yml (without one,
    Curvenote takes the path for the name of a template to download) and
    be a Typst template, the kind pubdoc builds."""
    path = project.template_dir(template)
    root = git_root(project.path)
    if root and not path.is_relative_to(root):
        return f"{template} is outside the repository ({shown(root)})"
    if not path.is_dir():
        return f"no directory {shown(path)}"
    spec = path / "template.yml"
    if not spec.is_file():
        return (f"{shown(path)} has no template.yml, which Curvenote needs "
                "to take a directory as a template")
    try:
        kind = (yaml.safe_load(spec.read_text(encoding="utf-8")) or {}).get("kind")
    except (yaml.YAMLError, AttributeError):
        return f"{shown(spec)} is not a YAML mapping"
    if kind != "typst":
        return f"{shown(spec)} is a {kind or 'kindless'} template; pubdoc builds Typst templates (kind: typst)"
    return None


def overrides(where: Path, parts, variants) -> list[Problem]:
    """A <part>.<x>.md whose x is no variant: most likely a typo."""
    found = []
    for f in sorted(where.glob("*.*.md")):
        part, variant = f.name.split(".")[:2]
        if part in parts and variant not in variants:
            found.append(Problem(f, missing("variant", variant, variants)))
    return found


def review_problems(file: Path, where: str, steps: list[dict], reviewers, notes: set[str]) -> list[Problem]:
    found, seen = [], set()
    for i, step in enumerate(steps):
        here = f"{where}[{i}]"
        if step["step"] in seen:
            found.append(Problem(file, f"{here}.step: {step['step']!r} is named twice"))
        seen.add(step["step"])
        for checker in step.get("automatic", []):
            if checker not in registry.CHECKERS:
                found.append(Problem(file, f"{here}.automatic: {missing('checker', checker, registry.CHECKERS)}"))
            elif not registry.CHECKERS[checker].implemented:
                notes.add(f"checker {checker!r} is not implemented yet: a later pubdoc runs it")
        wanted = step.get("human", {}).get("reviewers", 0)
        if wanted > len(reviewers):
            found.append(Problem(file, f"{here}.human: needs {wanted} reviewers, "
                                 f"and roles.reviewers names {len(reviewers)}"))
    return found


def publication_problems(file: Path, where: str, entry: dict, layouts, variants,
                         notes: set[str]) -> list[Problem]:
    found = []
    if entry["place"] not in registry.PLACES:
        found.append(Problem(file, f"{where}.place: {missing('place', entry['place'], registry.PLACES)}"))
    elif not registry.PLACES[entry["place"]].implemented:
        notes.add(f"place {entry['place']!r} is not implemented yet: a later pubdoc publishes there")
    for layout in entry["layouts"]:
        if layout not in layouts:
            found.append(Problem(file, f"{where}.layouts: {missing('layout', layout, layouts)}"))
    for variant in entry.get("variants", []):
        if variant not in variants:
            found.append(Problem(file, f"{where}.variants: {missing('variant', variant, variants)}"))
    return found


def doc_problems(doc: Doc, notes: set[str]) -> list[Problem]:
    config = doc.project.config
    found = overrides(doc.path, config["parts"], config["variants"])
    file = doc.path / DOC_FILE
    for key, everything in (("variants", config["variants"]), ("layouts", config["layouts"])):
        for name in doc.config.get(key, []):
            if name not in everything:
                found.append(Problem(file, f"{key}: {missing(key[:-1], name, everything)} in project.yml"))
    found.extend(doc_template_problems(doc, file))
    if "review" in doc.config:
        reviewers = config.get("roles", {}).get("reviewers", [])
        found.extend(review_problems(file, "review", doc.config["review"], reviewers, notes))
        found.extend(narrower_review(file, config.get("review", []), doc.config["review"]))
    if "publish" in doc.config:
        for i, entry in enumerate(doc.config["publish"]):
            here = f"publish[{i}]"
            found.extend(publication_problems(file, here, entry, doc.layouts(), doc.variants(), notes))
            found.extend(narrower_publication(file, here, entry, config.get("publish", []), config["variants"]))

    # A part is required of a doc only when one of its layouts renders it: a
    # doc whose doc.yml narrows its layouts to a CV's needs no letter.
    rendered = {config["layouts"][name].get("part") for name in doc.layouts()}
    for part, spec in config["parts"].items():
        if not spec["required"] or part not in rendered:
            continue
        for variant in doc.variants():
            if not doc.source(part, variant):
                start = f", and shared part {spec['starts-from']} has none" if "starts-from" in spec else ""
                found.append(Problem(doc.path, f"no {part}.md or {part}.{variant}.md for required part "
                                     f"{part!r} in variant {variant!r}{start}"))
    return found


def doc_template_problems(doc: Doc, file: Path) -> list[Problem]:
    """A doc.yml's `templates` may give another template only to a layout the
    doc keeps that a project template renders, and it must be one that
    layout's project.yml entry could name."""
    found = []
    layouts = doc.project.config["layouts"]
    for layout, given in doc.config.get("templates", {}).items():
        where = f"templates.{layout}"
        if layout not in doc.layouts():
            found.append(Problem(file, f"{where}: {missing('layout', layout, doc.layouts())} this doc keeps"))
            continue
        if "template" not in layouts[layout]:
            found.append(Problem(file, f"{where}: {layout} is made by an exporter, not a template"))
            continue
        template = doc.template(layout)
        if is_path(template):
            if problem := local_template_problem(doc.project, template):
                if problem.startswith(f"{template} "):
                    # Named as the doc.yml gives it, not as the project would.
                    problem = given + problem[len(template):]
                found.append(Problem(file, f"{where}: {problem}"))
        elif template not in registry.templates():
            found.append(Problem(file, f"{where}: {missing('template', given, registry.templates())}"))
    return found


def narrower_review(file: Path, project_steps: list[dict], doc_steps: list[dict]) -> list[Problem]:
    """A doc keeps every project review step, in order, and may only add
    checkers, reviewers or steps of its own."""
    found = []
    names = [step["step"] for step in doc_steps]
    position = -1
    for step in project_steps:
        name = step["step"]
        if name not in names:
            found.append(Problem(file, f"review: drops the project's review step {name!r}"))
            continue
        if names.index(name) < position:
            found.append(Problem(file, f"review: moves the project's review step {name!r} before an earlier one"))
        position = max(position, names.index(name))
        mine = doc_steps[names.index(name)]
        if dropped := set(step.get("automatic", [])) - set(mine.get("automatic", [])):
            found.append(Problem(file, f"review: step {name!r} drops checkers {', '.join(sorted(dropped))}"))
        wanted = step.get("human", {}).get("reviewers", 0)
        if mine.get("human", {}).get("reviewers", 0) < wanted:
            found.append(Problem(file, f"review: step {name!r} needs {wanted} human reviewers in project.yml"))
    return found


def narrower_publication(file: Path, where: str, entry: dict, project_entries: list[dict],
                         all_variants) -> list[Problem]:
    """A doc publishes only what a project publication to the same place
    already allows, to no wider readers."""
    candidates = [p for p in project_entries if p["place"] == entry["place"]]
    if not candidates:
        return [Problem(file, f"{where}.place: project.yml does not publish to {entry['place']!r}")]
    reasons = []
    for p in candidates:
        why = []
        if extra := set(entry["layouts"]) - set(p["layouts"]):
            why.append(f"layouts {', '.join(sorted(extra))}")
        if extra := set(entry.get("variants", all_variants)) - set(p.get("variants", all_variants)):
            why.append(f"variants {', '.join(sorted(extra))}")
        if READERS.index(entry["readers"]) > READERS.index(p["readers"]):
            why.append(f"{entry['readers']} readers (project.yml: {p['readers']})")
        if not why:
            return []
        reasons.append(" and ".join(why))
    return [Problem(file, f"{where}: widens what project.yml publishes to {entry['place']!r}: {reasons[0]}")]
