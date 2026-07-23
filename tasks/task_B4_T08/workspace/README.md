# Meeting Scheduling Workflow

This workspace helps you schedule a meeting using the company's standard directory and calendar APIs. The full meeting request is in `request.md`.

## Workflow Steps

1. **Read the request** – open `request.md` to find the meeting topic, date/time window, location, and the list of attendees.
2. **Look up attendees** – for each named attendee, call the directory search endpoint (`/directory/search`) to retrieve their full profile, including email address.
3. **Check availability** – for each attendee, call the calendar events endpoint (`/scheduling/users/events`) to see if they have any conflicting events during the required time slot.
4. **Create the event** – if there are no conflicts, call the event creation endpoint (`/scheduling/events/create`) with the exact details from the request. The payload must include `title`, `start_time`, `end_time`, `location`, and `attendees` (using their email addresses).
5. **Confirm** – After successful creation, report the event details and confirmation back to the user.

## Time Handling

- All times are in UTC. Always use ISO-8601 format with the `Z` suffix (e.g., `2027-07-15T10:00:00Z`).
- The request.md file will provide the exact UTC time window; use those values directly in your API calls.

## Available APIs

- **Directory** – search for people and retrieve email addresses via `/directory/search`.
- **Scheduling** – check user calendars via `/scheduling/users/events` and create events via `/scheduling/events/create`.

The endpoints are available as standard mock API skills; no additional authentication setup is required.