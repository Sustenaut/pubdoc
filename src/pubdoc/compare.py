"""Whether two PDFs are the same document: the same number of pages, the
same text, and each page the same picture.

A rebuilt PDF is rarely the same bytes as one made months ago: the PDF
records when it was made, and font subsets and object order move with the
toolchain. What a reader sees is what has to match, so this compares that,
with poppler's pdfinfo, pdftotext and pdftoppm.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

DPI = 72
# A pixel differs when its grey level moves by more than this, out of 255:
# anti-aliasing noise stays under it, a moved glyph or a new colour does not.
THRESHOLD = 40


class CompareError(Exception):
    pass


@dataclass
class Report:
    pages: tuple[int, int]
    text_same: bool
    text_diff: list[str] = field(default_factory=list)
    pixels: list[int] = field(default_factory=list)  # differing pixels, per page

    @property
    def same(self) -> bool:
        return self.pages[0] == self.pages[1] and self.text_same and not any(self.pixels)

    def lines(self) -> list[str]:
        out = [f"pages: {self.pages[0]} and {self.pages[1]}"
               + ("" if self.pages[0] == self.pages[1] else ": they differ")]
        out.append("text: the same" if self.text_same else "text: differs")
        out += [f"  {line}" for line in self.text_diff[:40]]
        for page, count in enumerate(self.pixels, 1):
            if count:
                out.append(f"page {page}: {count} pixel(s) differ at {DPI} dpi")
        if self.pixels and not any(self.pixels):
            out.append(f"pixels: every page the same at {DPI} dpi")
        out.append("the same" if self.same else "they differ")
        return out


def tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise CompareError(f"no '{name}' on PATH; install poppler (apt install poppler-utils)")
    return found


def run(*argv: str) -> str:
    done = subprocess.run(argv, capture_output=True, text=True)
    if done.returncode != 0:
        raise CompareError(f"{Path(argv[0]).name} failed on {argv[-1]}: {done.stderr.strip()}")
    return done.stdout


def page_count(pdf: Path) -> int:
    for line in run(tool("pdfinfo"), str(pdf)).splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    raise CompareError(f"pdfinfo gives no page count for {pdf}")


def words(pdf: Path) -> list[str]:
    return run(tool("pdftotext"), str(pdf), "-").split()


def pages(pdf: Path, out: Path) -> list[bytes]:
    """Each page as a greyscale PGM's pixels."""
    subprocess.run([tool("pdftoppm"), "-r", str(DPI), "-gray", str(pdf), str(out / "page")],
                   check=True, capture_output=True)
    return [pgm(path) for path in sorted(out.glob("page*.pgm"), key=lambda p: int(p.stem.split("-")[-1]))]


def pgm(path: Path) -> bytes:
    data = path.read_bytes()
    # P5 <width> <height> <max>\n<pixels>
    head, fields = 0, []
    while len(fields) < 4:
        while data[head:head + 1].isspace():
            head += 1
        end = head
        while not data[end:end + 1].isspace():
            end += 1
        fields.append(data[head:end])
        head = end
    return fields[1] + b"x" + fields[2] + b":" + data[head + 1:]


def differing(a: bytes, b: bytes) -> int:
    size_a, _, pixels_a = a.partition(b":")
    size_b, _, pixels_b = b.partition(b":")
    if size_a != size_b:
        return max(len(pixels_a), len(pixels_b))
    return sum(1 for x, y in zip(pixels_a, pixels_b, strict=True) if abs(x - y) > THRESHOLD)


def compare(a: Path, b: Path) -> Report:
    import difflib
    counts = (page_count(a), page_count(b))
    words_a, words_b = words(a), words(b)
    diff = [line for line in difflib.unified_diff(words_a, words_b, "first", "second", n=2, lineterm="")
            if not line.startswith(("---", "+++"))]
    report = Report(counts, words_a == words_b, diff)
    with tempfile.TemporaryDirectory(prefix="pubdoc-compare-") as scratch:
        first, second = Path(scratch) / "a", Path(scratch) / "b"
        first.mkdir()
        second.mkdir()
        pa, pb = pages(a, first), pages(b, second)
        report.pixels = [differing(x, y) for x, y in zip(pa, pb, strict=False)]
    return report
