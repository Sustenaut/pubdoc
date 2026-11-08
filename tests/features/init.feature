Feature: pubdoc init sets a repository up to run this release
  `init` writes ./pubdoc, which runs this release's wheel with uvx, and
  ignores the templates every build copies into .pubdoc/.

  Scenario: init writes the launcher and the ignore rule
    Given the file ".gitignore" reads "*.pdf"
    When I run pubdoc "init"
    Then it succeeds
    And "pubdoc" is executable
    And "pubdoc" contains "releases/download/v"
    And "pubdoc" contains "uvx --from"
    And ".gitignore" contains "/.pubdoc/"

  Scenario: init again adds no second ignore rule
    When I run pubdoc "init"
    And I run pubdoc "init"
    Then it succeeds
    And ".gitignore" holds "/.pubdoc/" once

  Scenario: init leaves a directory named pubdoc alone
    Given the file "pubdoc/README.md" reads "an old submodule"
    When I run pubdoc "init"
    Then the exit code is 1
    And stderr mentions "remove it first"
