Feature: pubdoc init sets a repository up to run this release
  `init` writes requirements-pubdoc.txt, which pins this release's wheel in
  the form pubrules's nightly moves, and ./pubdoc, which names no release and
  runs the one that file pins with uvx. Builds write only into each doc's
  build/, which ignores itself, so init touches no .gitignore.
  `new-project` starts a project: a project.yml and a first doc that check.

  Background:
    Given a scratch directory
    And the program under test is "pubdoc"

  Scenario: init writes the launcher and its pin
    Given a file ".gitignore" holding "*.pdf"
    When I run "pubdoc init"
    Then it succeeds
    And the file "pubdoc" can be run
    And the file "pubdoc" includes "uvx --from"
    And the file "pubdoc" does not include "releases/download"
    And "requirements-pubdoc.txt" is one release wheel pin of pubdoc
    And the file ".gitignore" holds "*.pdf"

  Scenario: new-project starts a project that checks
    When I run "pubdoc new-project notes --purpose 'Meeting notes'"
    And I run "pubdoc check"
    Then it succeeds
    And the file "notes/project.yml" includes "purpose: Meeting notes"
    And the file "notes/draft/main.md" exists

  Scenario: new-project leaves an existing project alone
    Given a file "notes/project.yml" holding "project: notes"
    When I run "pubdoc new-project notes"
    Then the exit code is 1
    And stderr mentions "notes/project.yml exists already"

  Scenario: A project's name is its directory's, and must be a name
    When I run "pubdoc new-project Notes"
    Then the exit code is 1
    And stderr mentions "'Notes' is not a project name"

  Scenario: init leaves a directory named pubdoc alone
    Given a file "pubdoc/README.md" holding "an old submodule"
    When I run "pubdoc init"
    Then the exit code is 1
    And stderr mentions "remove it first"

  Scenario Outline: The launcher runs the release the pin names, from wherever it is called
    Given pubdoc init has run
    And a stand-in "uvx"
    And a file "requirements-pubdoc.txt" holding "pubdoc @ https://github.com/Sustenaut/pubdoc/releases/download/v9.8.7/pubdoc-9.8.7-py3-none-any.whl"
    And a file "cv/cv/cv.md" holding "# CV"
    When from "<where>" I run "<launcher> build .."
    Then it succeeds
    And "uvx" was run with "--from https://github.com/Sustenaut/pubdoc/releases/download/v9.8.7/pubdoc-9.8.7-py3-none-any.whl pubdoc build .."

    Examples:
      | launcher     | where |
      | ./pubdoc     | .     |
      | ../../pubdoc | cv/cv |

  Scenario: The launcher without its pin says what to do
    Given pubdoc init has run
    And a stand-in "uvx"
    And the file "requirements-pubdoc.txt" is removed
    When I run "./pubdoc list"
    Then the exit code is 1
    And stderr mentions "requirements-pubdoc.txt, which pins the pubdoc ./pubdoc runs"
    And "uvx" was not run

  Scenario: The launcher with no pubdoc line in its pin says what to do
    Given pubdoc init has run
    And a stand-in "uvx"
    And a file "requirements-pubdoc.txt" holding "something-else==1.0"
    When I run "./pubdoc list"
    Then the exit code is 1
    And stderr mentions "has no line"
    And "uvx" was not run

  Scenario: The launcher passes shellcheck
    Given shellcheck is installed
    And pubdoc init has run
    When I run "shellcheck --severity=style pubdoc"
    Then it succeeds
