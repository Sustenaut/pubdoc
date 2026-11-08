// From-scratch Typst layout replicating cv-builder's original hand-built
// CSS design: a maroon horizontal rule + rotated vertical section-label
// sidebar above each top-level heading, a maroon/pink color scheme, on
// an A4 page (confirmed via `pdfinfo` on the original weasyprint-built
// PDF - not US Letter).

#let structural-maroon = rgb(128, 0, 0)   // #800000 - CSS: .section border-top, .section h1, .myname
#let link-maroon = rgb(0x72, 0, 0)        // #720000 - CSS: a, a:active, a:visited (a distinct, darker shade)
#let summary-pink = rgb(0xff, 0xee, 0xee) // #FEE - CSS: .summary background-color

#let gutter = 2.4em

// Target gap between the section's rule and the label's LAST letter.
// Rendered ink ends up ~1pt further than this (glyph side-bearings);
// verified by measuring every heading in the built PDF (all within
// 8.8-9.5pt of their rule).
#let label-top-offset = 8pt

#let label-font = ("Libertinus Serif", "Noto Serif", "DejaVu Serif")
#let label-text(body, ..args) = text(
  font: label-font, size: 12pt, tracking: 2pt, upper(body), ..args,
)

// The label is drawn in a zero-width box, so Typst wraps it at every
// space: the vertical extent is the LONGEST WORD, not the whole string.
// Measure exactly that, in the same font/size/tracking as the label.
#let label-length(it) = {
  let words = if it.body.has("text") { it.body.text.split(" ") } else { (it.body,) }
  calc.max(..words.map(w => measure(label-text(w)).width))
}

#let cv-sidebar(title: none, subtitle: none, body) = {
  set page(
    paper: "a4",
    margin: (left: gutter + 1in, rest: 1in),
  )
  set text(font: ("Libertinus Serif", "Noto Serif", "DejaVu Serif"), size: 12pt, fill: rgb(51, 51, 51))
  set par(justify: false, leading: 0.65em)

  show link: it => text(fill: link-maroon, it)

  // Each top-level heading becomes a rotated vertical label in the left
  // gutter, matching CSS's `.section h1 { position:absolute; transform:
  // translate(-100%,0%) rotate(-90deg); transform-origin:100% 0; }` -
  // removed entirely from normal flow, not printed inline.
  //
  // Level 2, not 1: MyST's typst exporter maps Markdown `#` (H1) to Typst
  // `==` (level 2) - it reserves level 1 (`=`) for the document title
  // itself (confirmed by inspecting the generated main.typ directly).
  //
  // Positioning uses `place()`, not `block()`: a real `block()` (tried
  // briefly, with `rotate(reflow: true, ...)` so its reported size
  // matches the label's true rotated, tall-and-narrow shape) is an
  // ordinary flow element - it reserves that much vertical space in the
  // page's single content column before the next thing can start, even
  // though the label itself is shifted out into the margin visually. For
  // a long label like "Employment" that pushed the body text below it
  // down by a large, unwanted gap. `place()`'d content never reserves
  // flow space at all, regardless of its own size, which is what we
  // actually want here: the label lives entirely in the margin and
  // should never affect where body text in the main column starts.
  //
  // An *unaligned* `place()` (no alignment argument, just `dx`/`dy`)
  // tracks the current flow position automatically and correctly, even
  // with `rotate()` - but only when it is the sole content of a
  // zero-size `box(width: 0pt, height: 0pt, ...)`, with nothing else
  // wrapping the rotated text beyond the bare `label-text(...)` and the
  // `rotate(-90deg, ...)` below (an inner box, a
  // scoped show rule, `reflow: true` on the outer rotate, or extracting
  // `it.body.text` all independently reintroduce a mis-tracking bug that
  // silently sends the label to the wrong heading's position - keep this
  // block exactly this minimal).
  //
  // The label reads up the page (-90deg). Its zero-width layout box
  // means "origin: top + right" collapses onto the text's START, so the
  // pivot is the first letter, which lands a fixed distance below the
  // rule, and the label extends UPWARD from there by its own length.
  // The show rule below therefore drops the label by exactly that
  // length, putting the LAST letter a constant distance under the rule
  // for every heading. (An earlier version scaled a gap by an estimated
  // width instead - wrong for any label whose estimate differed from
  // what is actually drawn, i.e. most of them.)
  //
  show heading.where(level: 2): it => {
    v(1em, weak: true)
    line(length: 100%, stroke: 0.75pt + structural-maroon)
    v(0.5em, weak: true)
    context {
      // The rotated label's first letter lands a constant 6.7pt below the
      // rule at dy: 0 (measured from the render); it then extends upward by
      // its own length, so dropping it by (length + wanted offset - 6.7pt)
      // puts the LAST letter `label-top-offset` below the rule.
      let drop = label-length(it) + label-top-offset - 6.7pt
      box(width: 0pt, height: 0pt,
        place(dx: -gutter - 0.15em, dy: drop,
          rotate(-90deg, origin: top + left,
            label-text(it.body, fill: structural-maroon)
          ),
        ),
      )
    }
  }

  // Name / tagline, matching .myname (bold, maroon, 16px) / .tagline.
  text(weight: "bold", fill: structural-maroon, size: 16pt, title)
  if subtitle != none {
    linebreak()
    text(subtitle)
  }
  v(1em)

  body
}
