// Thin jtex wrapper around the @preview/charged-ieee Typst Universe
// package. Unlike lapreprint-typst, charged-ieee isn't itself a jtex/MyST
// template - this file is what adapts it into one, so MyST/Curvenote can
// drive it from the same index.md/myst.yml as any other template.
//
// charged-ieee's `title`/`abstract` parameters are Typst *content*
// ([...]), not strings - jtex only does raw text substitution, so a
// title/abstract containing Typst markup characters (_, *, #, $) would be
// interpreted as markup here. Not an issue for plain prose titles; if
// that ever matters, escape at the source (myst.yml/index.md) instead of
// here.
#import "@preview/charged-ieee:0.1.4": ieee

#show: ieee.with(
  title: [[-doc.title-]],
[# if parts.abstract #]
  abstract: [
[-parts.abstract-]
  ],
[# endif #]
  authors: (
[# for author in doc.authors #]
    (
      name: "[-author.name-]",
[# if author.email #]
      email: "[-author.email-]",
[# endif #]
    ),
[# endfor #]
  ),
[# if doc.keywords #]
  index-terms: ([#- for keyword in doc.keywords -#]"[-keyword-]",[#- endfor -#]),
[# endif #]
[# if doc.bibtex #]
  bibliography: bibliography("[-doc.bibtex-]"),
[# endif #]
)

[-IMPORTS-]

[-CONTENT-]
