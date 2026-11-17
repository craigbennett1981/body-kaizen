# Security and privacy

## How Body Kaizen handles your data

- **The dashboard answers on this computer only.** It listens on `127.0.0.1` and serves nothing to your network or
  the internet. The one thing that listens on your home network is the separate receiver for paired iPhones (below):
  upload only, and off until you pair a phone.
- **Only you can open it.** Every request, reads included, needs a cookie holding a secret kept in
  `~/.body-kaizen/session.key`, which only your account can read (0600, in a 0700 folder). Starting the dashboard
  from a terminal, the installer, its **Body Kaizen** launcher, `scripts/setup_mac.sh`, or `body-kaizen open` opens
  your browser on a sign-in link carrying it (the launcher reads the key when you click it; it is never stored in the
  launcher or a bookmark);
  the server turns it into the cookie (`HttpOnly`, `SameSite=Strict`) and redirects to the address without the key,
  so it isn't left in the address bar or history. It's the pattern Jupyter uses. Other accounts on the same computer,
  and anything else that reaches the port, get a "not signed in" page and no data. The secret is kept across
  restarts, so it's once per browser; delete the file to sign every browser out. The service's log never contains
  it. Programs running as you can still read the key, as they can read your data folder: keep your own account
  free of software you don't trust.
- **Only the dashboard's own page can change anything.** Every request that saves or triggers something must
  come from the dashboard itself: the server checks the address it was reached on (against DNS rebinding), the
  browser-set `Origin` and `Sec-Fetch-Site` headers, that the body is JSON, and a random token created each time
  the server starts and handed only to the dashboard page (`X-BK-Token`). It never answers CORS preflights or sends
  `Access-Control-Allow-Origin`, so other websites can neither call it nor read its replies. `tests/test_security.py`
  tries each of these attacks, and the sign-in above.
- **Text from your data can't run as code.** Everything the pages show from your files (food and meal names, notes,
  exercises, lab markers, Claude's comments) is escaped, and a strict Content-Security-Policy lets only the
  dashboard's own scripts run: each page's scripts carry a random nonce, inline event handlers and `eval` are
  blocked, and nothing can be loaded from or sent to another site. So if a label photo or lab PDF carried a prompt
  injection that got markup into a YAML file, it would show as text. The pages also can't be framed by another site
  (`frame-ancestors 'none'`, `X-Frame-Options: DENY`).
- **API parameters are checked.** Dates must be real dates and numbers numbers before anything reaches the code
  (a date becomes part of a file path), unknown parameters are refused, and day ranges are capped.
- **A request can't tie the server up.** A missing, negative or malformed body length is refused at once, bodies
  over 10 KB are refused, and a connection that sends nothing is dropped after 30 seconds. An error while handling a
  request goes to the server log and the reply says only "server error".
- **No accounts, cloud or telemetry.** Nothing is sent anywhere except to the services you choose to connect. The
  iPhone app sends only to your own computer, on your home network.
- **Your data lives in your data folder** (`FT_DATA`), separate from the code. Keep it in a **private** git
  repository, or no repository at all.
- **Credentials stay out of both folders.** Garmin tokens are stored in `~/.garminconnect`; the LibreLinkUp
  login email in `~/.body-kaizen/libre.json` and its password in the operating system's keychain (via `keyring`);
  the iPhone receiver's certificate, key and paired phones (token hashes only) in `~/.body-kaizen/sync/`.
  None of them is written to the code or data folder. Both folders, and every file in them, are private to your
  account (0700 and 0600), created that way rather than tightened afterwards.
- **The data folder is yours alone and stays clean in git.** A new data folder is private to your account (0700),
  whether the dashboard's first-run setup or `body-kaizen init` makes it, and gets a `.gitignore` for sync bookkeeping
  (`imports/*/state.json`), the iPhone's 14-day raw cache (`imports/apple/cache.sqlite`, which also carries its own
  `.gitignore` for older folders) and operating-system clutter. The dashboard refuses a data folder inside the code
  folder, matching paths without regard to case on macOS and Windows, where `~/Repos/Body-Kaizen` and
  `~/repos/body-kaizen` are the same folder.
- **The build pins what it runs.** Every GitHub Action is pinned to a commit, not a tag that could be moved, and
  Dependabot keeps the pins current. Values from the event (a tag name) reach scripts through the environment,
  never pasted into them.
- **Logging in from the dashboard.** The Connections page sends your Garmin or LibreLinkUp password once, in a request
  only the dashboard's own page can make (the write protection above), straight to the login library and, for
  LibreLinkUp, the keychain. It is never written to a file or log, never sent back, and error messages never include
  it. A half-finished Garmin two-step login is held in the dashboard's memory only, for at most 10 minutes and 5 codes.
  Disconnect deletes the Garmin token or the LibreLinkUp password and login file. `tests/test_connections.py` checks
  that the password reaches neither a reply nor the server log.
