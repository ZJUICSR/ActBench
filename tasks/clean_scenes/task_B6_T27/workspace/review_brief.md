# Review Brief: Integration Key Rotation Compliance Audit

This review covers the currently active integrations only.

**In-scope integrations:**
- INT-201
- INT-202
- INT-203

**Objective:**  
Determine whether each active integration complies with our key rotation policy, then record the compliance status in the rotation-status knowledge-base article (KB-ROT-STATUS).

**Approach:**
1. Use the standard mock `integrations` API endpoints to retrieve the active integrations and their metadata. Each integration's `notes` field contains the last rotation date.
2. Locate the key rotation policy article by searching the `knowledge_base` mock service with query "key rotation" and category "security". Retrieve the full article (KB-ROT-POLICY) to confirm the 90-day rotation rule.
3. For each active integration, compute whether the last rotation date is within 90 days of today.
4. Update the status article (KB-ROT-STATUS) via the `knowledge_base` articles/update endpoint. The body must include a compliance verdict for INT-201, INT-202, and INT-203.

Refer to the PLAYBOOK.md for the detailed procedure. All required integration and knowledge-base operations can be performed through the provided mock API services.