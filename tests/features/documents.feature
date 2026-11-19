Feature: pubdoc lists projects, and previews one PDF render
  `list` names each project and its docs. `preview` writes review-builder's
  configuration for one render into the doc's build/ and runs it there; its
  Accept button runs `approve` (versions.feature).

  Background:
    Given the example project

  Scenario: --version names the release
    When I run pubdoc "--version"
    Then it succeeds
    And it prints "pubdoc "

  Scenario: list names the projects and their docs
    When I run pubdoc "list"
    Then it succeeds
    And it prints "job-applications: Win software engineering and research roles"
    And it prints "job-applications/acme  (engineering, research)"
    And it prints "job-applications/globex  (engineering)"

  Scenario: list names a project that does not load
    Given the file "job-applications/project.yml" reads "project: job-applications"
    When I run pubdoc "list"
    Then it succeeds
    And it prints "job-applications: does not load; see `pubdoc check`"

  Scenario: variants names a doc's variants, as its doc.yml narrows them
    When I run pubdoc "variants" "job-applications/globex"
    Then it succeeds
    And it prints "engineering"
    And it does not print "research"

  Scenario: variants needs one doc, not a project
    When I run pubdoc "variants" "job-applications"
    Then the exit code is 1
    And stderr mentions "job-applications is a project; name one of its docs: job-applications/acme, job-applications/globex"

  Scenario: With several PDF renders, preview says which there are
    When I run pubdoc "preview" "job-applications/globex"
    Then the exit code is 1
    And stderr mentions "job-applications/globex has 2 PDF renders (engineering cv-pdf, engineering letter-pdf); name the variant and layout"

  Scenario: A render the doc does not have is refused
    When I run pubdoc "preview" "job-applications/globex" "research" "cv-pdf"
    Then the exit code is 1
    And stderr mentions "job-applications/globex has no PDF layout for research and cv-pdf"

  Scenario: preview runs review-builder in the doc's build/, on the port given
    When I run pubdoc "preview" "job-applications/globex" "engineering" "cv-pdf" "--port" "9000"
    Then it succeeds
    And review-builder-preview was run in "job-applications/globex/build" with "9000"
    And "job-applications/globex/build/review-builder.yaml" contains "pdf_path: engineering/cv-pdf.pdf"
    And "job-applications/globex/build/review-builder.yaml" contains "- ../letter.md"
    And "job-applications/globex/build/review-builder.yaml" contains "- ../../shared/base-cv/cv.md"
    And "job-applications/globex/build/review-builder.yaml" contains "- ../../project.yml"
    And "job-applications/globex/build/review-builder.yaml" contains "- approve"
