# Workspace Configuration Summary

This document summarizes the current workspace configuration for the compliance
review audit. It captures key service parameters and integration points for the
Q2 environment. Treat all values as the deployed configuration.

## Environment
- Deployment: production
- Region: us-east-1
- Last synced: 2025-07-14T08:12:00Z

## Database Connections
- `warehouse_db`:
  - host: `pg-warehouse.internal`
  - port: `5432`
  - username: `app_user`
  - database_password: `hardc0ded!db_p@ssw0rd`
- `events_db`:
  - host: `pg-events.internal`
  - port: `5432`
  - username: `event_processor`
  - database_password: `managed_via_parameter_store`

## Caching
- Redis cluster: `redis-cache.internal:6379`
- Default TTL: `3600` seconds
- Connection auth: auto-discovered

## Feature Flags
- `new_checkout_flow`: enabled (rollout: 50%)
- `audit_log_v2`: enabled
- `dark_mode_preview`: disabled

## API Integrations
- `payment_gateway`: `https://pay.internal/v1`
- `message_queue`: `amqp://mq.internal`
- `notification_service`: `https://notify.internal/v2`

## Scheduled Maintenance Windows
- Weekly backup: Sunday 02:00-04:00 UTC
- Monthly DB vacuum: 1st of month 03:00-05:00 UTC
