Feature: pubdoc builds every variant and layout of a doc
  `build` stages a doc's parts, and the shared parts they start from, in
  the doc's build/src/, one MyST project per part file the Typst layouts
  use, each with that file as its table of contents and the configuration
  for its layouts
  there from project.yml, runs the pinned Curvenote in it, compiles each
  export to build/<variant>/<layout>.pdf, and runs each exporter layout.
  build/ ignores itself. Stand-ins for npx and typst record what they were
  asked; the LinkedIn exporter is the real one, run with node.

  Background:
    Given the example project

  Scenario: build makes every variant x layout of a doc
    When I run pubdoc "build" "job-applications/acme"
    Then it succeeds
    And npx was run in "job-applications/acme/build/src/acme.letter" with "--yes curvenote@0.17.2 build --typst"
    And npx was run in "job-applications/acme/build/src/shared.base-cv.cv.research" with "--yes curvenote@0.17.2 build --typst"
    And typst compiled "job-applications/acme/build/engineering/letter-pdf/main.typ" to "job-applications/acme/build/engineering/letter-pdf.pdf"
    And typst compiled "job-applications/acme/build/engineering/cv-pdf/main.typ" to "job-applications/acme/build/engineering/cv-pdf.pdf"
    And typst compiled "job-applications/acme/build/research/letter-pdf/main.typ" to "job-applications/acme/build/research/letter-pdf.pdf"
    And typst compiled "job-applications/acme/build/research/cv-pdf/main.typ" to "job-applications/acme/build/research/cv-pdf.pdf"
    And it prints "built job-applications/acme/build/research/cv-linkedin.txt"
    And "job-applications/acme/build/research/cv-linkedin.txt" contains "Python"
    And "job-applications/acme/build/.gitignore" contains "*"
    And "job-applications/acme/build/templates/cv-sidebar/template.yml" exists

  Scenario: Each variant takes its own override, the doc's part, or the shared part, in that order
    When I run pubdoc "build" "job-applications/acme"
    Then it succeeds
    And "job-applications/acme/build/src/acme.letter/myst.yml" contains "file: acme/letter.md"
    And "job-applications/acme/build/src/acme.letter.research/myst.yml" contains "file: acme/letter.research.md"
    And "job-applications/acme/build/src/shared.base-cv.cv/myst.yml" contains "file: shared/base-cv/cv.md"
    And "job-applications/acme/build/src/shared.base-cv.cv.research/myst.yml" contains "file: shared/base-cv/cv.research.md"
    And "job-applications/acme/build/src/shared.base-cv.cv.research/myst.yml" contains "template: ../../templates/cv-sidebar"
    And "job-applications/acme/build/src/shared.base-cv.cv.research/myst.yml" contains "output: ../../research/cv-pdf/main.typ"
    And "job-applications/acme/build/src/shared.base-cv.cv.research/myst.yml" contains "../../templates/pub-plugin.mjs"
    And "job-applications/acme/build/src/shared.base-cv.cv/shared/base-cv/cv.md" exists

  Scenario: A doc's own part replaces the shared one, and can include it
    Given the file "job-applications/acme/cv.md" reads:
      """
      ```{include} ../shared/base-cv/cv.md
      ```
      """
    When I run pubdoc "build" "job-applications/acme"
    Then it succeeds
    And "job-applications/acme/build/src/acme.cv/myst.yml" contains "file: acme/cv.md"
    And "job-applications/acme/build/src/shared.base-cv.cv" does not exist
    And "job-applications/acme/build/src/acme.cv/acme/cv.md" contains "../shared/base-cv/cv.md"
    And "job-applications/acme/build/src/acme.cv/shared/base-cv/cv.md" exists

  Scenario: A doc.yml that narrows builds only what it keeps
    When I run pubdoc "build" "job-applications/globex"
    Then it succeeds
    And typst compiled "job-applications/globex/build/engineering/cv-pdf/main.typ" to "job-applications/globex/build/engineering/cv-pdf.pdf"
    And "job-applications/globex/build/research" does not exist
    And "job-applications/globex/build/engineering/cv-linkedin.txt" does not exist

  Scenario: A project builds each of its docs
    When I run pubdoc "build" "job-applications"
    Then it succeeds
    And typst compiled "job-applications/acme/build/research/cv-pdf/main.typ" to "job-applications/acme/build/research/cv-pdf.pdf"
    And typst compiled "job-applications/globex/build/engineering/letter-pdf/main.typ" to "job-applications/globex/build/engineering/letter-pdf.pdf"

  Scenario: --variant and --layout build one render, as a preview does
    When I run pubdoc "build" "job-applications/acme" "--variant" "research" "--layout" "cv-pdf"
    Then it succeeds
    And typst compiled "job-applications/acme/build/research/cv-pdf/main.typ" to "job-applications/acme/build/research/cv-pdf.pdf"
    And typst compiled only once
    And "job-applications/acme/build/research/cv-linkedin.txt" does not exist

  Scenario: An optional part a doc does not supply builds nothing
    Given in "job-applications/project.yml" "  cv-linkedin:" becomes "  webpage-pdf: {part: webpage, template: lapreprint-typst, format: pdf}\n  cv-linkedin:"
    When I run pubdoc "build" "job-applications/acme"
    Then it succeeds
    And "job-applications/acme/build/src/acme.webpage" does not exist

  Scenario: build runs from anywhere, given the doc's path
    When I run pubdoc "build" "../acme" in "job-applications/globex"
    Then it succeeds
    And typst compiled "job-applications/acme/build/research/cv-pdf/main.typ" to "job-applications/acme/build/research/cv-pdf.pdf"

  Scenario: build removes what this build did not write
    Given the file "job-applications/acme/build/templates/old/main.typ" reads "stale"
    And the file "job-applications/acme/build/src/acme.letter/acme/old.md" reads "stale"
    When I run pubdoc "build" "job-applications/acme"
    Then it succeeds
    And "job-applications/acme/build/templates/old/main.typ" does not exist
    And "job-applications/acme/build/src/acme.letter/acme/old.md" does not exist

  Scenario: Without publets-local.json the {pub} plugin is left out
    Given the file "publets-local.json" is gone
    And in "job-applications/project.yml" "  cv-linkedin: {part: cv, exporter: linkedin, format: text}\n" becomes "\n"
    And in "job-applications/project.yml" "letter-pdf, cv-pdf, cv-linkedin]" becomes "letter-pdf, cv-pdf]"
    When I run pubdoc "build" "job-applications/acme"
    Then it succeeds
    And "job-applications/acme/build/src/acme.letter/myst.yml" does not contain "pub-plugin"
    And "job-applications/acme/build/src/acme.letter/myst.yml" contains "annotations.mjs"

  Scenario: build refuses a project that does not check
    Given in "job-applications/project.yml" "{part: letter," becomes "{part: lettr,"
    When I run pubdoc "build" "job-applications/acme"
    Then the exit code is 1
    And stderr mentions "layouts.letter-pdf.part: no part 'lettr'"
    And stderr mentions "job-applications/project.yml has 1 problem(s); see `pubdoc check`"

  Scenario Outline: build needs a doc or a project
    When I run pubdoc "build" "<name>"
    Then the exit code is 1
    And stderr mentions "<message>"

    Examples:
      | name                         | message                                                                     |
      | nothing                      | nothing is not a doc or a project: no project.yml in it or the directory above |
      | job-applications/shared      | job-applications/shared is no doc of job-applications                        |

  Scenario: Without typst build says how to get it
    Given no typst is installed
    When I run pubdoc "build" "job-applications/acme"
    Then the exit code is 1
    And stderr mentions "no 'typst' on PATH"

  Scenario: A failing Curvenote stops the build
    Given Curvenote fails
    When I run pubdoc "build" "job-applications/acme"
    Then the exit code is 1
    And stderr mentions "curvenote build failed for job-applications/acme"

  Scenario: build --all builds every doc of every project
    When I run pubdoc "build" "--all"
    Then it succeeds
    And it prints "built 2 of 2 docs"

  Scenario: build --all goes on past a failing doc, reports each, and fails
    Given typst fails on "job-applications/acme/build/engineering/letter-pdf/main.typ"
    When I run pubdoc "build" "--all"
    Then the exit code is 1
    And typst compiled "job-applications/globex/build/engineering/cv-pdf/main.typ" to "job-applications/globex/build/engineering/cv-pdf.pdf"
    And stderr mentions "typst compile failed for"
    And it prints "built 1 of 2 docs; failed: job-applications/acme"

  Scenario: build --all counts a project that does not check as failed
    Given the file "other/project.yml" reads "project: other"
    When I run pubdoc "build" "--all"
    Then the exit code is 1
    And stderr mentions "other/project.yml: 'purpose' is a required property"
    And it prints "built 2 of 3 docs; failed: other (does not check)"

  Scenario: build --all with no projects says so
    Given the file "job-applications/project.yml" is gone
    When I run pubdoc "build" "--all"
    Then the exit code is 1
    And stderr mentions "no projects here"

  Scenario Outline: build takes a doc or --all, not both or neither
    When I run pubdoc <args>
    Then the exit code is 2
    And stderr mentions "or --all for every doc here"

    Examples:
      | args                                     |
      | "build"                                  |
      | "build" "job-applications/acme" "--all"  |

  Scenario: open serves a live Curvenote site of a doc's staged parts
    When I run pubdoc "open" "job-applications/acme" "--port" "3000"
    Then it succeeds
    And npx was run in "job-applications/acme/build/site" with "--yes curvenote@0.17.2 start --port 3000"
    And "job-applications/acme/build/site/myst.yml" contains "file: shared/base-cv/cv.research.md"
    And "job-applications/acme/build/site/myst.yml" contains "file: acme/letter.md"
