# Cloudflare Worker Setup

This worker receives form submissions from the competition webpage and creates GitHub Issues automatically.

## Prerequisites

1. A [Cloudflare account](https://dash.cloudflare.com/sign-up) (free tier works)
2. A GitHub Personal Access Token with `repo` scope

## Setup Steps

### 1. Create GitHub Personal Access Token

1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Give it a name like "protein-competition-worker"
4. Select scope: `repo` (full control of private repositories)
5. Generate and **copy the token** (you won't see it again)

### 2. Deploy to Cloudflare Workers

**Option A: Using Cloudflare Dashboard (easiest)**

1. Go to [Cloudflare Workers Dashboard](https://dash.cloudflare.com/?to=/:account/workers-and-pages)
2. Click "Create application" → "Create Worker"
3. Name it `protein-competition` (or any name you prefer)
4. Click "Deploy"
5. Click "Edit code"
6. Delete the default code and paste the contents of `worker.js`
7. Click "Save and deploy"

**Option B: Using Wrangler CLI**

```bash
# Install wrangler
npm install -g wrangler

# Login to Cloudflare
wrangler login

# Create wrangler.toml in this directory
cat > wrangler.toml << 'EOF'
name = "protein-competition"
main = "worker.js"
compatibility_date = "2024-01-01"

[vars]
ALLOWED_ORIGIN = "https://YOUR_USERNAME.github.io"
EOF

# Deploy
wrangler deploy
```

### 3. Configure Environment Variables

In Cloudflare Dashboard:

1. Go to Workers & Pages → your worker → Settings → Variables
2. Add these **Environment Variables**:

| Variable | Value | Encrypt? |
|----------|-------|----------|
| `GITHUB_TOKEN` | Your GitHub PAT from step 1 | Yes (click Encrypt) |
| `GITHUB_OWNER` | Your GitHub username or org | No |
| `GITHUB_REPO` | `protein-competition` | No |
| `ALLOWED_ORIGIN` | `https://YOUR_USERNAME.github.io` | No |

3. Click "Save and deploy"

### 4. Get Your Worker URL

Your worker URL will be:
```
https://protein-competition.YOUR_SUBDOMAIN.workers.dev
```

Find your subdomain in Workers & Pages → Overview (shown at the top).

### 5. Update the Webpage

Edit `docs/index.html` and update line 334:

```javascript
const WORKER_URL = 'https://protein-competition.YOUR_SUBDOMAIN.workers.dev';
```

Replace `YOUR_SUBDOMAIN` with your actual Cloudflare subdomain.

### 6. Test

1. Open your GitHub Pages site
2. Fill out the form and submit
3. Check that a new issue appears in your repository with the "submission" label

## Troubleshooting

**CORS errors:**
- Make sure `ALLOWED_ORIGIN` matches your GitHub Pages URL exactly (including https://)

**401/403 from GitHub API:**
- Check that your PAT hasn't expired
- Verify the PAT has `repo` scope
- Make sure `GITHUB_OWNER` and `GITHUB_REPO` are correct

**Worker not responding:**
- Check the worker logs in Cloudflare Dashboard → Workers → your worker → Logs

## Security Notes

- The GitHub PAT is stored encrypted in Cloudflare and never exposed to users
- The worker validates all input before creating issues
- CORS restricts submissions to your GitHub Pages domain only
- Rate limiting is handled by GitHub API limits (5000 requests/hour with PAT)
