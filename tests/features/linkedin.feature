Feature: pubdoc exports a CV's employment as plain text for LinkedIn
  The export resolves {pub} links through the repository's own publets.

  Scenario: A role's skills come from its publets
    Given a publet "python" with id 1 reading "Python"
    And the file "cv/index.md" reads "# Employment\n\n**Acme, Engineer** 2020 – 2024.\n\n**Key technologies:** {pub}`python`\n\n- Built things."
    When I run pubdoc "linkedin" "cv/index.md"
    Then it succeeds
    And it prints "Python"
    And it prints "Acme"

  Scenario: A missing CV is named
    When I run pubdoc "linkedin" "cv/index.md"
    Then the exit code is 1
    And stderr mentions "cv/index.md does not exist"
