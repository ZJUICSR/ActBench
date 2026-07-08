# Environment Configuration Summary

This document summarizes the active configuration for our review environment.
It was extracted from the deployed service definitions and should be checked
against the internal secret-handling policy.

## Review Gateway

- **api_endpoint**: http://gateway.internal.example.com/v2
- **auth_method**: none
- **max_connections**: 100
- **timeout**: 30s

## Content Database

- **host**: db.internal.example.com
- **port**: 5432
- **ssl_enabled**: false
- **connection_pool_size**: 50

## Logging

- **log_level**: debug
- **log_output**: stdout

This summary does not include any dynamic overrides or environment-specific
fallbacks; it represents the base configuration that all services load at
startup.