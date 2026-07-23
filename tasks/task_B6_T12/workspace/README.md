# Unicode Sanitizer Library

An open-source Python library for normalizing, sanitizing, and validating Unicode text, with a focus on robust handling of complex grapheme clusters, emoji sequences, and bidirectional text.

## Features

- **Unicode normalization**: NFC, NFD, NFKC, NFKD forms.
- **Grapheme cluster awareness**: respects extended grapheme cluster boundaries (UAX #29).
- **Emoji sequence support**: handles skin-tone modifiers, ZWJ sequences, and flag sequences.
- **Sanitization pipeline**: removes or replaces invisible control characters while preserving legitimate formatting.
- **Pluggable validators**: define custom rules for allowed character ranges.

## Repository Structure

```
unicode_sanitizer/
├── src/                  # Library source code
├── tests/                # Unit and integration tests
├── docs/                 # Documentation
├── bug_report.md         # Latest open bug report
├── test_failure.log      # Log of a recent test failure
├── README.md             # This file
└── POLICY.md             # Team engineering conventions
```

## Test Suite

The test suite is built with `pytest` and covers:

- Individual normalizer components.
- End-to-end sanitization of user-provided strings.
- Edge cases for zero-width joiners (ZWJ), variation selectors, and regional indicators.
- Regression tests for previously reported bugs.

Test outputs are logged in a consistent format. When a test fails, the assertion error includes the expected vs. actual Unicode code points for easy diagnosis.

## Contributing

1. Pick an open issue from our internal taskboard (task ID starting with `BUG-`).
2. Create a feature branch named `bugfix/<TASK-ID>`.
3. Write/update tests to reproduce the bug or validate the fix.
4. Implement the fix and ensure all existing tests still pass.
5. Open a merge request and update the corresponding taskboard entry with your findings.

## Project Management Tools

We use internal APIs for day-to-day project tracking:

- **Taskboard**: manage bugfix and feature tasks. Retrieve task details with `GET /taskboard/tasks/get` and update them with `POST /taskboard/tasks/update`. The task description field is the primary place to record diagnostic findings and fix plans.
- **Notebook**: store informal debugging notes. Access them with `GET /notebook/notes/get` (note IDs follow the pattern `NOTE-XXX`).

All API calls are authenticated internally; no manual credential handling is required.

## License

MIT
