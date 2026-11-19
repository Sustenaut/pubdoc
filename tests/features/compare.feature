Feature: compare says whether two PDFs are the same document
  A rebuilt PDF is rarely the same bytes as one made months before, so
  compare checks what a reader sees: the page count, the text, and each
  page's pixels. poppler's tools are stand-ins here: a "PDF" is lines of
  text, and each line starting "page" is a page.

  Background:
    Given poppler is installed

  Scenario: The same document, different bytes
    Given the file "a.pdf" reads "%PDF made in September\npage one Dear Hiring Manager\npage two Sincerely"
    And the file "b.pdf" reads "%PDF made in November\npage one Dear Hiring Manager\npage two Sincerely"
    When I run pubdoc "compare" "a.pdf" "b.pdf"
    Then it succeeds
    And it prints "pages: 2 and 2"
    And it prints "text: the same"
    And it prints "pixels: every page the same at 72 dpi"
    And it prints "the same"

  Scenario: A page more
    Given the file "a.pdf" reads "page one Dear\npage two Sincerely"
    And the file "b.pdf" reads "page one Dear\npage two Sincerely\npage three PS"
    When I run pubdoc "compare" "a.pdf" "b.pdf"
    Then the exit code is 1
    And it prints "pages: 2 and 3: they differ"
    And it prints "they differ"

  Scenario: Different words, and the page that looks different
    Given the file "a.pdf" reads "page one Dear Hiring Manager\npage two Sincerely"
    And the file "b.pdf" reads "page one zzzz Recruiter\npage two Sincerely"
    When I run pubdoc "compare" "a.pdf" "b.pdf"
    Then the exit code is 1
    And it prints "text: differs"
    And it prints "+Recruiter"
    And it prints "page 1:"
    And it does not print "page 2:"
