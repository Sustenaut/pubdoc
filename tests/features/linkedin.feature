Feature: pubdoc exports a CV's employment as plain text for LinkedIn
  The export resolves {pub} links through the repository's own publets.

  Background:
    Given a scratch directory
    And the program under test is "pubdoc"

  Scenario: A role's skills come from its publets
    Given a publet "python" with id 1 reading "Python"
    And a file "cv/index.md" holding:
      """
      # Employment

      **Acme, Engineer** 2020 – 2024.

      **Key technologies:** {pub}`python`

      - Built things.
      """
    When I run "pubdoc linkedin cv/index.md"
    Then it succeeds
    And it prints "Python"
    And it prints "Acme"

  Scenario: A missing CV is named
    When I run "pubdoc linkedin cv/index.md"
    Then the exit code is 1
    And stderr mentions "cv/index.md does not exist"
