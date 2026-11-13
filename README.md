# pubdoc

Build, preview and approve documents written in MyST Markdown as Typst
PDFs, with review and approval in
[review-builder](https://github.com/Sustenaut/review-builder). pubdoc
carries a small template library and two MyST plugins, so a document
repository holds only its content.

- `cv-sidebar`: a CV and cover-letter template with rotated section
  labels in a left sidebar.
- `lapreprint-typst`: an upstream preprint template.
- `charged-ieee`: a thin wrapper around `@preview/charged-ieee`.
- `pub-plugin.mjs`: the `{pub}` role, which links through the
  repository's publet registry.
- `annotations.mjs`: verdict-coded note markers for fact-checks.

[docs/design.md](docs/design.md) explains how each piece works and the
MyST and Typst behaviour it works around.

## Requirements

- [uv](https://docs.astral.sh/uv/), which runs pubdoc's wheel.
- Node.js, for `npx`, which fetches the pinned Curvenote version.
- A `typst` binary on `PATH`, or a build at `~/git/typst/target/release/typst`.
  pubdoc stops with install instructions if it finds neither.
- review-builder, for `preview` and the Accept button:
  `pipx install ~/git/review-builder`.

## Set up a repository

From the repository's root, run a release once:

```bash
uvx --from https://github.com/Sustenaut/pubdoc/releases/download/v0.1.0/pubdoc-0.1.0-py3-none-any.whl pubdoc init
```

That writes `requirements-pubdoc.txt`, one line pinning that release's
wheel:

```
pubdoc @ https://github.com/Sustenaut/pubdoc/releases/download/v0.1.0/pubdoc-0.1.0-py3-none-any.whl
```

and `./pubdoc`, which names no release: it runs the one that file pins with
uvx, from the repository's root or through its path from anywhere (as
review-builder runs `../../pubdoc`). It also adds `/.pubdoc/` to
`.gitignore`. Commit all three. To move to another release, change the
line, or let pubkit's nightly move it: that line is a release wheel pin in
a requirements file, which the nightly moves to pubdoc's latest release
like any other. Running another release's `pubdoc init` the same way
still works too.

The repository then looks like this:

```
<repo>/
├── pubdoc                      the launcher
├── requirements-pubdoc.txt     the pubdoc release the launcher runs
├── publets/                    one Markdown file per linked concept
├── publets-local.json          short name -> publet id, shared by every doc
├── .gitignore
└── <name>/                     one document
    ├── index.md                MyST source, the real content
    ├── myst.yml                which templates and plugins it builds with
    ├── refs.bib                optional bibliography
    └── <variant>/              one directory per export, e.g. cv/
        ├── review-builder.yaml
        └── versions/           approved, dated PDFs (committed)
```

A document's `myst.yml` names the templates in `.pubdoc/templates/`, where
pubdoc copies them before each build:

```yaml
version: 1
project:
  title: Jane Doe
  plugins:
    - ../.pubdoc/templates/pub-plugin.mjs
  exports:
    - format: typst
      template: ../.pubdoc/templates/cv-sidebar
      output: cv/main.typ
site:
  title: Jane Doe - CV
  nav: []
```

Each variant's `review-builder.yaml` calls the launcher; review-builder
runs these from `<name>/<variant>/`:

```yaml
title: "Jane Doe CV"
watched_files: ["../index.md", "../myst.yml"]
build_cmd: ["../../pubdoc", "build", ".."]
pdf_path: "main.pdf"
default_port: 8746
commit_cmd: ["../../pubdoc", "approve", "..", "cv"]
version_name: "Jane_Doe_CV"
```

A repository that uses `{pub}` needs `publets-local.json` and `publets/`
at its root; `{}` and an empty directory are fine to start with.

`build` writes `main.typ`, `main.pdf` and template support files into each
variant directory, and Curvenote writes `_build/` into the document's.
These `.gitignore` lines keep them out and keep the approved PDFs in:

```gitignore
.preview/
node_modules/
/*/_build/
/*/*/main.typ
/*/*/main.pdf
/*/*/main.bib
/*/*/myst-imports.typ
/*/*/files/
/*/*/cv-sidebar.typ
/*/*/lapreprint.typ
/*/*/frontmatter.typ
/*/*/LICENSE
*.pdf
!*/*/versions/*.pdf
```

## Usage

Run from the repository's root:

```bash
./pubdoc list                              # the documents here
./pubdoc variants <name>                   # a document's variants
./pubdoc open <name> [port]                # a live Curvenote site of it
./pubdoc build <name>                      # every variant's main.typ and main.pdf
./pubdoc build --all                       # every document's, reporting each that fails
./pubdoc preview <name> [variant] [port]   # review-builder's loop, with Accept
./pubdoc approve <name> [variant]          # copy main.pdf into versions/, dated
./pubdoc linkedin <name>/index.md          # a CV as plain text for LinkedIn
```

`<name>` is a path to a document directory, so `./pubdoc build cv` builds
`cv/cv/main.pdf`. `./pubdoc build --all` builds every document `list`
finds, each with all its variants, goes on past one that fails, prints
`built N of M documents` (naming the ones that failed) and exits non-zero
if any did. `preview` and `approve` act on one variant; leave it out
when the document has only one, so `./pubdoc approve cv` approves
`cv/cv/main.pdf`. Accept in the preview page runs `approve`; commit the
new `versions/*.pdf` afterwards.

## Adding a document

Copy an existing document's `myst.yml` and a variant's
`review-builder.yaml`, write `index.md`, give each `review-builder.yaml`
its own `title`, `default_port` and variant name in `commit_cmd`, and run
`./pubdoc build <name>` once. `approve` names the approved copy
`<doc-dir>_<variant>_<date>.pdf` unless the variant's
`review-builder.yaml` sets `version_name: "..."`.

One document can build through several templates: list one export per
template in `myst.yml`, each with its own output directory.

```yaml
project:
  exports:
    - format: typst
      template: ../.pubdoc/templates/lapreprint-typst
      output: lapreprint/main.typ
    - format: typst
      template: ../.pubdoc/templates/charged-ieee
      output: ieee/main.typ
```

`build` makes all of them in one pass; `preview` and `approve` then need
the variant (output directory) as their second argument.

## Links with `{pub}`

Every link in a document goes through the `{pub}` role:
``{pub}`python` `` looks up `python` in `publets-local.json`, gets an id,
and links to the publet with that id in `publets/`:

```markdown
---
id: 6
url: https://www.python.org
text: Python
---

One-paragraph synopsis, used as the link's hover title on the web.
```

Add a publet by writing a new file with the next unused id and adding
`"<short-name>": <id>` to `publets-local.json`. A trailing `+` gives the
plural: ``{pub}`llm+` `` renders "LLMs".

## Developing

```bash
make venv          # hash-locked environment, this checkout installed editable
make functional    # the Gherkin suite in tests/features/
```

The suite runs pubdoc against stand-ins for npx and typst, so it needs
neither. To try a change on a real document repository, build the wheel
(`make wheel`) and run it there with `uvx --from dist/pubdoc-*.whl pubdoc build <name>`.

A template or plugin change reaches a repository only when that
repository moves to a release that has it. Rebuild every document there
(`./pubdoc build --all`) and compare the generated `main.typ` before committing the move.

### Releasing

With [pubrel](https://github.com/Sustenaut/pubrel), like the other
Sustenaut packages. A pull request that changes `src/` or `pyproject.toml`
records what it changes (`pubrel add fixed "…"`, or `internal` for no
release), and CI checks it. To release, run `pubrel prepare` on an
up-to-date main in a checkout holding the release key (`corpus/.publet`,
gitignored): it sets `version` in `pyproject.toml`, signs the release and
opens its pull request. Merging that tags `vX.Y.Z` and makes the release,
and `wheel.yml` then attaches `pubdoc-X.Y.Z-py3-none-any.whl`.

## License

Apache-2.0, except `src/pubdoc/templates/lapreprint-typst/`, which keeps
its own upstream MIT license.
