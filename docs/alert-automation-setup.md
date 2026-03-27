# Alert Automation Setup Guide

This guide explains how to connect your monitoring tools so that Aelu automatically
diagnoses and fixes problems without you needing to do anything.

## How It Works

When something goes wrong, this is what happens automatically:

1. **A test fails or the app goes down** — GitHub, Sentry, or UptimeRobot detects it
2. **An AI agent reads the error** — Claude analyzes what went wrong
3. **The agent creates a fix** — A pull request appears on GitHub with the fix
4. **You review and merge** — or set up auto-merge for low-risk fixes

---

## Step 1: Add Your Anthropic API Key to GitHub

The AI agent needs a Claude API key to work. This is the only setup step that's required.

1. Go to https://console.anthropic.com/settings/keys
2. Click "Create Key" — name it "Aelu CI Auto-Fix"
3. Copy the key (starts with `sk-ant-...`)
4. Go to https://github.com/AeluApp/mandarin/settings/secrets/actions
5. Click "New repository secret"
6. Name: `ANTHROPIC_API_KEY`
7. Value: paste the key
8. Click "Add secret"

**Cost:** Each auto-fix costs about $0.05-0.50 in API usage (Claude Sonnet).

---

## Step 2: Connect Sentry (Error Monitoring)

Sentry catches crashes and errors in your live app. Right now these show up as emails.
Let's make them create GitHub issues automatically.

### Option A: Sentry GitHub Integration (Recommended)

1. In Sentry, go to **Settings → Integrations → GitHub**
2. Click "Install" and authorize for `AeluApp/mandarin`
3. Go to **Alerts → Create Alert Rule**
4. Set conditions:
   - When: "An event is seen" with level "error"
   - Then: "Create a GitHub issue" in `AeluApp/mandarin`
   - Add label: `sentry`
5. Save the rule

Now every new Sentry error automatically creates a GitHub issue.

### Option B: Sentry Webhook (triggers auto-fix directly)

1. In Sentry, go to **Settings → Integrations → Webhooks**
2. Webhook URL:
   ```
   https://api.github.com/repos/AeluApp/mandarin/dispatches
   ```
3. This requires a GitHub Personal Access Token — see Step 4 below.

---

## Step 3: Connect UptimeRobot (Downtime Alerts)

UptimeRobot checks if your app is alive. Right now it emails you.
Let's make it trigger auto-recovery.

1. Log into UptimeRobot
2. Go to **My Settings → Alert Contacts**
3. Click "Add Alert Contact"
4. Type: **Webhook**
5. URL:
   ```
   https://api.github.com/repos/AeluApp/mandarin/dispatches
   ```
6. POST body:
   ```json
   {
     "event_type": "incident-response",
     "client_payload": {
       "source": "uptimerobot",
       "severity": "critical",
       "details": "Monitor *monitorFriendlyName* is *alertTypeFriendlyName*. URL: *monitorURL*"
     }
   }
   ```
7. Headers:
   ```
   Authorization: Bearer YOUR_GITHUB_PAT
   Accept: application/vnd.github.v3+json
   ```
8. Save and attach this contact to your Aelu monitors

---

## Step 4: GitHub Personal Access Token (for webhooks)

Both Sentry webhooks and UptimeRobot need a GitHub token to trigger workflows.

1. Go to https://github.com/settings/tokens?type=beta
2. Click "Generate new token"
3. Name: "Aelu Alert Automation"
4. Repository access: Only select `AeluApp/mandarin`
5. Permissions: **Actions** (read & write)
6. Generate and copy the token
7. Use this token in the UptimeRobot and Sentry webhook headers

---

## What Happens After Setup

| Alert Source | What Triggers | What Happens |
|---|---|---|
| **GitHub CI fails** | Test failure, lint error, deploy error | AI agent reads logs, creates fix PR |
| **Sentry error** | App crash, unhandled exception | GitHub issue created, labeled `sentry` |
| **UptimeRobot** | App down or slow | Auto-restart attempted, incident issue created, AI agent investigates |

### What You Need To Do

- **Review and merge fix PRs** — the agent creates them, you approve them
- **Check GitHub issues** — for problems that need your attention
- **Everything else is automatic**

---

## Costs

| Service | Cost |
|---|---|
| Claude API (auto-fix) | ~$0.05-0.50 per fix attempt |
| Sentry | Free tier covers 5,000 errors/month |
| UptimeRobot | Free tier covers 50 monitors |
| GitHub Actions | Free for public repos, 2,000 min/month for private |

---

## Troubleshooting

**Auto-fix didn't run after CI failure:**
- Check that `ANTHROPIC_API_KEY` is set in GitHub secrets
- The workflow only runs on failures on the `main` branch (not PRs)

**UptimeRobot webhook not working:**
- Verify the GitHub PAT hasn't expired
- Check the webhook URL matches exactly

**Sentry issues not appearing:**
- Verify the Sentry-GitHub integration is installed
- Check alert rules are active
