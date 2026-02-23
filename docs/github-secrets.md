# GitHub Actions secrets setup

This workflow writes sensitive values to files at runtime, so they must be stored as **GitHub Actions secrets**.

## Where to add secrets

Go to **Repository → Settings → Secrets and variables → Actions** and click **New repository secret**.

## Secrets required

Add these secrets **exactly** with the following names:

- **FACEBOOK_COOKIES**: Paste the full contents of `facebook_cookies.txt` (Netscape format, single line).
- **ONEMAP_EMAIL**: Your OneMap account email.
- **ONEMAP_PASSWORD**: Your OneMap account password.

## How the workflow uses them

The workflow in [update-map.yml](../.github/workflows/update-map.yml) does the following at runtime:

- Writes `FACEBOOK_COOKIES` to `facebook_cookies.txt`
- Writes `ONEMAP_EMAIL` and `ONEMAP_PASSWORD` into `secrets/secrets.py`

Nothing sensitive is committed to the repository; the files are created only inside the workflow run.
