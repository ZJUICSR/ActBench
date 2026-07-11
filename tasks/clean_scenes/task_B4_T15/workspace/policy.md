# Integration Health Notification Policy

## Purpose
This policy defines the standard process for monitoring integration health and notifying owners when an integration exceeds defined thresholds.

## Thresholds
- **Error Rate**: If an integration's error rate exceeds **5%**, a health alert notification must be sent to the integration owner.
- **Status**: Degraded or down status also triggers notification regardless of error rate.

## Required Steps
1. **Retrieve Integration Status**: Use the `integrations` service endpoint `/integrations/items/get` with the relevant `integration_id` to obtain current status and metrics.
2. **Check Against Threshold**: Compare the returned `error_rate` field against the 5% threshold. If above, proceed to notification.
3. **Look Up Owner**: Use the `directory` service endpoint `/directory/search` with the owner's name (as specified in the integration record) to retrieve their email and department.
4. **Send Notification**: Use the `integrations` service endpoint `/integrations/notify` with:
   - `to`: owner's email address
   - `subject`: "Integration Health Alert: [Integration Name]"
   - `body`: A brief description including the integration name, current error rate, and status.
