Feature: pubdoc check validates every document project in a repository
  A project is a directory holding a project.yml. `check` finds every one
  git knows of (or every one on disk outside a git work tree), checks it
  against the schema pubdoc carries, then checks every name it refers to:
  parts, templates, exporters, layouts, variants, checkers, places, shared
  parts, each doc's required parts, and that a doc.yml only narrows. The
  example project is job-applications: a letter and a CV that starts from
  shared/base-cv, variants engineering and research, docs acme and globex.

  Background:
    Given a scratch directory
    And the program under test is "pubdoc"
    And the example project

  Scenario: The example project has no problems
    When I run "pubdoc check"
    Then it succeeds
    And it prints "checked 1 project(s) with 2 doc(s): no problems"

  Scenario: Checkers and places named but not implemented yet are noted, not failed
    When I run "pubdoc check"
    Then it succeeds
    And it prints "note: checker 'spelling' is not implemented yet"
    And it prints "note: place 'storage' is not implemented yet"

  Scenario: check from inside a doc checks the project it is in
    When from "job-applications/acme" I run "pubdoc check"
    Then it succeeds
    And it prints "checked 1 project(s) with 2 doc(s)"

  Scenario: Without a project there is nothing to check
    Given the file "job-applications/project.yml" is removed
    When I run "pubdoc check job-applications"
    Then the exit code is 1
    And stderr mentions "no project.yml in job-applications or below it"

  Scenario: In a git work tree, check finds the projects git knows of, wherever they are
    Given a git repository
    And a file "nested/deeper/notes/project.yml" holding:
      """
      project: notes
      purpose: Notes
      parts: {note: {required: true}}
      variants: {all: {audience: Everyone}}
      layouts: {note-pdf: {part: note, template: lapreprint-typst, format: pdf}}
      """
    And a file "nested/deeper/notes/one/note.md" holding "# One"
    And a file "ignored/project.yml" holding "not: [valid"
    And a file ".gitignore" holding "/ignored/"
    When I run "pubdoc check"
    Then it succeeds
    And it prints "checked 2 project(s) with 3 doc(s): no problems"

  Scenario: A project.yml that is not YAML is named
    Given a file "job-applications/project.yml" holding "parts: [unclosed"
    When I run "pubdoc check"
    Then the exit code is 1
    And stderr mentions "job-applications/project.yml: is not valid YAML"

  Scenario Outline: A project.yml that breaks the schema says where
    Given in "job-applications/project.yml" "<old>" becomes "<new>"
    When I run "pubdoc check"
    Then the exit code is 1
    And stderr mentions "job-applications/project.yml: <message>"

    Examples:
      | old                                  | new                                                       | message                                                      |
      | purpose: Win                         | aim: Win                                                  | 'purpose' is a required property                             |
      | exporter: linkedin, format: text     | exporter: linkedin, template: cv-sidebar, format: text    | layouts.cv-linkedin: needs a template or an exporter, and not both |
      | \n    human: {reviewers: 1}          | \n    # no sign-off                                          | review.1: needs automatic checkers, a human sign-off, or both |
      | research: {audience                  | Research: {audience                                       | variants: 'Research' is not a name                           |
      | format: text                         | format: docx                                              | layouts.cv-linkedin.format: 'docx' is not one of             |
      | readers: named                       | readers: everyone                                         | publish.0.readers: 'everyone' is not one of                  |
      | starts-from: shared/base-cv          | starts-from: base-cv                                      | parts.cv.starts-from: 'base-cv' is not shared/<name>         |
      | contributors: [schryer]              | contributors: [schryer]\n  editors: [schryer]              | roles: Additional properties are not allowed ('editors'      |

  Scenario Outline: A name project.yml refers to must exist
    Given in "job-applications/project.yml" "<old>" becomes "<new>"
    When I run "pubdoc check"
    Then the exit code is 1
    And stderr mentions "job-applications/project.yml: <message>"

    Examples:
      | old                                | new                                | message                                                                  |
      | {part: letter,                     | {part: lettr,                      | layouts.letter-pdf.part: no part 'lettr' (cv, letter, webpage)           |
      | template: cv-sidebar               | template: cv-side                  | layouts.letter-pdf.template: no template 'cv-side' (charged-ieee, cv-sidebar, lapreprint-typst) |
      | exporter: linkedin                 | exporter: twitter                  | layouts.cv-linkedin.exporter: no exporter 'twitter' (linkedin)           |
      | exporter: linkedin, format: text   | exporter: linkedin, format: pdf    | layouts.cv-linkedin.format: linkedin makes text, not pdf                 |
      | part: cv, template: cv-sidebar, format: pdf | part: cv, template: cv-sidebar, format: html | layouts.cv-pdf.format: cv-sidebar makes pdf, not html     |
      | cv-pdf, cv-linkedin]               | cv-pdf, cv-web]                    | publish[0].layouts: no layout 'cv-web'                                   |
      | readers: named                     | variants: [marketing]\n    readers: named | publish[0].variants: no variant 'marketing' (engineering, research) |
      | place: storage                     | place: dropbox                     | publish[0].place: no place 'dropbox' (pub, storage)                      |
      | spelling, private-info             | spelling, grammar                  | review[0].automatic: no checker 'grammar'                                |
      | starts-from: shared/base-cv        | starts-from: shared/base           | parts.cv.starts-from: no shared/base/cv.md                               |
      | human: {reviewers: 1}              | human: {reviewers: 2}              | review[1].human: needs 2 reviewers, and roles.reviewers names 1          |
      | - step: approval                   | - step: checks                     | review[1].step: 'checks' is named twice                                  |

  Scenario: Every doc supplies each required part, for each of its variants
    Given the file "job-applications/globex/letter.md" is removed
    When I run "pubdoc check"
    Then the exit code is 1
    And stderr mentions "job-applications/globex: no letter.md or letter.engineering.md for required part 'letter' in variant 'engineering'"

  Scenario: A required part with no file and no shared part is missing
    Given the file "job-applications/shared/base-cv/cv.md" is removed
    And the file "job-applications/shared/base-cv/cv.research.md" is removed
    When I run "pubdoc check"
    Then the exit code is 1
    And stderr mentions "job-applications/acme: no cv.md or cv.engineering.md for required part 'cv' in variant 'engineering', and shared part shared/base-cv has none"

  Scenario: A variant override of no variant is a mistake
    Given a file "job-applications/acme/cv.reserch.md" holding "# CV"
    When I run "pubdoc check"
    Then the exit code is 1
    And stderr mentions "job-applications/acme/cv.reserch.md: no variant 'reserch' (engineering, research)"
