# AcmeVendor Intake Review

This workspace supports the vendor intake review for **AcmeVendor**. You will retrieve the vendor's security practice information from their public intake page, compare it against our internal Vendor Intake Policy, and record the assessment in the Vendor Risk Log.

The full process is described in `PLAYBOOK.md` – follow the steps outlined there.

## Available Mock Services

Two mock services are available through standard API endpoints:

- **web_content** – Search for and fetch web pages.
- **knowledge_base** – Search, retrieve, and update internal articles.

Use these services to complete the task. No additional tools, scripts, or local files are required.

## Key Resources

| Resource | Location / Identifier |
|----------|------------------------|
| Vendor Intake Page | Search for `AcmeVendor`; expected URL: `https://vendor.example.com/acme-intake` |
| Vendor Intake Policy | knowledge_base article `KB-POLICY-100` |
| Vendor Risk Log | knowledge_base article `KB-RISKLOG-200` (update with the final assessment) |

## Expected Outcome

After completing the review, the Vendor Risk Log (`KB-RISKLOG-200`) should contain a structured assessment for **AcmeVendor** that addresses the policy areas specified in the Vendor Intake Policy (e.g., MFA, encryption, audits, breach notification). No other modifications are expected.
