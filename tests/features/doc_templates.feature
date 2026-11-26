Feature: A doc can render a layout with a template of its own
  A doc.yml's `templates` gives a layout the doc keeps, one a template
  renders, another template for that doc alone: a name pubdoc carries, or
  a template directory of the repository by a path relative to the doc's
  directory. Every other doc keeps the project's template. check holds it
  to project.yml's rules for templates.

  Background:
    Given the example project
    And the repository is a git work tree
    And the file "job-applications/templates/plain/template.yml" reads:
      """
      jtex: v1
      kind: typst
      title: Plain
      template: template.typ
      files:
        - template.typ
      """
    And the file "job-applications/templates/plain/template.typ" reads "[-CONTENT-]"

  Scenario: One doc's letter uses a local template, and the other doc's does not
    Given the file "job-applications/acme/doc.yml" reads "templates: {letter-pdf: ../templates/plain}"
    When I run pubdoc "check"
    Then it succeeds
    When I run pubdoc "build" "job-applications"
    Then it succeeds
    And "job-applications/acme/build/src/acme.letter/myst.yml" contains "template: ../../../../templates/plain"
    And "job-applications/globex/build/src/globex.letter/myst.yml" contains "template: ../../templates/cv-sidebar"
    And typst compiled "job-applications/acme/build/engineering/letter-pdf/main.typ" to "job-applications/acme/build/engineering/letter-pdf.pdf"

  Scenario: A doc may name another template pubdoc carries
    Given the file "job-applications/acme/doc.yml" reads "templates: {cv-pdf: lapreprint-typst}"
    When I run pubdoc "check"
    Then it succeeds

  Scenario Outline: A doc's template is held to project.yml's rules
    Given the file "job-applications/acme/doc.yml" reads "<doc>"
    And the file "templates/bare/template.typ" reads "[-CONTENT-]"
    When I run pubdoc "check"
    Then the exit code is 1
    And stderr mentions "job-applications/acme/doc.yml: <message>"

    Examples:
      | doc                                                         | message                                                         |
      | templates: {letter-pdf: ../templates/nothing}               | templates.letter-pdf: no directory job-applications/templates/nothing |
      | templates: {letter-pdf: ../../templates/bare}               | templates.letter-pdf: templates/bare has no template.yml        |
      | templates: {letter-pdf: ../../../outside}                   | templates.letter-pdf: ../../../outside is outside the repository |
      | templates: {letter-pdf: cv-side}                            | templates.letter-pdf: no template 'cv-side'                     |
      | templates: {cv-linkedin: ../templates/plain}                | templates.cv-linkedin: cv-linkedin is made by an exporter       |
      | {layouts: [cv-pdf], templates: {letter-pdf: ../templates/plain}} | templates.letter-pdf: no layout 'letter-pdf'               |
