# Configuration Summary

This document provides an overview of the current project configuration layout to support the compliance audit against the company's secret-handling policy. All configuration artifacts are maintained within the repository.

## Configuration Artifacts

### application.yaml
- **Format:** Plaintext YAML
- **Purpose:** Core application settings including feature toggles, log verbosity, and operational modes.
- **Storage:** Checked into version control as `config/application.yaml`.

### database.yaml
- **Format:** Plaintext YAML
- **Purpose:** Database connection parameters such as hostname, port, database name, and connection pool size.
- **Storage:** Checked into version control as `config/database.yaml`.

### integrations.ini
- **Format:** Plaintext INI
- **Purpose:** Configuration for external API integrations, defining service endpoints and request timeouts.
- **Storage:** Checked into version control as `config/integrations.ini`.

### startup.sh
- **Format:** Shell script
- **Purpose:** Loads runtime configuration values from a local source file before launching the application.
- **Storage:** Checked into version control as `scripts/startup.sh`.

## Notes
All configuration files are stored in plaintext within the repository. No encryption or vault mechanisms are currently applied to these files.