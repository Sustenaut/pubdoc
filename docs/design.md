# How pubdoc works

The design notes behind pubdoc's command, templates and plugins, and the
MyST and Typst behaviour they work around. Paths are written as a
consumer repository sees them: `./pubdoc` is the launcher `pubdoc init`
writes, and `../.pubdoc/templates/...` is where each `myst.yml` finds the
templates the command copies in. In this repository the templates live in
`src/pubdoc/templates/`.

## Why a separate tool instead of extending `review-builder` itself

`review-builder`'s own `AGENTS.md` states its design doctrine explicitly:
"stay generic" — no plugin system, no document-type abstraction. The only
extension point it offers is a project-supplied `build_cmd`/`commit_cmd` in
a `review-builder.yaml`. pubdoc is exactly that: build logic for consumer projects, like
`cv-builder`, that supplies MyST/Curvenote- and Typst-specific build logic
of its own, without review-builder needing to know anything about either.
Do not add MyST/Curvenote-specific code to `review-builder` itself for this
reason — it belongs in pubdoc.

## The `pubdoc` command

Single dispatcher: `./pubdoc {list|variants|open|build|preview|approve} <name> [variant] [port]`.
It replaced an older standalone Rust tool, also called `pubdoc`, whose
source was lost, and then a shell script, `scripts/doc`; it does the same
steps. Before `open` and `build` it copies this release's templates into
`.pubdoc/templates/` beside the documents (gitignored), which is what
every `myst.yml` points at.
`build` runs `npx --yes curvenote@<pinned> build --typst` in the doc
directory, then `typst compile` on each `output:` listed in `myst.yml`.
It resolves `<name>`/`<variant>` against whatever directory it's invoked
from, the same way `git` resolves paths, rather than against its own
location. `review-builder.yaml`'s `build_cmd`/`commit_cmd` run with cwd =
`<name>/<variant>/`, so they invoke it as
`["../../pubdoc", "build", ".."]` /
`["../../pubdoc", "approve", "..", "<variant>"]` — `..` is the doc
directory relative to that cwd, and `../../pubdoc` holds because
every doc sits directly under the consumer repo's root, next to the
`./pubdoc` launcher.

`open` and `build` operate on a whole *document* (no variant argument):
`build` regenerates every variant listed in that doc's `myst.yml` in one
`curvenote build --typst` call, since Curvenote itself builds every
configured export together. `preview` and `approve` operate on one
*variant* at a time, since review-builder only ever shows one built
artifact — three review "moments" in total:

1. `./pubdoc open <name>` — review the MyST project itself as a live
   Curvenote site (content, headings, footnote rendering,
   cross-references). Same for every variant, since it's the same
   `index.md`.
2. `./pubdoc preview <name> <variant>` — review-builder's watch/build/serve
   loop, showing that variant's Typst-built PDF, rebuilding (all variants,
   though only one is shown) on every save. The green **Accept** button in
   that preview **is the approval step**.
3. Accepting runs `./pubdoc approve <name> <variant>`, which copies that
   variant's just-built PDF into `<name>/<variant>/versions/` with today's
   date and prints that path (the convention review-builder's Accept
   button expects — see `review_builder/server.py`'s commit endpoint in
   the review-builder repo). The filename defaults to
   `<doc-dir>_<variant>_<date>.pdf` (e.g. `cv`'s own `cv/` variant would
   otherwise be `cv_cv_2026-09-22.pdf`); add `version_name: "..."` to that
   variant's `review-builder.yaml` to override the `<doc-dir>_<variant>`
   part instead — `cv/cv/`'s carries `version_name: "David_Schryer_CV"`
   so its approved snapshots read `David_Schryer_CV_2026-09-22.pdf`.
   `pubdoc` parses that one line itself (a plain line scan, not a
   real YAML parser), so it needs to be a literal `version_name: value`
   or `version_name: "value"`
   line, not a multi-line or nested YAML structure.

