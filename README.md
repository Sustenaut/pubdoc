# pubdoc

Check, build, preview and approve document projects written in MyST
Markdown, as Typst PDFs and other formats, with review and approval in
[review-builder](https://github.com/Sustenaut/review-builder). A project
is one `project.yml` naming the parts a purpose needs (a letter and a
CV), the audiences each is shaped for, the layouts each is rendered in,
its review steps and where it publishes; pubdoc owns its schema and
carries a small template library and two MyST plugins, so a repository
holds only content and configuration.

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
uvx, from the repository's root or through its path from anywhere
(`../pubdoc check`). Commit both. Builds write only into each doc's
`build/`, which ignores itself, so nothing needs adding to `.gitignore`.
To move to another release, change the line, or let pubrules's nightly move it: that line is a release wheel pin in
a requirements file, which the nightly moves to pubdoc's latest release
like any other. Running another release's `pubdoc init` the same way
still works too.

## Document projects

A project is a directory holding a `project.yml`, anywhere in a
repository: pubdoc finds every one git knows of. Its docs are the
directories beside that file; each is one use of the project (one job
application) and holds a MyST file per part:

```
<repo>/
├── pubdoc                      the launcher
├── requirements-pubdoc.txt     the pubdoc release the launcher runs
├── publets/                    one Markdown file per linked concept
├── publets-local.json          short name -> publet id, shared by every doc
└── job-applications/           one project
    ├── project.yml
    ├── shared/base-cv/
    │   ├── cv.md               a shared part: docs start from it
    │   └── cv.research.md      ...and its research variant
    └── veriff/                 one doc
        ├── letter.md           a part, MyST Markdown
        ├── letter.research.md  replaces letter.md for the research variant
        ├── doc.yml             optional: only narrows project.yml
        ├── refs.bib            optional bibliography
        ├── versions/           approved, dated PDFs (committed)
        └── build/              everything pubdoc builds (ignores itself)
```

```yaml
# job-applications/project.yml
project: job-applications
purpose: Win software engineering roles
parts:
  letter: {required: true}
  cv: {required: true, starts-from: shared/base-cv}
  webpage: {required: false}
roles:
  contributors: [schryer]
  reviewers: [schryer]
variants:
  engineering: {audience: Hiring managers for software roles}
  research: {audience: Research and R&D groups}
layouts:
  letter-pdf: {part: letter, template: cv-sidebar, format: pdf}
  cv-pdf: {part: cv, template: cv-sidebar, format: pdf}
  cv-linkedin: {part: cv, exporter: linkedin, format: text}
review:
  - step: checks
    automatic: [build, links, spelling, private-info]
  - step: approval
    human: {reviewers: 1}
publish:
  - place: storage
    layouts: [letter-pdf, cv-pdf, cv-linkedin]
    readers: named
```

- `parts`: what each doc supplies. A `required` part must resolve for
  every variant of every doc. `starts-from: shared/<name>` names a shared
  part, `shared/<name>/<part>.md`.
- `variants`: audiences. A file `<part>.<variant>.md` replaces
  `<part>.md` for that variant, in a doc or in a shared part.
- `layouts`: one part rendered by a template pubdoc carries
  (`cv-sidebar`, `lapreprint-typst`, `charged-ieee`; each makes a PDF) or
  by an exporter (`linkedin`, plain text), in a `format`: `pdf`, `text` or
  `html`.
- `review`: ordered steps; each has automatic checkers (`build`, `links`,
  `spelling`, `private-info`), a human sign-off by a number of
  `roles.reviewers`, or both.
- `publish`: which layouts (and variants; all when left out) go to which
  place (`storage`, `pub`), for which readers: `public`, `signed-in` or
  `named`.

Checker and place names come from pubdoc's registry and are checked
against it; none runs yet (later releases add review and publishing), and
`pubdoc check` says so in a note without failing. The schema ships in the
package as `src/pubdoc/schema/project.schema.json` and `doc.schema.json`.

For each variant, a part comes from the first of: the doc's
`<part>.<variant>.md`, the doc's `<part>.md`, the shared part's
`<part>.<variant>.md`, the shared part's `<part>.md`. A doc that supplies
no file of a part with `starts-from` uses the shared part as it is; a
doc's own part may also include it with MyST's
`` ```{include} ../shared/base-cv/cv.md `` ``.

A `doc.yml` can only narrow its project:

```yaml
# job-applications/globex/doc.yml
variants: [engineering]           # a subset of the project's
layouts: [letter-pdf, cv-pdf]     # a subset of the project's
publish:                          # each within one project publication
  - {place: storage, layouts: [cv-pdf], readers: named}
review:                           # every project step, in order; may add
  - {step: checks, automatic: [build, links, spelling, private-info]}
  - {step: approval, human: {reviewers: 1}}
```

It may publish to fewer places, layouts, variants and readers (`named`
is narrower than `signed-in`, which is narrower than `public`), and it may
add checkers, reviewers and steps, but never drop or loosen a project
review step. [examples/job-applications/](examples/job-applications/) is
a complete project with two docs.

## Usage

Run from anywhere in the repository; paths are relative to where you are:

```bash
./pubdoc check [path]                                   # every project.yml and doc.yml below path
./pubdoc list [path]                                    # the projects and their docs
./pubdoc build <project>/<doc>                          # every variant x layout of a doc
./pubdoc build <project>                                # ...of each of its docs
./pubdoc build --all                                    # every doc here, reporting each that fails
./pubdoc build <project>/<doc> --variant V --layout L   # one render
./pubdoc preview <project>/<doc> [variant] [layout] [--port N]
./pubdoc approve <project>/<doc> [variant] [layout]     # copy a PDF into versions/, dated
./pubdoc open <project>/<doc> [--port N]                # a live Curvenote site of it
./pubdoc variants <project>/<doc>                       # its variants, as doc.yml narrows them
./pubdoc new-project <path> [--purpose "..."]           # a project.yml and a first doc
./pubdoc linkedin <file.md>                             # a CV as plain text for LinkedIn
```

`check` validates each `project.yml` and `doc.yml` against the schema,
then every name they refer to: a layout's part, template, exporter and
format, each publication's layouts, variants and place, each review step's
checkers and reviewer count, each `starts-from`, each doc's required parts
for each of its variants, variant overrides that name no variant, and that
each `doc.yml` only narrows. It prints every problem as `path: what is
wrong` and exits non-zero if there is one. It finds projects with `git
ls-files` (tracked and untracked, not ignored), so it works in any
repository; outside a git work tree it searches the disk. `build` checks
the project first and refuses one with problems.

`build` writes `<doc>/build/<variant>/<layout>.<ext>`: `.pdf` for a
template layout (with its `.typ` source beside it), `.txt` for the
LinkedIn exporter. `build --all` goes on past a doc that fails, prints
`built N of M docs` (naming the ones that failed) and exits non-zero if
any did.

`preview` and `approve` act on one PDF render; leave out the variant and
layout when the doc has only one. `preview` writes review-builder's
configuration into `<doc>/build/review-builder.yaml` and runs it there;
its Accept button runs `approve`, which copies the PDF into
`<doc>/versions/<doc>_<variant>_<layout>_<date>.pdf` and prints that path.
Commit the new `versions/*.pdf` afterwards.

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
repository moves to a release that has it. Rebuild every doc there
(`./pubdoc build --all`) and compare the generated `build/*/*.typ` before
committing the move.

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
