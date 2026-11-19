# The fonts pubdoc renders with

pubdoc runs typst with `--ignore-system-fonts` and this directory as its only
font path, so a render depends on the pubdoc release, not on the fonts a
machine happens to have: on 2026-11-19 a laptop's newly installed FreeSans
took over the verdict symbols (✓ ✗ ◪) from DejaVu Sans and reflowed every
line of a fact-check. Beside these, typst carries Libertinus Serif, New
Computer Modern (and its Math) and DejaVu Sans Mono itself.

These are the system fonts the PDFs approved before then embed, taken from
Ubuntu's packages:

| File | Font | Package | Licence |
|---|---|---|---|
| DejaVuSans.ttf, DejaVuSans-Bold.ttf | DejaVu Sans 2.37 | fonts-dejavu-core 2.37-8build1 | Bitstream Vera / DejaVu (public domain changes), LICENSE-DejaVu.txt |
| Ubuntu-R.ttf | Ubuntu Regular 0.869 | fonts-ubuntu 0.869+git20240321-0ubuntu2 | Ubuntu Font Licence 1.0, LICENCE-Ubuntu.txt |
| LiberationSans-*.ttf | Liberation Sans 2.1.5 | fonts-liberation 1:2.1.5-3build1 | SIL Open Font License 1.1, LICENSE-Liberation.txt |

Each licence allows redistributing the fonts unmodified with software. A
template that wants another font names one here, added with its licence, or
falls back to these.