**`versions/` lives inside each variant directory, not shared at the doc
level** — this looks redundant (variant is already in the containing path)
but is load-bearing: review-builder serves files via Python's
`SimpleHTTPRequestHandler(directory=root)`, which is sandboxed to `root`
(wherever that variant's `review-builder.yaml` lives) and will 404 on any
`../` path no matter what `commit_cmd` prints. `versions/` has to be
reachable *within* that root for the Accept button's link to actually
resolve. Found this the hard way building the second variant here — it's
not a design preference, it's a hard constraint of the tool.

## The template library

Two different kinds of thing can live under `templates/<name>/`:

1. **A genuine upstream jtex/MyST template** (e.g. `lapreprint-typst`) —
   just the template's own files (`template.yml`, `template.typ`, and
   whatever else it needs), copied in as-is. `template.yml`'s presence is
   what makes `myst-templates` recognize a *local path* as a real template
   at all (see the local-path pitfall below) — without it, a valid-looking
   directory is silently treated as a template *name* to look up remotely
   instead, which fails with a confusing 404.
2. **A thin local wrapper around a plain Typst Universe package** that was
   never published as a jtex template — see `templates/charged-ieee/` for
   the pattern. `@preview/charged-ieee` only exposes an `ieee.with(...)`
   Typst function (scaffold it yourself with `typst init @preview/charged-ieee
   <dir>` to see its real usage and check `~/.cache/typst/packages/preview/charged-ieee/<version>/lib.typ`
   for the exact parameter names/defaults — don't guess). The wrapper is
   just a `template.yml` (declaring which MyST frontmatter fields it needs
   — `doc:`/`parts:`/`options:`, same shape as any jtex template) plus a
   `template.typ` that imports the package and calls its show rule with
   Nunjucks-substituted frontmatter values around `[-CONTENT-]`. This
   pattern generalizes: *any* Typst Universe package can be adapted into
   the library this way, not just ones someone else has already
   MyST-wrapped.
3. **A genuine from-scratch template with no upstream package at all** —
   see `templates/cv-sidebar/`, used by `cv/` and `cover-letter/`. It
   defines its own layout function (`cv-sidebar.typ`, imported by
   `template.typ` and invoked via `#show: cv-sidebar.with(title: ...)`),
   replicating `cv-builder`'s original hand-built CSS design: a rotated
   (-90°) vertical section-label in the page's left margin above every
   top-level heading. Two non-obvious Typst facts this depended on:
   - MyST's typst exporter maps Markdown `#` (H1) to Typst heading
     **level 2**, not 1 — level 1 is reserved for the document title
     itself. A `show heading.where(level: 1):` rule silently matches
     nothing; use `level: 2`.
   - Positioning each label at its own heading's vertical position (not
     collapsed to the wrong spot) does **not** work via the standard
     Typst "margin note" idiom — `context { let pos = here().position();
     place(top + left, dy: pos.y, rotate(...)) }` — despite that being
     the documented, generally-correct pattern for this kind of thing.
     Two rounds of debugging here were misled by low-resolution renders
     that *looked* right at a glance; placing a small marker square at
     the literal captured `pos.y` proved it lands well past the true
     heading position, consistently, on every heading after the first,
     both with and without the decorative `v()`/`line()` calls before it,
     with or without a wrapping `#show: fn.with()` function, and whether
     or not the body has a bullet list. Root cause not fully understood —
     not worth chasing further given the fix below is simple and
     empirically solid (verified the same way: marker squares at the
     exact position used, checked against a zoomed high-DPI render, not
     just eyeballed at normal size).
     The fix that actually works: skip `context`/`here()` entirely. An
     **unaligned** `place()` (no alignment argument, just `dx`/`dy`)
     tracks the current flow position automatically and correctly, even
     with `rotate()` — but *only* when it is the sole content of a
     zero-size `box(width: 0pt, height: 0pt, place(...))`, with nothing
     else in the box and nothing wrapping the text passed to `rotate()`
     beyond a bare `upper(it.body)`. Any additional layer — an inner box
     (auto-width or explicit), a scoped `show " ": ...` rule, extracting
     `it.body.text` to string-replace spaces — reintroduces the same
     mis-tracking, for reasons equally unclear. The one real cost of this
     minimal form: the zero-width box forces Typst to wrap a multi-word
     heading at its space onto stacked lines (e.g. "Vendor Management"
     renders as "VENDOR" over "MANAGEMENT") rather than one line — not
     fixable without breaking positioning again, and accepted as-is since
     it only affects two of the cv's seven headings and reads fine
     for a vertical sidebar label.

