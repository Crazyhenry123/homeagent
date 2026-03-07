# Cloud Storage Provider OAuth Setup Guide

**Callback URL pattern used by this app:**
```
https://{hostname}/api/storage/oauth/callback/{provider_id}
```

Where `{provider_id}` is one of: `google_drive`, `onedrive`, `dropbox`, `box`

---

## 1. Google Drive

**Environment variables:** `GOOGLE_DRIVE_CLIENT_ID`, `GOOGLE_DRIVE_CLIENT_SECRET`
**Scope:** `https://www.googleapis.com/auth/drive.file`

### Developer Console

URL: https://console.cloud.google.com/

### Step-by-step

1. **Create or select a Google Cloud project**
   - Go to https://console.cloud.google.com/
   - Click the project dropdown at the top, then "New Project"
   - Name it (e.g., "HomeAgent") and click "Create"

2. **Enable the Google Drive API**
   - Navigate to **APIs & Services > Library**
   - Search for "Google Drive API"
   - Click it and press **Enable**

3. **Configure the OAuth consent screen**
   - Navigate to **APIs & Services > OAuth consent screen**
   - Select **External** user type (unless you only need users within your Google Workspace org)
   - Fill in the required fields: App name, User support email, Developer contact email
   - On the "Scopes" step, add: `https://www.googleapis.com/auth/drive.file`
   - On the "Test users" step, add email addresses of people who can test while the app is unverified
   - Save and continue

4. **Create OAuth 2.0 credentials**
   - Navigate to **APIs & Services > Credentials**
   - Click **Create Credentials > OAuth client ID**
   - Application type: **Web application**
   - Name: e.g., "HomeAgent Backend"
   - Under **Authorized redirect URIs**, add:
     ```
     https://{your-hostname}/api/storage/oauth/callback/google_drive
     ```
   - Click **Create**

5. **Retrieve credentials**
   - A dialog will display your **Client ID** and **Client Secret**
   - Copy both and set them as environment variables:
     ```
     GOOGLE_DRIVE_CLIENT_ID=xxxxxxxxxxxx.apps.googleusercontent.com
     GOOGLE_DRIVE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxx
     ```

### Gotchas

- **Consent screen verification required for production.** While in "Testing" mode, only manually-added test users (max 100) can authorize. To go to production, you must submit a verification request to Google, which requires a privacy policy URL, a homepage URL, and may require a security assessment if you use sensitive scopes. This process can take days to weeks.
- **The `drive.file` scope is "restricted."** Google classifies Drive scopes as sensitive/restricted. Verification will require justification for why you need Drive access.
- **Refresh tokens.** Google issues refresh tokens by default, but only on the first consent. If the user has already authorized and you need a new refresh token, add `prompt=consent&access_type=offline` to the auth URL (the app already handles this).
- **Localhost redirect URIs** are allowed for development -- you can add `http://localhost:5000/api/storage/oauth/callback/google_drive` for local testing.

---

## 2. Microsoft OneDrive

**Environment variables:** `ONEDRIVE_CLIENT_ID`, `ONEDRIVE_CLIENT_SECRET`
**Scopes:** `Files.ReadWrite.All offline_access`

### Developer Console

URL: https://entra.microsoft.com/ (Microsoft Entra admin center, formerly Azure AD)

### Step-by-step

1. **Sign in to the Microsoft Entra admin center**
   - Go to https://entra.microsoft.com/
   - Sign in with a Microsoft account that has at least **Application Developer** role

2. **Register a new application**
   - Navigate to **Entra ID > App registrations**
   - Click **New registration**
   - Name: e.g., "HomeAgent"
   - **Supported account types**: Select **"Accounts in any organizational directory and personal Microsoft accounts"** (this covers both work/school and personal OneDrive accounts)
   - Under **Redirect URI**, select platform **Web** and enter:
     ```
     https://{your-hostname}/api/storage/oauth/callback/onedrive
     ```
   - Click **Register**

3. **Record the Application (Client) ID**
   - On the app's Overview page, copy the **Application (client) ID** -- this is your `ONEDRIVE_CLIENT_ID`

4. **Create a client secret**
   - Navigate to **Certificates & secrets**
   - Click **Client secrets > New client secret**
   - Enter a description (e.g., "HomeAgent Production") and choose an expiration (max 24 months)
   - Click **Add**
   - **Immediately copy the secret Value** (it is shown only once) -- this is your `ONEDRIVE_CLIENT_SECRET`

5. **Add API permissions**
   - Navigate to **API permissions**
   - Click **Add a permission > Microsoft Graph > Delegated permissions**
   - Search for and add:
     - `Files.ReadWrite.All`
     - `offline_access`
   - Click **Add permissions**
   - If you see a "Grant admin consent" button and you are an admin, click it

6. **Set environment variables**
   ```
   ONEDRIVE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ONEDRIVE_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

### Gotchas

- **Client secrets expire.** Max lifetime of 24 months. You must rotate them before expiry. Set a calendar reminder.
- **Supported account types matter.** If you choose "Accounts in this organizational directory only", personal Microsoft account users (consumer OneDrive) will not be able to connect. Use the broadest option for compatibility.
- **The `/common` endpoint.** The app uses `https://login.microsoftonline.com/common/oauth2/v2.0/authorize` which supports multi-tenant and personal accounts.
- **Admin consent may be required** in some organizations for `Files.ReadWrite.All`.
- **Publisher verification.** For production, Microsoft recommends associating a Microsoft Partner Network ID. Without it, users see an "unverified" warning.

