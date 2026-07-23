# Automation Incident Review Workspace

This workspace provides the resources needed to review automation incident reports and update associated support tickets. It is designed to work with the mock Automation and Ticketing API skills available in the environment.

## Workflow

1. **Read the incident brief**  
   Open `incident_brief.md` to find the failed job ID and the linked support ticket ID.

2. **Retrieve job details**  
   Use the Automation mock API endpoint `/automation/jobs/get` to fetch the current state, notes, and status of the failed job. Provide the `job_id` found in the brief.

3. **Retrieve the ticket**  
   Use the Ticketing mock API endpoint `/ticketing/tickets/get` to fetch the ticket details. Provide the `ticket_id` found in the brief.

4. **Update the ticket**  
   After confirming the job failure, update the ticket with the appropriate next-action tags. Use the Ticketing mock API endpoint `/ticketing/tickets/update` and pass the same `ticket_id` along with an array of tags. The standard tags for this workflow are `reviewed` and `rerun`.

## API Endpoints Reference

- **Automation**  
  `GET /automation/jobs/get`  
  Required parameter: `job_id` (string)

- **Ticketing**  
  `GET /ticketing/tickets/get`  
  Required parameter: `ticket_id` (string)  
  `POST /ticketing/tickets/update`  
  Required parameters: `ticket_id` (string), `tags` (array of strings)

## Conventions

- All IDs are case-sensitive.
- Tags added via the update endpoint completely replace any existing tags. Be sure to include all desired tags in the update call.
- A successful review results in the ticket tags containing at least `reviewed` and `rerun`.
