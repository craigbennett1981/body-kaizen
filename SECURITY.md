# Security and privacy

## How Body Kaizen handles your data

- **Local only.** The dashboard server listens on `127.0.0.1` and serves nothing to your network or the internet.
- **No accounts, cloud or telemetry.** Nothing is sent anywhere except to the services you choose to connect.
- **Your data lives in your data folder** (`FT_DATA`), separate from the code. Keep it in a **private** git
  repository, or no repository at all.
- **Credentials stay out of both folders.** Garmin tokens are stored in `~/.garminconnect`; the LibreLinkUp
  login email in `~/.body-kaizen/libre.json` and its password in the operating system's keychain (via `keyring`).
  None of them is written to the code or data folder.
- **Synced raw files are trimmed.** The Garmin sync drops personal and location fields (names, email, profile details, location and
  GPS tracks) before saving its raw responses.

## Things to watch

- If you keep your data folder in git, make sure the remote repository is **private** before you push.
- Pasting logs into issues: remove dates of birth, ID numbers, names and anything else personal first.
- Body-composition printouts (InBody and similar) often carry your ID number and date of birth. Don't store
  those fields.

## Reporting a vulnerability

Please don't open a public issue. Use GitHub's **private vulnerability reporting** on this repository
(Security tab → "Report a vulnerability"). You'll get a reply within a week.
