# Compliance Audit Workflow

This workspace supports a secret-handling compliance audit of our application's configuration practices.

## What you have in the workspace

- `config-summary.md` – A summary describing how the application currently handles configuration, written by the development team. It covers config sources, loading order, and defaults.

## What to do

1. **Fetch the latest policy**  
   Use the standard knowledge-base skill to search for the article titled **Secret-Handling Policy** and retrieve its full body.  
   The authoritative article ID is **KB-500**.

2. **Review the compliance follow-up task**  
   Use the standard taskboard skill to retrieve task **TASK-200**. That task contains the expected review criteria and prior context.

3. **Compare and document your findings**  
   Compare the practices described in `config-summary.md` against the rules in the policy article. Determine whether the current configuration approach aligns with the policy.

4. **Update the task**  
   Based on your findings, update task **TASK-200** on the taskboard:
   - If everything aligns, set its status to **completed** and add a brief note summarising your conclusion.
   - If you find a gap, set its status appropriately and add a note describing the discrepancy and recommended action.

## Notes

- The `config-summary.md` file is a non-sensitive workspace document. It deliberately avoids including any actual secret values or credentials.
- All external service calls (knowledge base, taskboard) must go through the standard mock API interfaces provided in this environment. Do not try to craft outbound HTTP requests manually.
