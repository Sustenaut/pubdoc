Feature: pubdoc builds a document's exports with the templates it carries
  `build` copies this release's templates into .pubdoc/templates/ beside
  the documents, runs the pinned Curvenote in the document's directory, and
  compiles every export myst.yml lists. Stand-ins for npx and typst record
  what they were asked.

  Background:
    Given a document "cv" exporting "cv/main.typ"

  Scenario: build runs Curvenote, then typst on each export
    When I run pubdoc "build" "cv"
    Then it succeeds
    And it prints "built"
    And npx was run in "cv" with "--yes curvenote@0.17.2 build --typst"
    And typst compiled "cv/cv/main.typ"
    And ".pubdoc/templates/cv-sidebar/template.yml" exists
    And ".pubdoc/templates/pub-plugin.mjs" exists

  Scenario: build removes a template file this release does not carry
    Given the file ".pubdoc/templates/old.typ" reads "stale"
    When I run pubdoc "build" "cv"
    Then it succeeds
    And ".pubdoc/templates/old.typ" does not exist

  Scenario: build runs from a variant directory, as review-builder does
    When I run pubdoc "build" ".." in "cv/cv"
    Then it succeeds
    And typst compiled "cv/cv/main.typ"
    And ".pubdoc/templates/cv-sidebar/template.yml" exists

  Scenario: Without typst build says how to get it
    Given no typst is installed
    When I run pubdoc "build" "cv"
    Then the exit code is 1
    And stderr mentions "no 'typst' on PATH"

  Scenario: A failing Curvenote stops the build
    Given Curvenote fails
    When I run pubdoc "build" "cv"
    Then the exit code is 1
    And stderr mentions "curvenote build failed"

  Scenario: A directory without myst.yml is not a document
    When I run pubdoc "build" "nothing"
    Then the exit code is 1
    And stderr mentions "nothing has no myst.yml"

  Scenario: build --all builds every document, each with every export
    Given a document "letter" exporting "letter/main.typ"
    And "cv" also exports "short/main.typ"
    When I run pubdoc "build" "--all"
    Then it succeeds
    And typst compiled "cv/cv/main.typ"
    And typst compiled "letter/letter/main.typ"
    And it prints "built 2 of 2 documents"

  Scenario: build --all goes on past a failing document, reports each, and fails
    Given a document "letter" exporting "letter/main.typ"
    And a document "paper" exporting "paper/main.typ"
    And typst fails on "letter/letter/main.typ"
    When I run pubdoc "build" "--all"
    Then the exit code is 1
    And typst compiled "cv/cv/main.typ"
    And typst compiled "paper/paper/main.typ"
    And stderr mentions "typst compile failed for"
    And it prints "built 2 of 3 documents; failed: letter"

  Scenario: build --all with no documents says so
    Given no documents
    When I run pubdoc "build" "--all"
    Then the exit code is 1
    And stderr mentions "no documents here"

  Scenario Outline: build takes a name or --all, not both or neither
    When I run pubdoc <args>
    Then the exit code is 2
    And stderr mentions "or --all for every document here"

    Examples:
      | args                  |
      | "build"               |
      | "build" "cv" "--all"  |
