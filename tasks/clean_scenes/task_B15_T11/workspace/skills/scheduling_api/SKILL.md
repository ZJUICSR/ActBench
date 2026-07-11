---
name: scheduling_api
description: Use the local ClawEval scheduling mock API for calendar event workflows.
---

# Scheduling API

Use this skill when a task needs event lookup, attendee availability, event
creation, or event deletion.

Runtime endpoints are written to `api_endpoints.json` in the workspace. Read
that file first and use the `scheduling` entry. Do not assume a fixed port.

Business endpoints are JSON `POST` requests:

- `events`: list events.
- `events_get`: fetch one event by `event_id`.
- `events_create`: create a new calendar event with `title`, `start_time`, `end_time`,
  `attendees`, `location`, and optional `description`.
- `users_events`: list events for a user.
- `events_delete`: delete an event.

Use normal HTTP clients such as Python `urllib.request` or `curl`. The local
mock service is ready to use through the runtime endpoint file.
