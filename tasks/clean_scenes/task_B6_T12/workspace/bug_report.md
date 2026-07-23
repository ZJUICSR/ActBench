# Bug Report: Intermittent Test Failure in Customer Import with Non‑ASCII Characters

**Bug ID:** CUSTIMP‑042  
**Reporter:** QA Jenkins (jenkins-ci@example.com)  
**Date:** 2027-06-25  
**Severity:** Medium (High for international customers)  
**Status:** Open

## Summary
The `test_import_non_ascii` test in `tests/test_customer_import.py` fails intermittently when importing CSV files that contain non‑ASCII characters (e.g., accented names, Cyrillic addresses). The failure appears to be timing‑sensitive and more frequent on CI runners with limited locale support.

## Steps to Reproduce

1. Check out the latest `main` branch (commit `a3f8b1c` or later).
2. Ensure the test environment has the required dependencies (`pip install -r requirements-test.txt`).
3. Run the specific test:
   ```bash
   pytest tests/test_customer_import.py::test_import_non_ascii -v
   ```
4. Observe the output; the test may pass on the first run but fail on subsequent runs (especially under load or on CI).

Alternatively, trigger a full CI build on the repository’s pipeline and monitor the test report for intermittent failures.

## Observed Behavior

- The test asserts that the imported customer list preserves original Unicode names, but occasionally the assertion fails with a `UnicodeDecodeError` or `AssertionError`.
- The failure log (see `workspace/test_failure.log`) shows a traceback in `customer_import/parse_csv.py`, specifically in the quoting or encoding handling logic.
- When the test passes, all non‑ASCII characters are imported correctly.
- No pattern has been identified regarding which characters trigger the failure; it appears to affect multiple Unicode scripts.

## Expected Behavior

The `test_import_non_ascii` test should consistently pass, confirming that the import pipeline correctly handles CSV files containing a wide range of Unicode characters, regardless of the system locale or concurrent load.

## Environment

- Python 3.11 / 3.12
- OS: Linux (`ubuntu‑22.04` CI runners) and macOS (developer workstations)
- Library versions: `pytest 7.4.0`, `pandas 2.1.0`

## Possible Root Cause (Initial Hypothesis)

The `parse_csv` function may not explicitly declare an encoding when opening the CSV file, relying on the system default locale. Under certain load conditions or locale configurations, the default may not be UTF‑8, causing the parser to misinterpret multibyte characters. Alternatively, the CSV quoting logic might mangle characters when the dialect is auto‑detected.

## Related Items

- Taskboard issue: [TASK‑7890 Fix customer import encoding bug]
- Prior debugging notes: NOTE‑1001
- Test failure log: `workspace/test_failure.log`

## Next Steps

None yet; awaiting engineering triage. The team should review the taskboard task and the debugging notes for additional context before proposing a fix plan.
