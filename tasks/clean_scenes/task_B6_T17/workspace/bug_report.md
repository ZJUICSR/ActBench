# Bug Report: Division rounding error in calc.divide

**Issue ID**: BUG-001  
**Reported by**: Developer  
**Date**: 2026-06-23  
**Priority**: High  

## Summary

The `divide` function in `src/calc.py` produces incorrect results when dividing float numbers. The implementation uses integer floor division (`//`) which truncates the result toward minus infinity rather than performing true mathematical division and rounding the result to the expected precision.

## Steps to Reproduce
1. Open a Python shell or run the existing test suite.
2. Call `calc.divide(5, 3)` with both arguments as floats (e.g., `5.0` and `3.0`).
3. Observe the returned value.

## Expected Behavior
`divide` should return the quotient as a float rounded to two decimal places. The test in `test_calc.py` (`test_divide_floats`) expects `1.67`.

## Actual Behavior
The current implementation returns `1.0` because `5 // 3` evaluates to `1` (integer floor division). The fractional part is completely discarded.

## Impact
The calculator module cannot correctly divide float inputs; the `test_divide_floats` test fails, blocking the build.

## Suggested Fix
Replace the `//` operator with `/` inside the `divide` function and apply proper rounding (e.g., using `round(result, 2)`) to align with the test expectations. Confirm that all other arithmetic functions remain unaffected.
