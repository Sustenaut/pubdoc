Feature: pubdoc init sets a repository up to run this release
  `init` writes requirements-pubdoc.txt, which pins this release's wheel in
  the form pubrules's nightly moves, and ./pubdoc, which names no release and
  runs the one that file pins with uvx. Builds write only into each doc's
  build/, which ignores itself, so init touches no .gitignore.
  `new-project` starts a project: a project.yml and a first doc that check.

  Scenario: init writes the launcher and its pin
    Given the file ".gitignore" reads "*.pdf"
    When I run pubdoc "init"
    Then it succeeds
    And "pubdoc" is executable
    And "pubdoc" contains "uvx --from"
    And "pubdoc" does not contain "releases/download"
    And "requirements-pubdoc.txt" is one release wheel pin of pubdoc
    And ".gitignore" does not contain "pubdoc"

  Scenario: new-project starts a project that checks
    When I run pubdoc "new-project" "notes" "--purpose" "Meeting notes"
    And I run pubdoc "check"
    Then it succeeds
    And "notes/project.yml" contains "purpose: Meeting notes"
    And "notes/draft/main.md" exists

  Scenario: new-project leaves an existing project alone
    Given the file "notes/project.yml" reads "project: notes"
    When I run pubdoc "new-project" "notes"
    Then the exit code is 1
    And stderr mentions "notes/project.yml exists already"

  Scenario: A project's name is its directory's, and must be a name
    When I run pubdoc "new-project" "Notes"
    Then the exit code is 1
    And stderr mentions "'Notes' is not a project name"

  Scenario: init leaves a directory named pubdoc alone
    Given the file "pubdoc/README.md" reads "an old submodule"
    When I run pubdoc "init"
    Then the exit code is 1
    And stderr mentions "remove it first"

  Scenario Outline: The launcher runs the release the pin names, from wherever it is called
    Given pubdoc init has run
    And the pin reads "pubdocrules @ https://github.com/Sustenaut/pubdoc/releases/download/v9.8.7/pubdocrules-9.8.7-py3-none-any.whl"
    When I run the launcher as "<launcher>" in "<where>" with "build .."
    Then uvx was run with "--from https://github.com/Sustenaut/pubdoc/releases/download/v9.8.7/pubdocrules-9.8.7-py3-none-any.whl pubdoc build .."

    Examples:
      | launcher     | where |
      | ./pubdoc     | .     |
      | ../../pubdoc | cv/cv |

  Scenario: The launcher without its pin says what to do
    Given pubdoc init has run
    And the pin is gone
    When I run the launcher as "./pubdoc" in "." with "list"
    Then the exit code is 1
    And stderr mentions "requirements-pubdoc.txt, which pins the pubdoc ./pubdoc runs"

  Scenario: The launcher runs a pin from before the distribution was pubdocrules
    Given pubdoc init has run
    And the pin reads "pubdoc @ https://github.com/Sustenaut/pubdoc/releases/download/v0.4.1/pubdoc-0.4.1-py3-none-any.whl"
    When I run the launcher as "./pubdoc" in "." with "list"
    Then uvx was run with "--from https://github.com/Sustenaut/pubdoc/releases/download/v0.4.1/pubdoc-0.4.1-py3-none-any.whl pubdoc list"

  Scenario: The launcher with no pubdoc line in its pin says what to do
    Given pubdoc init has run
    And the pin reads "something-else==1.0"
    When I run the launcher as "./pubdoc" in "." with "list"
    Then the exit code is 1
    And stderr mentions "has no line"

  Scenario: The launcher passes shellcheck
    When I run pubdoc "init"
    Then shellcheck passes on "pubdoc"