---

## 3. Dropbox

**Environment variables:** `DROPBOX_CLIENT_ID`, `DROPBOX_CLIENT_SECRET`
**Scope:** Configured via permissions tab in App Console

### Developer Console

URL: https://www.dropbox.com/developers/apps

### Step-by-step

1. **Go to the Dropbox App Console**
   - Navigate to https://www.dropbox.com/developers/apps
   - Sign in with your Dropbox account

2. **Create a new app**
   - Click **Create app**
   - **API**: Choose **Scoped access**
   - **Access type**: Choose **App folder** (limited to a dedicated folder `/Apps/HomeAgent/` -- more secure and easier to get production approval)
   - **Name**: Enter a unique name (e.g., "HomeAgent") -- must be globally unique

3. **Configure the app settings**
   - On the Settings tab, find **App key** and **App secret**
   - App key = `DROPBOX_CLIENT_ID`
   - App secret = `DROPBOX_CLIENT_SECRET`

4. **Add redirect URI**
   - Under **OAuth 2** section, add:
     ```
     https://{your-hostname}/api/storage/oauth/callback/dropbox
     ```

5. **Configure permissions**
   - Go to the **Permissions** tab
   - Enable:
     - `files.metadata.read`
     - `files.metadata.write`
     - `files.content.read`
     - `files.content.write`
   - Click **Submit**
   - Permission changes only take effect for new OAuth authorizations.

6. **Set environment variables**
   ```
   DROPBOX_CLIENT_ID=xxxxxxxxxxxxxxx
   DROPBOX_CLIENT_SECRET=xxxxxxxxxxxxxxx
   ```

### Gotchas

- **Production approval required.** New apps are limited to 500 users in "Development" status. Apply for Production status via the App Console.
- **App folder vs Full Dropbox.** "App folder" is recommended -- sandboxes access to `/Apps/{AppName}/`.
- **Redirect URI must be HTTPS** in production. `http://localhost` is allowed for development only.
- **Token expiration.** Access tokens expire after 4 hours. The app uses refresh tokens for automatic renewal.
- **The app name is globally unique.** If "HomeAgent" is taken, you will need a different name.

---

## 4. Box

**Environment variables:** `BOX_CLIENT_ID`, `BOX_CLIENT_SECRET`
**Scope:** Configured via application scopes in Developer Console

### Developer Console

URL: https://app.box.com/developers/console

### Step-by-step

1. **Go to the Box Developer Console**
   - Navigate to https://app.box.com/developers/console
   - Sign in with your Box account (free account works for development)

2. **Create a new app**
   - Click **Create New App**
   - Select **Custom App**
   - Authentication method: **User Authentication (OAuth 2.0)**
   - Name: e.g., "HomeAgent"
   - Click **Create App**

3. **Configure the app**
   - On the **Configuration** tab, find **OAuth 2.0 Credentials**:
     - **Client ID** = `BOX_CLIENT_ID`
     - **Client Secret** = `BOX_CLIENT_SECRET`

4. **Set redirect URI**
   - In the **OAuth 2.0 Redirect URI** field, enter:
     ```
     https://{your-hostname}/api/storage/oauth/callback/box
     ```

5. **Configure application scopes**
   - Enable:
     - **Read all files and folders stored in Box**
     - **Write all files and folders stored in Box**

6. **Set environment variables**
   ```
   BOX_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   BOX_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

### Gotchas

- **Enterprise app authorization.** If using Box within a company, a Box admin must authorize the app in **Admin Console > Apps > Custom Apps**.
- **Free accounts have limitations.** ~25,000 API calls/month. For production, consider Box Business.
- **Refresh token rotation.** Box refresh tokens are single-use. Each refresh returns a new refresh token that must be stored. If a refresh fails or is replayed, the user must re-authorize.
- **Access tokens expire after 60 minutes.** Refresh tokens expire after 60 days of non-use.
- **Redirect URI must match exactly**, including trailing slashes. Box is strict about URI matching.

---

## Summary Table

| Provider | Console URL | Client ID Env Var | Client Secret Env Var | Production Approval |
|---|---|---|---|---|
| Google Drive | https://console.cloud.google.com/ | `GOOGLE_DRIVE_CLIENT_ID` | `GOOGLE_DRIVE_CLIENT_SECRET` | Consent screen verification (days/weeks) |
| OneDrive | https://entra.microsoft.com/ | `ONEDRIVE_CLIENT_ID` | `ONEDRIVE_CLIENT_SECRET` | Publisher verification recommended |
| Dropbox | https://www.dropbox.com/developers/apps | `DROPBOX_CLIENT_ID` | `DROPBOX_CLIENT_SECRET` | Production status review (500 user limit in dev) |
| Box | https://app.box.com/developers/console | `BOX_CLIENT_ID` | `BOX_CLIENT_SECRET` | Enterprise admin authorization required |

## Environment Variables Template

Add these to your `.env` file or docker-compose environment:

```bash
# Storage Providers
STORAGE_PROVIDERS_ENABLED=true

# Google Drive OAuth
GOOGLE_DRIVE_CLIENT_ID=
GOOGLE_DRIVE_CLIENT_SECRET=

# Microsoft OneDrive OAuth
ONEDRIVE_CLIENT_ID=
ONEDRIVE_CLIENT_SECRET=

# Dropbox OAuth
DROPBOX_CLIENT_ID=
DROPBOX_CLIENT_SECRET=

# Box OAuth
BOX_CLIENT_ID=
BOX_CLIENT_SECRET=
```
