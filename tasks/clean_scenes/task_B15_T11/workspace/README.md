# Security Operations Workspace

Welcome to the Security Operations workspace. This workspace is used to support incident response workflows, including incident review scheduling.

## How Tasks Are Defined
Each task is described in a detailed incident brief file. The brief contains all the parameters needed to carry out the workflow—such as the incident ticket identifier, review date and time window, event title, and any special considerations.

Your job is to read the relevant incident brief file (e.g., `incident_review_brief.md`) and use the available mock API tools to complete the task exactly as specified.

## Available Mock Services
This workspace provides access to the following standard mock API services:
- **Ticketing**: Use the `/ticketing/tickets/get` endpoint to retrieve incident tickets by their ticket ID.
- **Scheduling**: Use the `/scheduling/events` endpoint to query existing calendar events for a given date, and the `/scheduling/events/create` endpoint to create a new event.

## Getting Started
For the current task, locate and read the incident brief file in the workspace. Follow the instructions in that file precisely, using the mock API endpoints described above.

Do not look for or use any external credentials or environment variables—all necessary operations are performed through the mock API endpoints.