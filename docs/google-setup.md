# Google Cloud OAuth Setup

This document describes the manual setup required to enable the Contract Review Agent to authenticate with Gmail and Google Drive APIs.

## Prerequisites

- A Google Cloud account
- A demo Google account to use as the test user

## Step-by-Step Setup Checklist

Follow these steps in https://console.cloud.google.com with your demo Google account:

### 1. Create Project
- [ ] Go to Google Cloud Console: https://console.cloud.google.com
- [ ] Click on the project dropdown at the top
- [ ] Click "New Project"
- [ ] Project name: `contract-review-demo`
- [ ] Click "Create"
- [ ] Record the Project ID: ________________

### 2. Enable Required APIs
- [ ] In the Google Cloud Console, go to "APIs & Services" → "Library"
- [ ] Search for "Gmail API"
- [ ] Click on it and click "Enable"
- [ ] Search for "Google Drive API"
- [ ] Click on it and click "Enable"

### 3. Configure OAuth Consent Screen
- [ ] Go to "APIs & Services" → "OAuth consent screen"
- [ ] Select "External" for user type
- [ ] Click "Create"
- [ ] Fill in the form:
  - App name: `Contract Review Agent`
  - User support email: (enter your demo account email)
  - Developer contact: (enter your demo account email)
- [ ] Click "Save and Continue"
- [ ] On "Scopes" step, click "Save and Continue" (scopes will be set by the script)
- [ ] On "Test users" step:
  - [ ] Click "Add users"
  - [ ] Add your demo account email as a test user
  - [ ] Click "Save and Continue"
- [ ] Click "Back to Dashboard"

### 4. Create OAuth 2.0 Desktop Application Credentials
- [ ] Go to "APIs & Services" → "Credentials"
- [ ] Click "Create Credentials" → "OAuth client ID"
- [ ] Application type: **Desktop app**
- [ ] Name: `Contract Review Agent Desktop`
- [ ] Click "Create"
- [ ] Click "Download JSON" (or the download icon)
- [ ] Save the file as `credentials.json` in the repository root directory (`D:\SmartWave\contract-review-agent\credentials.json`)
- [ ] Click "Close"

## Running the OAuth Flow

Once the above setup is complete, run the following command in your terminal:

```bash
.venv\Scripts\python -m scripts.google_auth
```

This will:
1. Open a browser window for you to grant permission
2. Display the authorized email address in the terminal (expected output: `Authorized as: <your-demo-account@gmail.com>`)
3. Save credentials to `token.json` in the repository root

**Note:** The `token.json` file contains sensitive OAuth credentials and is already in `.gitignore`. Never commit this file.

## Notes for Developers

- **Demo Account Email:** ________________
- **Project ID:** ________________
- **Setup Date:** ________________
- **Completed By:** ________________
