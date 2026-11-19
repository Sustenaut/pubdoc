Feature: pubdoc corpus init makes the corpus versions are signed in, once
  It makes the corpus and its key with pub, names the key as corpus.key in
  the config, declares it in pubrules.json's signing_keys, keeps the store
  out of git and has pubsec back the key up. Run again, it changes nothing.
  When the config trusts a key this machine lacks, it stops and points to
  pubsec signing-key restore; around a key restored that way, it rebuilds
  the store with pub sign --restore-key, which must give the trusted key.
  pub and pubsec are stand-ins here.

  Background:
    Given the example project
    And the repository is a git work tree
    And publet's pub is installed
    And pubsec is a stand-in
    And the file "pubrules.json" reads:
      """
      {"kind": "content"}
      """

  Scenario: The repository's corpus, made, trusted, declared, ignored and backed up
    When I run pubdoc "corpus" "init" "--bitwarden-project" "11111111-2222-3333-4444-555555555555" "--backup-name" "pub-signing-key-demo"
    Then it succeeds
    And it prints "made the corpus corpus"
    And it prints "trusted in pubdoc.yml"
    And it prints "pubrules.json declares corpus/.publet/signing.key as pub-signing-key-demo"
    And it prints "backed up as pub-signing-key-demo"
    And "corpus/corpus.json" exists
    And "corpus/.publet/signing.key" exists
    And "pubdoc.yml" contains "corpus: {path: corpus, key: pub:sha2-256:"
    And "pubrules.json" contains "pub-signing-key-demo"
    And ".gitignore" contains "/corpus/.publet/"
    And pubsec was asked to "signing-key backup"

  Scenario: Run again, it makes nothing new
    Given pubdoc "corpus" "init" "--bitwarden-project" "11111111-2222-3333-4444-555555555555" "--backup-name" "pub-signing-key-demo" has run
    And the trusted key is remembered
    When I run pubdoc "corpus" "init"
    Then it succeeds
    And it does not print "made"
    And it prints "backed up as pub-signing-key-demo"
    And the trusted key is the one remembered

  Scenario: A key the config trusts but this machine lacks is restored, never made again
    Given pubdoc "corpus" "init" "--bitwarden-project" "11111111-2222-3333-4444-555555555555" "--backup-name" "pub-signing-key-demo" has run
    And the trusted key is remembered
    And the corpus's store is gone from this machine
    When I run pubdoc "corpus" "init"
    Then the exit code is 1
    And stderr mentions "is not on this machine: restore it, never make another: pubsec signing-key restore pub-signing-key-demo"
    And "corpus/.publet/signing.key" does not exist

  Scenario: Around a restored key, the store is rebuilt and must be the trusted key
    Given pubdoc "corpus" "init" "--bitwarden-project" "11111111-2222-3333-4444-555555555555" "--backup-name" "pub-signing-key-demo" has run
    And the trusted key is remembered
    And the corpus's store is gone from this machine, its key put back
    When I run pubdoc "corpus" "init" "--no-backup"
    Then it succeeds
    And it prints "rebuilt the store around corpus/.publet/signing.key"
    And pub was run in "corpus" with "sign --restore-key --principal=human --expect={trusted}"
    And the trusted key is the one remembered

  Scenario: A restored key that is not the trusted one is refused
    Given pubdoc "corpus" "init" "--bitwarden-project" "11111111-2222-3333-4444-555555555555" "--backup-name" "pub-signing-key-demo" has run
    And the corpus's store is gone from this machine, another key put in its place
    When I run pubdoc "corpus" "init" "--no-backup"
    Then the exit code is 1
    And stderr mentions "nothing was changed"

  Scenario: Without a declaration or the names to make one, it says what to give
    When I run pubdoc "corpus" "init"
    Then the exit code is 1
    And stderr mentions "give --bitwarden-project"

  Scenario: A project that names its own corpus gets its own, trusted in its project.yml
    Given in "job-applications/project.yml" "publish:" becomes "corpus: {path: corpus}\npublish:"
    When I run pubdoc "corpus" "init" "job-applications" "--bitwarden-project" "11111111-2222-3333-4444-555555555555" "--backup-name" "pub-signing-key-applications"
    Then it succeeds
    And "job-applications/corpus/.publet/signing.key" exists
    And "job-applications/project.yml" contains "corpus: {path: corpus, key: pub:sha2-256:"
    And ".gitignore" contains "/job-applications/corpus/.publet/"
    And "pubrules.json" contains "job-applications/corpus/.publet/signing.key"
