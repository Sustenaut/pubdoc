Feature: A layout can use a template of the repository's own
  A layout's template is a template pubdoc carries when it is a bare name
  (cv-sidebar), and a directory of the repository when it holds a /: a path
  relative to the project's directory (./templates/plain, ../templates/plain).
  check refuses one outside the repository, missing, without the template.yml
  Curvenote needs, or of another kind than Typst; build points each export at
  the directory where it is.

  Background:
    Given the example project
    And the repository is a git work tree
    And the file "templates/plain/template.yml" reads:
      """
      jtex: v1
      kind: typst
      title: Plain
      template: template.typ
      files:
        - template.typ
      """
    And the file "templates/plain/template.typ" reads "[-CONTENT-]"
    And in "job-applications/project.yml" "{part: letter, template: cv-sidebar," becomes "{part: letter, template: ../templates/plain,"

  Scenario: A local template checks
    When I run pubdoc "check"
    Then it succeeds
    And it prints "checked 1 project(s) with 2 doc(s): no problems"

  Scenario: build points the export at the local template, where it is
    When I run pubdoc "build" "job-applications/acme"
    Then it succeeds
    And "job-applications/acme/build/src/acme.letter/myst.yml" contains "template: ../../../../../templates/plain"
    And "job-applications/acme/build/src/shared.base-cv.cv/myst.yml" contains "template: ../../templates/cv-sidebar"
    And typst compiled "job-applications/acme/build/engineering/letter-pdf/main.typ" to "job-applications/acme/build/engineering/letter-pdf.pdf"

  Scenario: A template inside the project's own directory
    Given the file "job-applications/templates/plain/template.yml" reads "kind: typst"
    And in "job-applications/project.yml" "template: ../templates/plain," becomes "template: ./templates/plain,"
    When I run pubdoc "check"
    Then it succeeds

  Scenario Outline: A local template that cannot be built with is refused
    Given in "job-applications/project.yml" "template: ../templates/plain," becomes "template: <template>,"
    And the file "templates/other/template.yml" reads "kind: tex"
    And the file "templates/bare/template.typ" reads "[-CONTENT-]"
    When I run pubdoc "check"
    Then the exit code is 1
    And stderr mentions "job-applications/project.yml: layouts.letter-pdf.template: <message>"

    Examples:
      | template             | message                                                                  |
      | ../templates/nothing | no directory templates/nothing                                           |
      | ../templates/bare    | templates/bare has no template.yml, which Curvenote needs                |
      | ../templates/other   | templates/other/template.yml is a tex template; pubdoc builds Typst templates |
      | ../../outside        | ../../outside is outside the repository                                  |

  Scenario: A template that is neither a name nor a relative path is refused
    Given in "job-applications/project.yml" "template: ../templates/plain," becomes "template: /templates/plain,"
    When I run pubdoc "check"
    Then the exit code is 1
    And stderr mentions "'/templates/plain' is neither a template name nor a path relative to the project"

  Scenario: A local template makes a PDF, and nothing else
    Given in "job-applications/project.yml" "template: ../templates/plain, format: pdf" becomes "template: ../templates/plain, format: text"
    When I run pubdoc "check"
    Then the exit code is 1
    And stderr mentions "layouts.letter-pdf.format: ../templates/plain makes pdf, not text"
