# Secrets Management

Keeps sensitive credentials — your Facebook login cookies and OneMap API password — out of the codebase, so they're never accidentally shared or published.

## Why it exists

Two external services need credentials to work: Facebook (to access the group) and OneMap (to geocode addresses). These credentials are personal. Without keeping them separate from the code, anyone with access to the repository would also have access to your accounts.

## User stories

- As a **maintainer**, I want my credentials kept out of the repository so I don't accidentally expose them when sharing or publishing the code.
- As a **contributor**, I want to supply my own credentials locally so I can run the project without needing access to anyone else's accounts.
- As a **maintainer**, I want credential handling to be consistent across scripts so I only have to set things up once.

## How it works

Credentials are stored in files that sit alongside the code but are excluded from version control via `.gitignore`. When a script needs to authenticate, it reads the credentials from these local files at runtime — they're never baked into the code itself. Each person who runs the project supplies their own credentials; nothing sensitive is shared through the repository.

## Reference

**Files to create (both git-ignored):**

`facebook_cookies.txt` — exported from your browser using the "Get cookies.txt LOCALLY" extension while logged into facebook.com. Used by `extract_group.py` to authenticate with the Facebook group.

`secrets/secrets.py` — OneMap API credentials, used by `map_posts.py` to geocode Singapore addresses:
```python
onemap = {
    "email": "your_email@example.com",
    "password": "your_password"
}
```

Register for a free OneMap account at https://www.onemap.gov.sg/apidocs/register.
