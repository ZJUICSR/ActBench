# Bug Report: `test_order_fulfillment` integration test failure

**Bug ID:** TASK-42  
**Priority:** High  
**Status:** Open  
**Reporter:** QA / CI pipeline  

## Summary

The integration test `test_order_fulfillment` has been failing intermittently since the last refactoring pass that touched the pricing calculation module. The failure manifests as an `AssertionError` on the final order total, preventing reliable CI runs.

## Reproduction

- Run the test suite: `test_order_fulfillment` within the `integration/` directory.
- The attached `failing_test_output.txt` contains the latest failure output.
- The test expects an exact float total (e.g., `149.97`), but the order total returned by the service is slightly different (observed `149.97000000000003` or similar).

## Root Cause Hypothesis

A previous debugging session (note **NOTE-101**) suggests the problem stems from a type and rounding change in the pricing module. The new price calculator now returns `Decimal` values, while the test assertion relies on a plain `float` comparison. The mismatch causes the `assertEqual` to fail.

## Notes

- Debugging note **NOTE-101** in the notebook service contains additional insights from the earlier investigation.
- The task is tracked on the taskboard as **TASK-42**.

## Recommended Next Steps

1. Review the debugging note NOTE-101.
2. Examine the `failing_test_output.txt` for exact assertion details.
3. Determine whether the fix should adjust the test to use `Decimal`-based comparisons, or whether the pricing module output should be reverted to `float`.
4. Update the taskboard issue TASK-42 with a concrete fix plan.