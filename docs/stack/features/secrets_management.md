
# Secrets Management

## Overview
Secrets management ensures that sensitive information (such as API keys and authentication cookies) is handled securely and is not exposed in version control.

- **Files:** `secrets/secrets.py`, `facebook_cookies.txt`
- **Purpose:** Stores sensitive information required for authentication and API access.
- **Usage:** Required for scripts that interact with Facebook or other external services.
- **Note:** These files are not tracked in version control for security reasons.

## Product Value
- Protects user credentials and sensitive data from accidental exposure.
- Simplifies onboarding by centralizing secret management.
- Supports compliance and best practices for security.

## How it works
1. Secrets are stored in dedicated files, excluded from version control.
2. Scripts load secrets as needed for authentication and API access.

## User Impact
- Reduces risk of credential leaks.
- Makes it easier for new contributors to set up the project securely.
- Ensures compliance with security best practices.
