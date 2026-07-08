# Quarterly Access Review Brief – Q3 2027

**Review period:** 1 July – 30 September 2027  
**Prepared by:** IT Compliance Team  
**Taskboard task:** TASK-1010

---

## Scope

This brief covers the two production systems that require owner verification this quarter. For each system, confirm the designated owner is still an active member of the IT department using the corporate directory, then document your findings in Taskboard.

---

## Systems and Designated Owners

### 1. Payroll

- **System name:** Payroll
- **Designated owner:** Alice Chen
- **Employee ID:** EMP001
- **Expected department:** IT
- **Notes:** Alice has been the owner since Q1 2025. Her last review was completed without issues.

### 2. HR Portal

- **System name:** HR Portal
- **Designated owner:** Bob Martinez
- **Employee ID:** EMP002
- **Expected department:** IT
- **Notes:** Bob assumed ownership in June 2027 following an internal transfer from the Operations department.

---

## Review Steps

1. Use the **Directory** mock API to search for each owner by name and confirm:
   - The employee record exists.
   - The department field shows "IT."
   - The notes or status fields indicate the employee is still active.

2. Retrieve the access-review task from **Taskboard** (TASK-1010) to review the existing description.

3. Update TASK-1010 via the Taskboard API with a summary of your findings. Include each owner’s name, department confirmation, and active status. Note any discrepancies or concerns (e.g., if someone has transferred out of IT or appears inactive).

---

## Reporting

All findings should be recorded directly in the Taskboard task description. No additional files need to be created in the workspace. The standard mock API skills for Directory and Taskboard provide the endpoints needed to complete this review.
