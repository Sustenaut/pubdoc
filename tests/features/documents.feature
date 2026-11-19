Feature: pubdoc lists projects, and previews and approves one PDF render
  `list` names each project and its docs. `preview` writes review-builder's
  configuration for one render into the doc's build/ and runs it there;
  `approve`, which its Accept button runs, copies that render's PDF into
  the doc's versions/, dated, and prints that path, which build/versions
  (a link to it) makes reachable from the preview.

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

  Scenario: approve copies one render into the doc's versions/
    Given "job-applications/acme/build/research/cv-pdf.pdf" is built
    When I run pubdoc "approve" "job-applications/acme" "research" "cv-pdf"
    Then it succeeds
    And it prints today's "versions/acme_research_cv-pdf" PDF
    And today's "job-applications/acme/versions/acme_research_cv-pdf" PDF exists

  Scenario: A doc's only PDF render needs no naming
    Given the file "job-applications/globex/doc.yml" reads "{variants: [engineering], layouts: [cv-pdf]}"
    And "job-applications/globex/build/engineering/cv-pdf.pdf" is built
    When I run pubdoc "approve" "job-applications/globex"
    Then it succeeds
    And today's "job-applications/globex/versions/globex_engineering_cv-pdf" PDF exists

  Scenario: With several PDF renders, approve says which there are
    When I run pubdoc "approve" "job-applications/globex"
    Then the exit code is 1
    And stderr mentions "job-applications/globex has 2 PDF renders (engineering cv-pdf, engineering letter-pdf); name the variant and layout"

  Scenario: A render the doc does not have is refused
    When I run pubdoc "approve" "job-applications/globex" "research" "cv-pdf"
    Then the exit code is 1
    And stderr mentions "job-applications/globex has no PDF layout for research and cv-pdf"

  Scenario: approve needs a built PDF
    When I run pubdoc "approve" "job-applications/acme" "research" "cv-pdf"
    Then the exit code is 1
    And stderr mentions "job-applications/acme/build/research/cv-pdf.pdf not built yet"

  Scenario: preview runs review-builder in the doc's build/, on the port given
    When I run pubdoc "preview" "job-applications/globex" "engineering" "cv-pdf" "--port" "9000"
    Then it succeeds
    And review-builder-preview was run in "job-applications/globex/build" with "9000"
    And "job-applications/globex/build/review-builder.yaml" contains "pdf_path: engineering/cv-pdf.pdf"
    And "job-applications/globex/build/review-builder.yaml" contains "- ../letter.md"
    And "job-applications/globex/build/review-builder.yaml" contains "- ../../shared/base-cv/cv.md"
    And "job-applications/globex/build/review-builder.yaml" contains "- ../../project.yml"
    And "job-applications/globex/build/review-builder.yaml" contains "- approve"
    And "job-applications/globex/build/versions" links to "../versions"
