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