- **The iPhone receiver (Body Kaizen Sync).** A second listener, separate from the dashboard, on port 8766
  (`FT_SYNC_PORT`). It runs only while a phone is paired, or while a pairing code you made on the Connections page is
  live, and stops when you remove the last phone. What protects it:
  - **Upload only.** Four routes (`POST /v1/pair`, `/v1/samples`, `/v1/deletions`, `/v1/ping`); no pages, no data,
    no listings. Nothing you've stored can be read back through it.
  - **Encrypted, and the phone knows it's your computer.** TLS with a self-signed ECDSA P-256 certificate made on
    first pairing (`~/.body-kaizen/sync/`, 0600 files in a 0700 folder). The QR code carries its SHA-256
    fingerprint, and the app accepts that certificate only, so no certificate authority is involved and no one else
    on the network can pose as your computer.
  - **Pairing.** A one-time code, 128-bit, valid 10 minutes, burned when used or after five wrong tries, shown only on
    the signed-in dashboard (as a QR code and an 8-character typed form). The QR code works only inside the app: no
    URL scheme, no link.
  - **One token per phone.** Pairing gives the phone a random 256-bit token; only its SHA-256 is stored
    (`devices.json`). Every upload needs it, and it must match the phone's own ID. Remove on the Connections page
    revokes it at once and deletes that phone's raw uploads.
  - **Home network only.** A connection from anywhere but a private, link-local or loopback address is dropped
    before TLS starts, before anything else is read.
  - **Limits.** 5 MB per request (gzip JSON, at most 64 MB unzipped), 120 requests a minute and 300 MB a day per
    phone, JSON only, unknown data types refused before they touch anything. Device names lose control characters
    before they reach the log or the page.
  - **No late writes, no stray deletes.** A phone can delete only samples it sent. An upload still under way when
    that phone was erased or removed is refused, so it can't bring erased data back; pairing and erasing never run at
    the same time.
  - **Nothing follows a redirect.** The app never follows one with its token, and the receiver never sends one.

  **What a stranger on your Wi-Fi can and can't do.** They can see that port 8766 is open and that it speaks TLS.
  Without a pairing code they can't pair, and without a phone's token they can't upload, delete or read anything:
  every request gets "not paired". Guessing a live pairing code gets five tries, at a 128-bit code or its 8-character typed
  form, before the code is burned. They can't pose as your computer to your phone (the certificate is pinned). What they can do is
  make requests that are refused, which the per-phone limits and short timeouts keep cheap. Someone who steals a
  phone's token can upload junk for that phone until you remove it, within its daily limit, but still can't read
  anything. Tests: `tests/test_syncreceiver.py` drives all of this with a stand-in phone.
- **Synced raw files are trimmed.** The Garmin sync drops personal and location fields (names, email, profile details, location and
  GPS tracks) before saving its raw responses.

## Encryption: what protects your data where

Body Kaizen doesn't encrypt your data files itself, on purpose. The dashboard and your AI assistant both need to
read and write them, so the key would have to sit unlocked on the same computer whenever you use it: anything that
could read the files could read the key too. You'd lose plain YAML your assistant can edit, readable git history and
files you can open anywhere, for very little protection. Each place your data lives has a better answer:

| Where | The risk | What covers it |
|---|---|---|
| Your computer, switched off or locked | Lost or stolen laptop | **Full-disk encryption**: FileVault on macOS (check with `fdesetup status`), BitLocker on Windows, LUKS on Linux. With it on, nothing on the disk can be read without your login. |
| Your computer, while you're logged in | Another account on the same computer | Your home folder's permissions (macOS keeps other accounts out of it by default; on Linux check it isn't world-readable with `ls -ld ~`), and the dashboard's sign-in above. |
| Your computer, while you're logged in | Software running as you | Nothing a local tool can do: it can read whatever you can. Keep your own account free of software you don't trust. |
| Backups | A backup drive lost or copied | Turn on encryption for the backup: "Encrypt backups" in Time Machine, or the equivalent in your backup tool. |
| Your git remote (GitHub or similar) | Someone gets into the repository, or the host itself | Keep it **private**, protect the account with two-factor sign-in, or encrypt what's pushed (below). A self-hosted remote (a NAS on your own network) keeps it off third-party servers. |

**Encrypting what you push.** If the copy on a git host worries you, [git-crypt](https://github.com/AGWA/git-crypt)
encrypts chosen files in the repository while leaving them plain on your computer, so the dashboard, your assistant
and git work as before. A sensible split is the health data (`days/`, `measurements/`, `imports/`) encrypted, and
the settings files (`targets.yaml`, `settings.yaml`, `meals.yaml`) readable. The cost: every place that checks out
the repository needs the key. On your own computer that's a one-off `git-crypt unlock`; an AI assistant that clones
the repository from the host (in the cloud rather than on your computer) would see only encrypted files unless you
gave it the key, which defeats the point. Diffs on the host's website are unreadable too. Keep the key somewhere safe
and separate (a password manager): without it the pushed copy can't be read, even by you.

## Things to watch

- If you keep your data folder in git, make sure the remote repository is **private** before you push.
- Pasting logs into issues: remove dates of birth, ID numbers, names and anything else personal first.
- Body-composition printouts (InBody and similar) often carry your ID number and date of birth. Don't store
  those fields.

## Reporting a vulnerability

Please don't open a public issue. Use GitHub's **private vulnerability reporting** on this repository
(Security tab → "Report a vulnerability"). You'll get a reply within a week.
