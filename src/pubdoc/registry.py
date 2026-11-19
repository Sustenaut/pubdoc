"""The names a project.yml may use: pubdoc's templates, exporters,
checkers and places.

A project only picks and configures these; what each one does lives in
pubdoc. Checkers and places are declared before they are implemented, so a
project can name the review steps and places it will use: `pubdoc check`
says which are not implemented yet, and does not fail for them.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True)
class Plugin:
    summary: str
    implemented: bool = False


# Exporters render a part without a template: name -> the formats it makes.
EXPORTERS: dict[str, tuple[str, ...]] = {
    "linkedin": ("text",),
}

# Every template pubdoc carries is a Typst template: it makes a PDF.
TEMPLATE_FORMATS = ("pdf",)

CHECKERS: dict[str, Plugin] = {
    "build": Plugin("every variant and layout of the doc builds"),
    "links": Plugin("every link resolves"),
    "spelling": Plugin("no unknown words"),
    "private-info": Plugin("no private information in a public render"),
}

PLACES: dict[str, Plugin] = {
    "storage": Plugin("storage.sustenaut.eu, with a link in the doc's versions"),
    "pub": Plugin("pub.sustenaut.eu"),
}


def templates() -> list[str]:
    """The templates this release carries: each a directory with a template.yml."""
    root = resources.files("pubdoc") / "templates"
    return sorted(child.name for child in root.iterdir()
                  if child.is_dir() and (child / "template.yml").is_file())


def formats(layout: dict) -> tuple[str, ...]:
    """The formats a layout's template or exporter can make."""
    if "template" in layout:
        return TEMPLATE_FORMATS
    return EXPORTERS.get(layout.get("exporter", ""), ())
