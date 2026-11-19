Feature: A doc.yml can only narrow its project
  A doc may keep fewer variants and layouts than its project, publish less
  to fewer readers, and add review checkers, reviewers or steps. It can
  never drop or loosen a review step, nor publish more than project.yml
  does. In the example project, globex's doc.yml keeps the engineering
  variant and the two PDF layouts.

  Background:
    Given a scratch directory
    And the program under test is "pubdoc"
    And the example project

  Scenario: A doc that narrows and tightens checks
    Given a file "job-applications/globex/doc.yml" holding:
      """
      variants: [engineering]
      layouts: [letter-pdf, cv-pdf]
      review:
        - step: checks
          automatic: [build, links, spelling, private-info]
        - step: legal
          automatic: [private-info]
        - step: approval
          human: {reviewers: 1}
          automatic: [build]
      publish:
        - place: storage
          layouts: [cv-pdf]
          variants: [engineering]
          readers: named
      """
    When I run "pubdoc check"
    Then it succeeds

  Scenario Outline: A doc.yml that loosens its project is refused
    Given a file "job-applications/globex/doc.yml" holding "<doc>"
    When I run "pubdoc check"
    Then the exit code is 1
    And stderr mentions "job-applications/globex/doc.yml: <message>"

    Examples:
      | doc                                                                                                   | message                                                          |
      | variants: [engineering, marketing]                                                                    | variants: no variant 'marketing' (engineering, research) in project.yml |
      | layouts: [letter-web]                                                                                 | layouts: no layout 'letter-web'                                  |
      | review: [{step: checks, automatic: [build, links, spelling, private-info]}]                           | review: drops the project's review step 'approval'               |
      | review: [{step: checks, automatic: [build]}, {step: approval, human: {reviewers: 1}}]                 | review: step 'checks' drops checkers links, private-info, spelling |
      | review: [{step: checks, automatic: [build, links, spelling, private-info]}, {step: approval, automatic: [build]}] | review: step 'approval' needs 1 human reviewers in project.yml |
      | review: [{step: approval, human: {reviewers: 1}}, {step: checks, automatic: [build, links, spelling, private-info]}] | review: moves the project's review step 'approval' before an earlier one |
      | publish: [{place: storage, layouts: [cv-pdf], readers: public}]                                       | publish[0]: widens what project.yml publishes to 'storage': public readers (project.yml: named) |
      | publish: [{place: pub, layouts: [cv-pdf], readers: named}]                                            | publish[0].place: project.yml does not publish to 'pub'          |
      | {layouts: [cv-pdf], publish: [{place: storage, layouts: [cv-linkedin], readers: named}]}              | publish[0].layouts: no layout 'cv-linkedin' (cv-pdf)             |
      | title: Globex                                                                                         | Additional properties are not allowed ('title'                   |
      | variants: engineering                                                                                 | variants: 'engineering' is not of type 'array'                   |

  Scenario: A publication narrower than the project's in one way but wider in another is refused
    Given in "job-applications/project.yml" "    readers: named" becomes "    variants: [engineering]\n    readers: named"
    And a file "job-applications/acme/doc.yml" holding "publish: [{place: storage, layouts: [cv-pdf], variants: [research], readers: named}]"
    When I run "pubdoc check"
    Then the exit code is 1
    And stderr mentions "job-applications/acme/doc.yml: publish[0]: widens what project.yml publishes to 'storage': variants research"
