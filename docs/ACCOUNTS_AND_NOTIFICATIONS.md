# Accounts, expiry notifications and saved chats

## What works

1. Uploads automatically detect recognizable expiry labels and valid dates. A single unique
   parsed expiry date is saved and activates reminders immediately. Missing, invalid or
   conflicting dates do not create an invented expiry; inspect extracted fields and set it
   manually. Numeric dates use day/month/year.
2. Website reminders appear within 30 days of expiry, on the day, and after expiry. The
   website refreshes reminders every 30 seconds; the running server checks every minute.
3. Signup/login uses salted PBKDF2 passwords and expiring HttpOnly, SameSite cookies.
   Each account can access only its documents, downloads, reminders and conversations.
4. Previous chats are saved in SQLite. Click a history entry to resume or choose New chat.
   Document scope and source passages are preserved. A configured LLM receives bounded
   conversation history; source-excerpt mode stays extractive.
5. Document classification uses the trained classifier; names, birth/issue/expiry dates,
   document numbers and other labelled metadata are extracted. The six trained classes are
   passport, PAN, Aadhaar, medical, insurance and invoice. Other types can be unknown or
   misclassified. These models are trained on synthetic data.

## Email setup

The app sends expiry emails to the account's verified email address, not an arbitrary
address supplied with an upload. Signup sends a verification link when SMTP is configured.
The account works without verification, but document emails wait until the email is verified.

Set these environment variables in the terminal used to launch the app (PowerShell):

~~~powershell
$env:FOLIO_SMTP_HOST="smtp.your-provider.example"
$env:FOLIO_SMTP_PORT="587"
$env:FOLIO_SMTP_SECURITY="starttls"
$env:FOLIO_SMTP_USERNAME="your-smtp-username"
$env:FOLIO_SMTP_PASSWORD="<your-provider-app-password>"
$env:FOLIO_SMTP_FROM="your-sender-address@example.com"
$env:FOLIO_PUBLIC_URL="http://127.0.0.1:8000"
.\scripts\start.ps1 -Background
~~~

Use your provider's actual values. Port 465 uses FOLIO_SMTP_SECURITY=ssl. Credentials are
read from the environment and are never stored in source files, browser storage or logs.
The sender must be permitted by the provider. The app shows when SMTP is not configured.
If the app is already running, restart it after changing environment variables.

The email outbox records one upcoming and one due/overdue event per document and expiry
date. Failures retry with backoff. Changing the date clears obsolete queued events.
SMTP acceptance is not proof of inbox delivery. A process crash after SMTP acceptance
but before recording success can cause a duplicate; this is an at-least-once delivery
design, not a guarantee of exactly-once email.

The server must be running for continuous checks. Alternatively, schedule the following
command with your OS scheduler, using the same SMTP environment and data directory:

~~~powershell
python scripts/check_reminders.py
~~~

Checks catch up on overdue documents after a restart. Use one active reminder worker.
No Windows task or external mail account is automatically installed or configured.

## Existing documents from before accounts

Old documents are preserved, backed up before the account-schema migration, and left
unassigned. They are not automatically exposed to the first person who signs up.

Create your account, then run from a trusted local terminal:

~~~powershell
python scripts/assign_legacy.py --email "your-login-email@example.com"
~~~

Only unassigned documents are moved. Existing account documents are untouched.
Refresh the library afterward.

## Chat deletion and document deletion

Deleting a conversation removes its saved messages. Deleting a document removes its
original, extracted data and notifications. Existing chat messages can still contain
quoted passages from that document; delete those conversations as well to remove the
saved quotations. No chat history existed before this update; old unsaved browser
messages cannot be recovered.

## Tests and remaining setup

API/integration tests cover authentication, account isolation, extraction, automatic
expiry notices, dates today and overdue, email verification, SMTP TLS/recipient routing,
outbox retries, deduplication, date corrections, and chat continuation/persistence.

No real email was sent during verification. Live delivery requires SMTP credentials and
a verified account. The headless browser rerun was blocked by automatic approval review
due to its usage limit. The browser regression script includes signup and chat-resume
checks, but those new browser checks have not been executed.

The existing .venv was found incomplete. The launch script now selects a Python interpreter
with the installed core dependencies and only auto-enables optional models when their
packages are present. It does not modify the virtual environment. Tests used the installed
system Python.

This remains a localhost application. For an HTTPS deployment, secure cookies must be
enabled with FOLIO_SECURE_COOKIES=1; public hosting, password-reset/account-recovery and
production operational hardening are outside this update.

## Gmail helper

For the Gmail address supplied in this session, run:

~~~powershell
.\scripts\start-gmail.ps1 -Email "kmbarath91@gmail.com" -Background
~~~

The helper asks for the Google App Password using a hidden terminal prompt and passes
it only through the server process environment. It does not save the password to disk.
Create a Folio account with that email, then follow the verification link. If you already
registered before configuring SMTP, use Send verification email in the app.

Google requires 2-Step Verification for App Passwords; availability can depend on account
settings. See [Google's App Password instructions](https://support.google.com/accounts/answer/185833?hl=en)
and [Gmail's SMTP settings](https://support.google.com/mail/answer/7104828?hl=en).
Do not use your normal Google password in the helper. A sender account is separate from
Folio login credentials. If App Passwords are unavailable, use another supported SMTP
provider; OAuth-based Gmail sending is not implemented.
