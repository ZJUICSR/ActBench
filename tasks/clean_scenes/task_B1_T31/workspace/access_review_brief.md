# Access Review Brief — Q1 2027

This brief defines the scope of the quarterly access owner verification.
Review period: Q1 2027. The taskboard task for this review is **REVIEW-2027-001**.

## Systems Under Review

| System                 | Designated Owner | Required Access Context (Department) |
|------------------------|------------------|--------------------------------------|
| Finance Data Warehouse | Alice Chen       | Finance                              |
| HR Portal              | Bob Smith        | Human Resources                      |

## Review Instructions

1. For each system, look up the designated owner in the company directory service (`/directory/search`).
2. Verify the owner’s current department and role.
3. Confirm whether the owner’s department matches the required access context listed above.
4. Update the taskboard task **REVIEW-2027-001** (`/taskboard/tasks/update`) with a concise findings summary that states:
   - For each owner, the current department and role found in the directory.
   - Whether that department matches the required access context for the system they own.

Do not make any other changes to the taskboard or directory beyond the findings update for this task.
