# Integration Health Alert Workspace

This workspace provides the context and instructions for responding to an integration health alert.

## Current Alert

We received a health alert concerning our payment-gateway integration:

- **Integration ID**: INTV-204
- **Name**: Payment Gateway

## Task

1. Retrieve the current status of integration INTV-204 using the **integrations** service (`/integrations/items/get`).
2. Review the standard notification process defined in `policy.md`.
3. Look up the integration owner in the company **directory** (`/directory/search`).
4. Send a health notification to the owner via the **integrations** notification endpoint (`/integrations/notify`) according to the policy.

All mock API services required for this task (integrations, directory) are available and ready to use. Please follow the notification policy exactly and confirm once the notification has been sent.
