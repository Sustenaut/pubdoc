Feature: Approving a doc makes a signed version, its renders in storage
  approve builds each variant of a doc, uploads every render to the
  project's storage tenant, has pub sign a version publet for it in the
  repository's corpus, and records the version in <doc>/versions/versions.yml.
  Each doc and variant is one lineage, so a new version supersedes the last.
  verify checks every versions.yml against the corpus's signed objects.
  pub and storage are stand-ins here.

  Background:
    Given the example project
    And the repository is a git work tree
    And publet's pub is installed
    And storage takes the tenant "documents" for the repository
    And a corpus at "corpus" with its signing key
    And "schryer" approves
    And everything is committed

  Scenario: approve signs a version of each variant, its renders uploaded
    When I run pubdoc "approve" "job-applications/acme"
    Then it succeeds
    And it prints "approved version 1 of job-applications/acme (engineering)"
    And it prints "approved version 1 of job-applications/acme (research)"
    And "job-applications/acme" records version 1 of "engineering", approved by "schryer"
    And "job-applications/acme" records version 1 of "research", approved by "schryer"
    And "job-applications/acme"'s renders are in storage with their checksums
    And storage holds 6 files
    And pub was run in "corpus" with "publish doc.job-applications.acme.engineering"
    And "corpus/publets/doc.job-applications.acme.research/publet.json" contains "DOC-ACMERE-"
    And "corpus/publets/doc.job-applications.acme.research/publet.json" contains "shared/base-cv/cv.research.md"
    And "job-applications/acme/versions/versions.yml" contains "corpus: ../../../corpus"

  Scenario: A doc's only variant, and its PDF shown last for review-builder
    When I run pubdoc "approve" "job-applications/globex" "--show" "cv-pdf"
    Then it succeeds
    And it prints "/documents/f/"
    And it prints "globex-engineering-cv-pdf-v1.pdf"
    And storage holds 2 files

  Scenario: The next version supersedes the last
    Given pubdoc "approve" "job-applications/globex" has run
    And everything is committed
    When I run pubdoc "approve" "job-applications/globex"
    Then it succeeds
    And "job-applications/globex" records version 2 of "engineering", approved by "schryer"
    And "job-applications/globex"'s version 2 supersedes version 1

  Scenario: A version rebuilt from an earlier commit keeps that commit and date
    When I run pubdoc "approve" "job-applications/globex" "--date" "2026-09-22" "--rebuilt-from" "3f9e1c2"
    Then it succeeds
    And typst was asked for the creation time 1790035200
    And "job-applications/globex/versions/versions.yml" contains "approved: '2026-09-22'"
    And "job-applications/globex/versions/versions.yml" contains "rebuilt_from: 3f9e1c2"
    And "corpus/publets/doc.job-applications.globex.engineering/publet.json" contains "rebuilt from the sources of commit 3f9e1c2"

  Scenario: Only the named variant
    When I run pubdoc "approve" "job-applications/acme" "--variant" "research"
    Then it succeeds
    And it does not print "(engineering)"
    And storage holds 3 files

  Scenario: approve refuses uncommitted changes
    Given the file "job-applications/globex/letter.md" reads "# Changed"
    When I run pubdoc "approve" "job-applications/globex"
    Then the exit code is 1
    And stderr mentions "commit these first"
    And storage holds 0 files

  Scenario: Only a reviewer the project names may approve
    Given "someone" approves
    When I run pubdoc "approve" "job-applications/globex"
    Then the exit code is 1
    And stderr mentions "someone is not one of job-applications/project.yml's reviewers (schryer)"

  Scenario: Without a tenant there is nowhere to put the renders
    Given the file "pubdoc.yml" reads "corpus: {path: corpus}"
    And everything is committed
    When I run pubdoc "approve" "job-applications/globex"
    Then the exit code is 1
    And stderr mentions "job-applications names no storage tenant"

  Scenario: A project's own tenant and corpus override the repository's
    Given in "job-applications/project.yml" "publish:" becomes "storage: {tenant: applications}\ncorpus: {path: corpus}\npublish:"
    And a corpus at "job-applications/corpus" with its signing key
    And the file ".gitignore" reads "/job-applications/corpus/.publet/\n/corpus/.publet/"
    And everything is committed
    When I run pubdoc "approve" "job-applications/globex"
    Then it succeeds
    And it prints "/applications/f/"
    And "job-applications/corpus/corpus.lock" exists
    And "corpus/corpus.lock" does not exist

  Scenario: Without a corpus there is nothing to sign with
    Given the repository's corpus is at "elsewhere"
    And everything is committed
    When I run pubdoc "approve" "job-applications/globex"
    Then the exit code is 1
    And stderr mentions "no corpus at elsewhere"

  Scenario Outline: approve needs publet's pub 0.4
    Given pub says it is "<first line>"
    When I run pubdoc "approve" "job-applications/globex"
    Then the exit code is 1
    And stderr mentions "pubdoc drives pub 0.4"

    Examples:
      | first line |
      | pub 0.3.0  |
      | pub 1.0.0  |

  Scenario: versions lists a doc's versions, newest first
    Given pubdoc "approve" "job-applications/globex" has run
    And everything is committed
    And pubdoc "approve" "job-applications/globex" has run
    When I run pubdoc "versions" "job-applications/globex"
    Then it succeeds
    And it prints "engineering v2"
    And it prints "engineering v1"
    And it prints "by schryer"

  Scenario: A doc with no versions says so
    When I run pubdoc "versions" "job-applications/globex"
    Then it succeeds
    And it prints "job-applications/globex has no versions yet"

  Scenario: fetch downloads a version's render, checked against its publet
    Given pubdoc "approve" "job-applications/globex" has run
    When I run pubdoc "fetch" "job-applications/globex" "1" "--layout" "cv-pdf" "--out" "fetched"
    Then it succeeds
    And "fetched/globex-engineering-cv-pdf-v1.pdf" exists

  Scenario: fetch refuses a render that is not the one recorded
    Given pubdoc "approve" "job-applications/globex" has run
    And storage serves other bytes for "cv-pdf" of "job-applications/globex"
    When I run pubdoc "fetch" "job-applications/globex" "--layout" "cv-pdf"
    Then the exit code is 1
    And stderr mentions "is not the file recorded"

  Scenario: verify accepts versions that agree with their signed publets
    Given pubdoc "approve" "job-applications/acme" has run
    When I run pubdoc "verify" "--remote"
    Then it succeeds
    And it prints "verified 1 doc(s)' versions against 1 signed corpus(es), and every render in storage"

  Scenario: verify finds a versions.yml that no longer says what its publet does
    Given pubdoc "approve" "job-applications/globex" has run
    And in "job-applications/globex/versions/versions.yml" "approved_by: schryer" becomes "approved_by: someone"
    When I run pubdoc "verify"
    Then the exit code is 1
    And stderr mentions "says approved_by 'someone', its publet 'schryer'"

  Scenario: verify finds a changed signed object
    Given pubdoc "approve" "job-applications/globex" has run
    And every object in "corpus/objects" has a byte more
    When I run pubdoc "verify"
    Then the exit code is 1
    And stderr mentions "does not hash to its name"

  Scenario: verify --remote finds a render storage no longer holds as recorded
    Given pubdoc "approve" "job-applications/globex" has run
    And storage serves other bytes for "cv-pdf" of "job-applications/globex"
    When I run pubdoc "verify" "--remote"
    Then the exit code is 1
    And stderr mentions "cv-pdf"
    And stderr mentions "is not the file recorded"

  Scenario: verify holds the corpus to the key the repository trusts
    Given pubdoc "approve" "job-applications/globex" has run
    And the repository trusts the key "pub:sha2-256:aaaa"
    When I run pubdoc "verify"
    Then the exit code is 1
    And stderr mentions "and the project trusts pub:sha2-256:aaaa"

  Scenario: preview's Accept button approves the variant and shows the render
    When I run pubdoc "preview" "job-applications/globex" "engineering" "cv-pdf"
    Then it succeeds
    And "job-applications/globex/build/review-builder.yaml" contains "- --show"
    And "job-applications/globex/build/review-builder.yaml" contains "- approve"
    And "job-applications/globex/build/versions" does not exist

  Scenario: verify takes the corpus from the project's settings, not from versions.yml
    Given pubdoc "approve" "job-applications/globex" has run
    And a corpus at "forged" with its signing key
    And in "job-applications/globex/versions/versions.yml" "corpus: ../../../corpus" becomes "corpus: ../../../forged"
    When I run pubdoc "verify"
    Then the exit code is 1
    And stderr mentions "names the corpus '../../../forged', and the project's is corpus"

  Scenario: verify says which key it accepted when none is named
    Given pubdoc "approve" "job-applications/globex" has run
    And everything is committed
    When I run pubdoc "verify"
    Then it succeeds
    And it prints "note: corpus is signed by pub:sha2-256:"

  Scenario Outline: The storage token goes only to the project's tenant: <case>
    Given pubdoc "approve" "job-applications/globex" has run
    And the newest "cv-pdf" render of "job-applications/globex" is recorded at "<url>"
    When I run pubdoc "fetch" "job-applications/globex" "--layout" "cv-pdf"
    Then the exit code is 1
    And stderr mentions "is not in the project's storage tenant"
    And storage was asked for nothing more

    Examples:
      | case              | url                                                  |
      | another host      | https://example.org/documents/f/abc/x.pdf            |
      | another tenant    | {storage}/documents-other/f/abc/x.pdf                |
      | a user in the URL | http://someone@{host}/documents/f/abc/x.pdf          |
      | another port      | http://127.0.0.1:1/documents/f/abc/x.pdf             |
      | a .. segment      | {storage}/documents/../other/f/abc/x.pdf             |

  Scenario: verify checks each version's sources against its commit
    Given the file "job-applications/globex/letter.md" reads "# Not committed"
    And pubdoc "approve" "job-applications/globex" "--allow-dirty" has run
    And everything is committed
    When I run pubdoc "verify"
    Then the exit code is 1
    And stderr mentions "job-applications/globex/letter.md at commit"
    And stderr mentions "is not the file it was built from"

  Scenario: verify finds a version missing from versions.yml
    Given pubdoc "approve" "job-applications/globex" has run
    And everything is committed
    And pubdoc "approve" "job-applications/globex" has run
    And the newest version is dropped from "job-applications/globex"'s versions.yml
    When I run pubdoc "verify"
    Then the exit code is 1
    And stderr mentions "engineering's newest version is not the corpus's"
