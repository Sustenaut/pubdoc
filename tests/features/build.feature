Feature: pubdoc builds every variant and layout of a doc
  `build` stages a doc's parts, and the shared parts they start from, in
  the doc's build/src/, writes the MyST configuration for each Typst layout
  there from project.yml, runs the pinned Curvenote in it, compiles each
  export to build/<variant>/<layout>.pdf, and runs each exporter layout.
  build/ ignores itself. Stand-ins for npx and typst record what they were
  asked; the LinkedIn exporter is the real one, run with node.

  Background:
    Given a scratch directory
    And the program under test is "pubdoc"
    And a stand-in "npx" that notes where it runs
    And a stand-in "typst"
    And the example project

  Scenario: build makes every variant x layout of a doc
    When I run "pubdoc build job-applications/acme"
    Then it succeeds
    And "npx" ran in "job-applications/acme/build/src" with "--yes curvenote@0.17.2 build --typst"
    And "typst" was run with arguments matching "compile /*/job-applications/acme/build/engineering/letter-pdf.typ /*/job-applications/acme/build/engineering/letter-pdf.pdf"
    And "typst" was run with arguments matching "compile /*/job-applications/acme/build/engineering/cv-pdf.typ /*/job-applications/acme/build/engineering/cv-pdf.pdf"
    And "typst" was run with arguments matching "compile /*/job-applications/acme/build/research/letter-pdf.typ /*/job-applications/acme/build/research/letter-pdf.pdf"
    And "typst" was run with arguments matching "compile /*/job-applications/acme/build/research/cv-pdf.typ /*/job-applications/acme/build/research/cv-pdf.pdf"
    And it prints "built job-applications/acme/build/research/cv-linkedin.txt"
    And the file "job-applications/acme/build/research/cv-linkedin.txt" includes "Python"
    And the file "job-applications/acme/build/.gitignore" includes "*"
    And the file "job-applications/acme/build/templates/cv-sidebar/template.yml" exists

  Scenario: Each variant takes its own override, the doc's part, or the shared part, in that order
    When I run "pubdoc build job-applications/acme"
    Then it succeeds
    And the file "job-applications/acme/build/src/myst.yml" includes "article: acme/letter.md"
    And the file "job-applications/acme/build/src/myst.yml" includes "article: acme/letter.research.md"
    And the file "job-applications/acme/build/src/myst.yml" includes "article: shared/base-cv/cv.md"
    And the file "job-applications/acme/build/src/myst.yml" includes "article: shared/base-cv/cv.research.md"
    And the file "job-applications/acme/build/src/myst.yml" includes "template: ../templates/cv-sidebar"
    And the file "job-applications/acme/build/src/myst.yml" includes "output: ../research/cv-pdf.typ"
    And the file "job-applications/acme/build/src/myst.yml" includes "../templates/pub-plugin.mjs"
    And the file "job-applications/acme/build/src/shared/base-cv/cv.md" exists

  Scenario: A doc's own part replaces the shared one, and can include it
    Given a file "job-applications/acme/cv.md" holding:
      """
      ```{include} ../shared/base-cv/cv.md
      ```
      """
    When I run "pubdoc build job-applications/acme"
    Then it succeeds
    And the file "job-applications/acme/build/src/myst.yml" includes "article: acme/cv.md"
    And the file "job-applications/acme/build/src/myst.yml" does not include "article: shared/base-cv/cv.md"
    And the file "job-applications/acme/build/src/acme/cv.md" includes "../shared/base-cv/cv.md"
    And the file "job-applications/acme/build/src/shared/base-cv/cv.md" exists

  Scenario: A doc.yml that narrows builds only what it keeps
    When I run "pubdoc build job-applications/globex"
    Then it succeeds
    And "typst" was run with arguments matching "compile /*/job-applications/globex/build/engineering/cv-pdf.typ /*/job-applications/globex/build/engineering/cv-pdf.pdf"
    And the file "job-applications/globex/build/research" does not exist
    And the file "job-applications/globex/build/engineering/cv-linkedin.txt" does not exist

  Scenario: A project builds each of its docs
    When I run "pubdoc build job-applications"
    Then it succeeds
    And "typst" was run with arguments matching "compile /*/job-applications/acme/build/research/cv-pdf.typ /*/job-applications/acme/build/research/cv-pdf.pdf"
    And "typst" was run with arguments matching "compile /*/job-applications/globex/build/engineering/letter-pdf.typ /*/job-applications/globex/build/engineering/letter-pdf.pdf"

  Scenario: --variant and --layout build one render, as a preview does
    When I run "pubdoc build job-applications/acme --variant research --layout cv-pdf"
    Then it succeeds
    And "typst" was run with arguments matching "compile /*/job-applications/acme/build/research/cv-pdf.typ /*/job-applications/acme/build/research/cv-pdf.pdf"
    And "typst" was run 1 times
    And the file "job-applications/acme/build/research/cv-linkedin.txt" does not exist

  Scenario: An optional part a doc does not supply builds nothing
    Given in "job-applications/project.yml" "  cv-linkedin:" becomes "  webpage-pdf: {part: webpage, template: lapreprint-typst, format: pdf}\n  cv-linkedin:"
    When I run "pubdoc build job-applications/acme"
    Then it succeeds
    And the file "job-applications/acme/build/src/myst.yml" does not include "webpage"

  Scenario: build runs from anywhere, given the doc's path
    When from "job-applications/globex" I run "pubdoc build ../acme"
    Then it succeeds
    And "typst" was run with arguments matching "compile /*/job-applications/acme/build/research/cv-pdf.typ /*/job-applications/acme/build/research/cv-pdf.pdf"

  Scenario: build removes what this build did not write
    Given a file "job-applications/acme/build/templates/old.typ" holding "stale"
    And a file "job-applications/acme/build/src/acme/old.md" holding "stale"
    When I run "pubdoc build job-applications/acme"
    Then it succeeds
    And the file "job-applications/acme/build/templates/old.typ" does not exist
    And the file "job-applications/acme/build/src/acme/old.md" does not exist

  Scenario: Without publets-local.json the {pub} plugin is left out
    Given the file "publets-local.json" is removed
    And in "job-applications/project.yml" "  cv-linkedin: {part: cv, exporter: linkedin, format: text}\n" becomes "\n"
    And in "job-applications/project.yml" "letter-pdf, cv-pdf, cv-linkedin]" becomes "letter-pdf, cv-pdf]"
    When I run "pubdoc build job-applications/acme"
    Then it succeeds
    And the file "job-applications/acme/build/src/myst.yml" does not include "pub-plugin"
    And the file "job-applications/acme/build/src/myst.yml" includes "annotations.mjs"

  Scenario: build refuses a project that does not check
    Given in "job-applications/project.yml" "{part: letter," becomes "{part: lettr,"
    When I run "pubdoc build job-applications/acme"
    Then the exit code is 1
    And stderr mentions "layouts.letter-pdf.part: no part 'lettr'"
    And stderr mentions "job-applications/project.yml has 1 problem(s); see `pubdoc check`"

  Scenario Outline: build needs a doc or a project
    When I run "pubdoc build <name>"
    Then the exit code is 1
    And stderr mentions "<message>"

    Examples:
      | name                         | message                                                                     |
      | nothing                      | nothing is not a doc or a project: no project.yml in it or the directory above |
      | job-applications/shared      | job-applications/shared is no doc of job-applications                        |

  Scenario: Without typst build says how to get it
    Given "typst" is not installed
    And the environment sets "HOME" to "/nonexistent"
    When I run "pubdoc build job-applications/acme"
    Then the exit code is 1
    And stderr mentions "no 'typst' on PATH"

  Scenario: A failing Curvenote stops the build
    Given a stand-in "npx" that fails, saying "curvenote: it broke"
    When I run "pubdoc build job-applications/acme"
    Then the exit code is 1
    And stderr mentions "curvenote build failed for job-applications/acme"
    And "typst" was not run

  Scenario: build --all builds every doc of every project
    When I run "pubdoc build --all"
    Then it succeeds
    And it prints "built 2 of 2 docs"

  Scenario: build --all goes on past a failing doc, reports each, and fails
    Given a stand-in "typst" that answers in turn:
      | args                                                                | exit |
      | compile /*/job-applications/acme/build/engineering/letter-pdf.typ * | 4    |
      | *                                                                   | 0    |
    When I run "pubdoc build --all"
    Then the exit code is 1
    And "typst" was run with arguments matching "compile /*/job-applications/globex/build/engineering/cv-pdf.typ /*/job-applications/globex/build/engineering/cv-pdf.pdf"
    And stderr mentions "typst compile failed for"
    And it prints "built 1 of 2 docs; failed: job-applications/acme"

  Scenario: build --all counts a project that does not check as failed
    Given a file "other/project.yml" holding "project: other"
    When I run "pubdoc build --all"
    Then the exit code is 1
    And stderr mentions "other/project.yml: 'purpose' is a required property"
    And it prints "built 2 of 3 docs; failed: other (does not check)"

  Scenario: build --all with no projects says so
    Given the file "job-applications/project.yml" is removed
    When I run "pubdoc build --all"
    Then the exit code is 1
    And stderr mentions "no projects here"

  Scenario Outline: build takes a doc or --all, not both or neither
    When I run "<command>"
    Then the exit code is 2
    And stderr mentions "or --all for every doc here"

    Examples:
      | command                                  |
      | pubdoc build                             |
      | pubdoc build job-applications/acme --all |

  Scenario: open serves a live Curvenote site of a doc's staged parts
    When I run "pubdoc open job-applications/acme --port 3000"
    Then it succeeds
    And "npx" ran in "job-applications/acme/build/src" with "--yes curvenote@0.17.2 start --port 3000"