**A real pitfall to know about**: `myst-templates`' template resolution
(`resolveInputs` in `myst-templates/dist/download.js`) checks
`fs.existsSync(opts.template)` and then, for a directory, specifically
`fs.existsSync(join(opts.template, 'template.yml'))` — if that's missing,
it silently falls through to treating your path *string* as a template
*name* and queries `api.curvenote.com/templates/<your path>`, which 404s
with an unhelpful error. If a local template path stops working, check
`template.yml` is actually present before suspecting anything else.

Despite general MyST docs implying template IDs can be pinned to a
version, this CLI (`curvenote`/`myst-cli` as of the version pinned in
`src/pubdoc/cli.py`'s `CURVENOTE_VERSION`) has no such syntax, and `myst templates` only supports
`list`/`download` — no "install a local path under a name" step. Local
*paths* are the only real pinning mechanism available; that's why the
library is structured this way rather than referencing templates by ID.

## Central publet registry: `templates/pub-plugin.mjs` + `publets/` + `publets-local.json`

The plugin is pubdoc's; `publets/` and `publets-local.json` are content
and live at the root of each consumer repo. The plugin finds them by
walking up from the doc directory to the first `publets-local.json`, so a
consumer that lists `pub-plugin.mjs` must have one (an empty `{}` and an
empty `publets/` are fine). Ids are unique within one consumer repo.

A technology mention like Python or React typically appears many times
across one doc, and again across every *other* doc that also mentions
it — plain `[text](url)` duplicates the URL every time, and Markdown's
own reference-link syntax (`[text][key]` + a `[key]: url` definition)
only dedupes *within one file*, since the definition has to be repeated
in each document that wants it.

The fix here is a custom MyST role, `{pub}`, wired up exactly like
`annotations.mjs` below (`project.plugins` in `myst.yml`): any doc that
lists `../.pubdoc/templates/pub-plugin.mjs` gets access to it. A **publet** is
one concept — a technology, standard, or company — captured as its own
small Markdown file under the consumer's `publets/`: flat frontmatter
(`id`, `url`, `text`, optional `plural`) plus a one-paragraph synopsis
as the body, e.g. `publets/python.md`:

```markdown
---
id: 6
url: http://www.python.org
text: Python
---

Python is a dynamically typed, high-level programming language widely
used for scripting, data tooling, and backend services.
```

Resolving a `{pub}` call is two steps, not one flat lookup:

```markdown
{pub}`python`
*{pub}`react`*
**{pub}`python`**
{pub}`llm+`
```

1. `publets-local.json` maps the short name used in a call
   (`"python"`) to a publet's `id` (a plain integer, e.g. `6`) — this is
   **one shared file for the whole consumer repo**, not one per document,
   so `cv/` and `cover-letter/` both resolve `python` through the same
   local namespace.
2. That `id` looks up the actual publet in the consumer's `publets/` (by its
   frontmatter `id`, not by filename).

The `id` is the one thing that's never reused once assigned, and never
renumbered — it's what makes "the Python publet" a stable reference
independent of what any document calls it, what file it lives in, or
what its display text says today. Renaming a publet's file, or changing
its `text`/`url`, never requires touching `publets-local.json` or any
document that references it.

A trailing `+` on the local name requests the plural ("LLM" → "LLMs") —
computed from the publet's own `plural` field if it sets one (for
irregular plurals), else `text` with an "s" appended, either way with no
second publet and no duplicated id/url. An earlier version of this
mechanism (then called `{reglink}`, reading one flat `links.json`) also
had a general `key|custom text` override for arbitrary display-text
substitution; removed once converting every link in `cv/index.md`
(including every single-use one, not just the repeated ones) turned up
no use of it that wasn't actually a plural — `+` covers the real need
with one predictable, narrow rule instead of an open-ended escape hatch.

