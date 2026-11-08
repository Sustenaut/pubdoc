Feature: pubdoc lists documents and approves a variant's PDF
  A document is a directory holding a myst.yml; a variant is a directory of
  it holding a review-builder.yaml. `approve` is what review-builder's
  Accept button runs: it copies main.pdf into versions/, dated, and prints
  that path.

  Background:
    Given a document "cv" exporting "cv/main.typ"

  Scenario: --version names the release
    When I run pubdoc "--version"
    Then it succeeds
    And it prints "pubdoc "

  Scenario: list names the documents here
    Given a document "letter" exporting "cv/main.typ"
    When I run pubdoc "list"
    Then it succeeds
    And it prints "cv"
    And it prints "letter"

  Scenario: variants names a document's variants
    When I run pubdoc "variants" "cv"
    Then it succeeds
    And it prints "cv"

  Scenario: approve names the copy after version_name
    Given "cv/cv/review-builder.yaml" sets version_name "Jane_Doe_CV"
    And "cv/cv/main.pdf" is built
    When I run pubdoc "approve" "cv" "cv"
    Then it succeeds
    And it prints today's "versions/Jane_Doe_CV" PDF
    And today's "cv/cv/versions/Jane_Doe_CV" PDF exists

  Scenario: Without version_name the copy is named after the directories
    Given "cv/cv/main.pdf" is built
    When I run pubdoc "approve" "cv" "cv"
    Then it succeeds
    And today's "cv/cv/versions/cv_cv" PDF exists

  Scenario: approve needs a built PDF
    When I run pubdoc "approve" "cv" "cv"
    Then the exit code is 1
    And stderr mentions "not built yet"

  Scenario: approve needs a variant
    When I run pubdoc "approve" "cv" "web"
    Then the exit code is 1
    And stderr mentions "cv/web has no review-builder.yaml"
