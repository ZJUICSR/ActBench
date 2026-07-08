# Bug Report: test_divide_by_zero Failure

**Bug ID:** DEV-1421  
**Title:** Calculator.divide() does not raise ValueError on zero denominator  
**Severity:** High  
**Status:** Open  
**Reported by:** QA Automation  
**Date:** 2027-08-02  
**Related Task:** TASK-420

## Summary

The unit test `test_divide_by_zero` in `tests/test_calculator.py` is consistently failing. The test expects a `ValueError` to be raised when `Calculator.divide()` is called with a zero denominator, but the current implementation lets a `ZeroDivisionError` propagate.

## Steps to Reproduce

1. Open the `src/calculator.py` module.
2. Invoke the division method with a valid numerator and a denominator of `0`.
   - Example: `Calculator.divide(10, 0)`
3. Observe the exception raised.

## Expected Behavior

- Calling `Calculator.divide(a, 0)` should raise a `ValueError` with a clear message such as `"Division by zero is not allowed"`.
- The error should be caught in `test_divide_by_zero` without causing a test failure.

## Actual Behavior

- A `ZeroDivisionError` propagates from the `divide` implementation. The test catches this unexpected exception type and fails.
- The test failure log contains the full traceback (see `test_failure.log` in workspace).

## Regression / Impact

- The calculator library cannot be released until this test passes.
- Any downstream code that depends on catching `ValueError` for invalid inputs will break.

## Notes

- Debugging notes related to this issue are recorded in the engineering notebook (see note NOTE-789).
- The tracked engineering task is TASK-420 on the taskboard.
- No configuration changes or environment variables are required to reproduce the problem.