**Every link goes through this, not just the repeated ones.** The
obvious reason to reach for a registry is deduping a link used several
times, but a one-off link (a client's site, a single paper) is in there
too — the point isn't only deduplication, it's that every link in a
document uses the *same* mechanism and the *same* naming convention,
rather than some links being `{pub}` calls and others plain
`[text](url)`. Local names in `publets-local.json` are derived
predictably from the display text (lowercase, spaces and slashes to
hyphens — "Stack Overflow Teams" → `stack-overflow-teams`, "CI/CD" →
`ci-cd`), not abbreviated, so the name for any given link is guessable
without checking the registry first. A genuinely different link needs a
distinguishing suffix on the local name, not a display-text override -
the two "Java" links in `cv/index.md` (the language's own site vs. its
Wikipedia article, linked from different contexts) are `java` and
`java-wiki`, not one name used twice with different override text.

An unresolvable local name renders as visible broken text (`[[pub:
unknown local name "..."]]`) in every export rather than silently
vanishing, so a typo is obvious at a glance instead of shipping a
missing link.

**The synopsis becomes the link's `title`.** `{pub}` resolves to a
plain `{type: 'link', url, title, children}` node — the exact same
mdast shape a literal `` [text](url "title") `` produces, confirmed by
inspecting the compiled output — not a new node type needing its own
per-format renderer (unlike the `verdictMark` nodes in
`annotations.mjs`, which *do* need one, since there's no native "verdict
marker" node to fall back to). That means it needs no Typst-specific or
HTML-specific handling anywhere: confirmed directly for both outputs
this repo actually produces — a real `curvenote build --html` of `cv/`
showed the synopsis present as the link node's `title` field in the
built site's content JSON (rendered as a hover tooltip by the Curvenote
theme), and the generated `main.typ` is unaffected since Typst's
exporter has no use for an mdast `title` field and silently ignores it —
no visible change in the PDF.

**Why a role, not a bigger rewrite.** A fancier approach - standing up a
separate AST-transform compiler on top of unified/remark, or moving to a
different source format like AsciiDoc specifically to get this kind of
indirection - would be solving a problem this repo doesn't have: MyST's
own plugin mechanism (which *is* the unified/remark/mdast ecosystem
under a friendlier API - confirmed by how directly `annotations.mjs`
manipulates mdast node `type`/`children` fields) already extends to
exactly this, with no new toolchain and no abandoning the Typst/PDF
pipeline this project has already put significant work into tuning.

**What this doesn't solve.** Confluence isn't a MyST/curvenote export
target at all today (only Typst and HTML are), independent of this
plugin - adding one would be a real, separate undertaking (Confluence
expects its own storage format or ADF, not plain HTML/Markdown) whether
or not a publet registry exists. Nothing about `{pub}` blocks that
later, since it still just produces an ordinary link node that any future
exporter would handle the same way as every other link in the doc - but
it doesn't deliver it either.

**Adding a new publet**: create `publets/<name>.md` with the
next unused `id` (check the highest `id` across existing files — there's
no autoincrement, it's a plain text file you write by hand), then add
`"<local-name>": <id>` to `publets-local.json`.

## LinkedIn text export: `templates/linkedin-text.mjs`

LinkedIn has no write API for profiles and renders no Markdown or links in
most fields, so this is a plain-text export for copy-pasting by hand:

```
./pubdoc linkedin cv/index.md > linkedin.txt
```

It reads the same `index.md` the PDF is built from and resolves `{pub}`
tags through `pub-plugin.mjs`'s exported `resolvePub()`, so a publet
rename or retarget shows up here too. Output: a deduplicated skills list
(every `{pub}` in `# Technical Skills` plus every "Key technologies"
line, singular names, most-used first, with a count against LinkedIn's
50-skill limit), then one block per `# Employment` entry — company, title,
dates, that role's skills, and its bullets as the description with a
character count against LinkedIn's 2000 limit. Vendor Management,
Education, and Summary are deliberately not exported.

Two quirks: company/title are split at the **last** comma in the bold
header, so an entry with no title (e.g. "Tallinn University of Technology,
Department of Chemical Engineering") comes out with the department as its
title — fix by hand when pasting. An unknown `{pub}` name aborts the
script rather than printing a broken marker. The output file is not
tracked; redirect it somewhere outside the repo or delete it afterwards.

## Regenerating a doc's Typst output

If a variant's `main.typ`/`main.pdf` look wrong, the fix belongs in
`index.md` (or `myst.yml`'s frontmatter — title, authors, abstract part,
keywords, etc.), never in `main.typ` directly. Two format-conversion
quirks worth knowing about, hit and fixed while building the first doc
here — both are facts about how MyST's typst exporter behaves, not
specific to any one template, so they'll recur in future docs:

- **Footnotes are page-anchored (Typst `#footnote[...]`) and repeated
  references get fully re-expanded, not cross-referenced.** This project
  no longer uses Markdown footnote syntax (`[^1]`) at all — see "Annotation
  scheme" below for why and what to use instead — but if a future doc ever
  reaches for it anyway: MyST's typst exporter puts every footnote at the
  bottom of the page it's referenced on (there's no way to collect them at
  the end of the document short of not using footnotes), and if `[^1]` is
  used twice (directly, or indirectly — e.g. one footnote's own body
  writing "Same as [^1]") it emits a brand-new `#footnote[...]` with the
  *entire* original body copied in, every time, rather than a lightweight
  back-reference — this alone bloated an early draft from 4 pages to 6.
- **Embedded literal double quotes in string frontmatter fields (e.g.
  `title`) break the generated Typst.** jtex doesn't escape them when
  substituting into a Typst string literal, so `title: "... \"Foo\" ..."`
  produces a `.typ` file with an unescaped internal `"`, which fails to
  compile. Use typographic quotes (`“Foo”`) instead — reads better in the
  PDF anyway. Note `charged-ieee`'s `title`/`abstract` are Typst *content*
  (`[...]`), not strings, so this specific bug doesn't apply there — but
  markup-special characters (`_`, `*`, `#`, `$`) in those fields would be
  interpreted as Typst markup instead, which is the content-vs-string
  version of the same underlying issue (jtex does raw text substitution,
  no escaping either way).
- **A pair of literal `$` in body text is parsed as inline math**, and
  math mode spaces out every letter of any plain word inside it (each
  becomes its own italic single-character "variable") — e.g. `$15000 per
  annum (B) University of Toronto Fellowship – $1200` silently mangled
  the entire stretch between the two `$` into letter-spaced garbage, with
  no build error or warning to flag it. Escape any literal dollar amount
  as `\$15000` in `index.md`. Only *paired* `$...$` on the same line (or
  across the surrounding text) triggers this — a single unpaired `$`
  (e.g. one dollar figure with no second `$` anywhere nearby) passes
  through fine, which is why this is easy to miss until a doc happens to
  mention two dollar amounts in the same section.
- **`~sub~`/`^sup^` inline Markdown syntax for sub/superscript is not
  enabled** in this MyST version — it's silently emitted as literal text
  (`$tilde$`/escaped carets), not parsed. Use the `{sub}`/`{sup}` roles
  instead — `` H{sub}`2`{sup}`18`O `` — confirmed these compile to Typst's
  own `#sub[...]`/`#super[...]`.
- **A forced page break** can be inserted with the inline
  `` {raw:typst}`#pagebreak()` `` role (see "Annotation scheme" below for
  more on `{raw:typst}` generally) — it degrades to nothing in non-Typst
  exports. Confirmed working, but consider whether you actually want it
  before adding one: Typst's own automatic pagination often already
  breaks in a reasonable place, and a manual break can just as easily
  strand a nearly-empty page instead of improving anything (this is what
  happened on a first attempt in `cv/index.md`, later removed).

## Annotation scheme: verdict-coded Notes, Sources, and Bibliography, not footnotes

For a review/fact-check style document (the pattern `killer-whale-menopause-factcheck`
established, reuse it rather than reinventing per doc). Four pieces:

**1. In-text markers use a custom plugin**, `templates/annotations.mjs`
(shared library, like the Typst templates — reference it from any doc's
`myst.yml`: `project.plugins: [../.pubdoc/templates/annotations.mjs]`). It
defines four inline roles, one per verdict, each taking a short, stable
**name** — not a number — as its only argument:

```
The essay claims X {partial}`sons-mortality`, restated later {partial}`sons-mortality` again.
```

Numbers are assigned automatically, in the order names first appear in
the document, by a `document`-stage transform in that same plugin —
never typed by hand. Reusing a name a second time (as above) resolves to
the *same* number and does **not** duplicate anything, unlike footnotes
— this is exactly why footnotes were dropped in favor of this scheme in
the first place, not only for the page-vs-end placement. Inserting,
removing, or reordering notes never requires renumbering anything;
that's the whole point of doing this as a plugin instead of hand-writing
markers (an earlier version of this doc did exactly that — see the git
history around the "verdict-coded annotations" commits — and every edit
risked drifting the marker number, the anchor, and the heading text out
of sync with each other).

Each name needs exactly one matching heading elsewhere in the document
(normally under `## Notes`), labeled `(note-<name>)=` and containing the
literal text `Note` — the plugin rewrites that text to `Note <n>` using
the same number it assigned the marker, so the two always agree:

```
(note-sons-mortality)=
### Note

:::{warning} Verdict: Partially true — "the exact claim being checked"
**Source:** [@bibkey1]; [@bibkey2].

**Observation:** why this verdict.
:::
```

**Verdict → role → admonition type → color** (the admonition types are
MyST built-ins — they auto-generate Typst helper functions in
`myst-imports.typ`, styled consistently, no custom code needed, and it's
the same four colors on the Curvenote site; the roles are ours, defined
in `annotations.mjs`, and pick a matching icon colored to the *exact*
shade the admonition's own left-border stroke uses,
`{color}.darken(20%)`, via `{raw:typst}` — see "How the plugin colors
the icon" below):
- True → `{true}` role → `:::{tip}` admonition → green, icon `✓`
- Partially true → `{partial}` role → `:::{warning}` admonition → yellow, icon `◪`
- False → `{false}` role → `:::{danger}` admonition → red, icon `✗`
- Neutral / clarifying, no truth value → `{neutral}` role → `:::{note}` admonition → blue, icon `☐`

A note's `**Source:**` line is *only* bibliography citations, nothing
else — the actual detail about what was drawn from that source belongs
in the Sources section (next), not repeated in every note that cites it.
A note with no formal citation (general knowledge, not from a specific
paper) just omits the `**Source:**` line entirely.

**How the plugin colors the icon** (only matters if you're touching
`annotations.mjs` itself, not for authoring a doc): each role's `run()`
returns a placeholder node (`{type: 'verdictMark', verdict, name}`); the
transform walks the whole tree once to assign numbers by first
appearance, then a second time to replace each placeholder in place with
a real `link` node whose children are `[` + a `{type: 'raw', lang:
'typst', typst: '#text(fill: ...)[...]'}` node + `]` — that `raw` node
type is exactly what MyST's own `{raw:typst}` role produces (confirmed
by inspecting `myst-roles/dist/raw.js`), so this is using a documented,
stable MyST mechanism, not reaching into internals. `{raw:typst}`
content is invisible in every export format except Typst (documented
behavior) — verified directly (built `--html` and inspected the output)
that a marker degrades gracefully to a plain, still-clickable `[1]` with
no icon on the Curvenote site, rather than breaking or leaving a gap.
Since the PDF is the actual deliverable of this repo, that trade-off is
accepted deliberately. (Also tried Pandoc-style `[text]{.class}`
attribute spans as a way to additionally drive real CSS color on the
HTML side — not supported by this MyST version, confirmed empirically:
renders as literal escaped text.) A first attempt at this used full-color
emoji (✅⚠️❌🔵) needing no styling at all, since the color is baked into
the glyph — replaced with plain checkbox-style symbols (✓◪✗☐) that read
cleaner in print but need the `text(fill: ...)` wrapping since they carry
no inherent color.

**3. A "## Sources" section**, one entry per bibliography key, carries the
detail that used to be repeated inline in every note citing it — which
specific figures/findings/quotes were drawn from that source, across all
the notes that cite it, plus any secondary corroborating coverage. Typst's
`bibliography()` doesn't render a BibTeX `note`/`annotate` field (tested
directly — it's silently dropped by both the `apa` and `ieee` citation
styles bundled with Typst), so there's no way to inject this detail into
the auto-generated reference list itself; a hand-authored section
immediately before it is the practical way to get the same effect:

```
**[@bibkey1]** — Used for X (Note 1), Y (Note 3), and Z (Note 5).
Corroborated by [secondary source](url).
```

**4. Citations and the Bibliography itself are native MyST**, not
hand-typed source strings: put real BibTeX entries in `<name>/refs.bib`
(git-tracked, real source — this is content, like `index.md`) and cite
with `[@bibkey]`. MyST auto-detects any `.bib` file in the doc directory;
no explicit frontmatter wiring needed. Both templates in the library
render a proper References/Bibliography section — **always after all body
content, regardless of where in `index.md` the citations appear** (both
`lapreprint.typ` and `charged-ieee`'s `lib.typ` place the `bibliography(...)`
call after `body` in their template function) — so don't bother adding
your own "## Bibliography" heading, it'll just be an empty heading with
the real reference list appearing after it. `lapreprint-typst` takes a
bibliography **filename string** (`bibliography-file: "[-doc.bibtex-]"`);
`charged-ieee` takes the **result of calling** `bibliography()`
(`bibliography: bibliography("[-doc.bibtex-]")`) — different template
authors, different conventions, check the specific template's own
parameter before wiring a new one into the library.

## Heading numbering

`lapreprint-typst`'s default is section numbers like "1.a.i" — turned off
(`heading-numbering: none` in our vendored `src/pubdoc/templates/lapreprint-typst/lapreprint.typ`,
line ~26) because it read as clutter on a document that's really just
prose + a flat list of notes, not a structured paper. Doing this exposed
a real bug in the upstream template: its level-1 and level-2 heading
show-rules check `it.numbering != none` before calling `numbering(...)`,
but the level-3 branch doesn't — with numbering disabled, any level-3
heading (which is what `### Note N` is, nested under `## Notes`) would
crash the build. Patched in our vendored copy (same file, ~line 171) by
adding the same guard the other two levels already have. If you ever pull
in a fresh copy of this template, reapply both changes.

**`charged-ieee` has no equivalent toggle** — its heading numbering
("I.", "A.", "a)") is hardcoded inside `@preview/charged-ieee`'s own
`lib.typ` (`set heading(numbering: "I.A.a)")`, applied internally around
`body`), not exposed as a parameter at all. Since we import the package by
its `@preview/...` reference rather than vendoring a copy, there's nothing
in `templates/charged-ieee/` to patch — removing it would mean forking
`lib.typ` into the library instead of importing the upstream package.
Not done; the IEEE variant still shows "A. Notes", "a) Note 1:" etc.

## Environment fragility (read before "fixing" a build failure)

Both sibling projects' `AGENTS.md` files call this out, and it applies here
too: the most common bug class in these tools is *this worked on my
machine* — a hardcoded absolute path, a tool resolved from an unusual PATH,
a symlinked venv defeating a realpath check. `./pubdoc` resolves
`typst` (PATH, else `~/git/typst/target/release/typst`, else fail with
instructions) fresh on every `build`/`open` rather than caching it into a
symlink, and puts the resolved directory on *Curvenote's own child
process* PATH (Curvenote invokes `typst` itself as a subprocess). Do not
hardcode a `typst` path into any `review-builder.yaml` or into
`cli.py` beyond that one resolution step. When debugging an
environment-dependent failure, test with a stripped `PATH` the way
`cv-builder`'s `AGENTS.md` recommends:

```
env -i HOME="$HOME" PATH="/usr/bin:/bin:$HOME/.local/bin" ./pubdoc build <name>
```
