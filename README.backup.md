# Protein Design Competition Platform

A reusable platform for running protein design competitions using AlphaFold3 structure prediction.

## For SeokLab Members

If you're in the SeokLab GitHub organization and want to run your own competition, follow these steps. The self-hosted runner on `galaxy4` is already available for all seoklab repos.

### Step 1: Create Your Repository

1. Create a new repo under `seoklab` org (e.g., `seoklab/designcomp-kidds`)
2. Clone this template:
   ```bash
   git clone https://github.com/seoklab/design-test.git designcomp-kidds
   cd designcomp-kidds
   git remote set-url origin https://github.com/seoklab/designcomp-kidds.git
   ```

### Step 2: Update Paths (Replace `j2ho` with your username)

**Files to edit:**

1. **`.github/workflows/process_submission.yml`** (lines ~23, ~59):
   ```yaml
   # Change:
   SUBMISSION_DIR="/data/galaxy4/user/j2ho/kidds2026/protein-competition/submissions/..."
   QUEUE_DIR="/data/galaxy4/user/j2ho/job_queue"

   # To:
   SUBMISSION_DIR="/data/galaxy4/user/yubeen/my-competition/submissions/..."
   QUEUE_DIR="/data/galaxy4/user/yubeen/job_queue"
   ```

2. **`.github/workflows/check_completion.yml`** (lines ~15-17):
   ```yaml
   # Change:
   SUBMISSIONS_BASE: /data/galaxy4/user/j2ho/kidds2026/protein-competition/submissions
   PUBLIC_RESULTS: /data/galaxy4/user/j2ho/kidds2026/protein-competition/public_results
   SITE_URL: https://seoklab.github.io/design-test

   # To:
   SUBMISSIONS_BASE: /data/galaxy4/user/yubeen/my-competition/submissions
   PUBLIC_RESULTS: /data/galaxy4/user/yubeen/my-competition/public_results
   SITE_URL: https://seoklab.github.io/designcomp-kidds
   ```

3. **`scripts/run_af3.py`** - Update AF3 paths if different

### Step 3: Create Directories on Galaxy4

SSH into galaxy4 and create your directories:
```bash
mkdir -p /data/galaxy4/user/yubeen/my-competition/submissions
mkdir -p /data/galaxy4/user/yubeen/my-competition/public_results
mkdir -p /data/galaxy4/user/yubeen/job_queue
chmod 777 /data/galaxy4/user/yubeen/my-competition/submissions
chmod 777 /data/galaxy4/user/yubeen/my-competition/public_results
```

### Step 4: Set Up Job Queue Cron

Add to your crontab on galaxy4 (`crontab -e`):
```bash
*/15 * * * * for f in /data/galaxy4/user/yubeen/job_queue/*.sh; do [ -f "$f" ] && sbatch "$f" && mv "$f" "$f.done"; done
```

### Step 5: Enable GitHub Pages

1. Go to your repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, Folder: `/docs`
4. Your site will be at `https://seoklab.github.io/designcomp-kidds/`

### Step 6: Set Up Netlify

1. Create account at [netlify.com](https://netlify.com)
2. **Add new site** → **Import an existing project** → Connect to GitHub
3. Select your `seoklab/designcomp-kidds` repo
4. Go to **Site settings** → **Environment variables**, add:
   - `GITHUB_TOKEN`: Create at github.com/settings/tokens (need `repo` scope)
   - `GITHUB_OWNER`: `seoklab`
   - `GITHUB_REPO`: `designcomp-kidds`
5. Note your Netlify URL (e.g., `https://your-site-name.netlify.app`)

### Step 7: Update Form Submit URL

Edit `docs/index.html`, find and update:
```javascript
const SUBMIT_URL = 'https://your-site-name.netlify.app/api/submit';
```

### Step 8: Customize Your Competition

Edit `docs/index.html`:
- Title and subtitle
- Competition info (goal, dates, deadline)
- Footer

### Step 9: Push and Test

```bash
git add -A
git commit -m "Configure for my competition"
git push origin main
```

Test by submitting a sequence at your GitHub Pages URL.

---

## Architecture

```
User → Web Form → Netlify Function → GitHub Issue
       (GitHub Pages)                     ↓
                                   Process Submission
                                   (GitHub Actions on galaxy4)
                                          ↓
                                   SLURM Job Queue → AlphaFold3
                                          ↓
                                   Check Completion
                                   (GitHub Actions)
                                          ↓
                              Email + Viewer Link → User
```

## File Structure

```
├── .github/workflows/
│   ├── process_submission.yml    # Handles new submissions
│   └── check_completion.yml      # Checks for completed jobs
├── docs/                         # GitHub Pages (public site)
│   ├── index.html                # Submission form
│   ├── viewer.html               # Mol* structure viewer
│   └── results/                  # Packaged results
├── netlify/functions/
│   └── submit.js                 # Form submission API
├── scripts/
│   ├── parse_submission.py       # Parse issue → submission.json
│   ├── prepare_af3_input.py      # Generate AF3 input JSON
│   ├── run_af3.py                # Generate SLURM script
│   └── package_results.py        # Package results with token
├── submissions/                  # (gitignored) On galaxy4
└── public_results/               # (gitignored) On galaxy4
```

## Maintenance

### Enable/Disable Scheduled Result Checks

In `.github/workflows/check_completion.yml`:
```yaml
on:
  # Comment out schedule to disable automatic checks
  schedule:
    - cron: '* * * * *'  # Every minute
  workflow_dispatch:      # Keep this for manual triggers
```

### Manual Trigger

**Actions** → **Check Job Completion** → **Run workflow**

### Updating the Site

- Changes to `docs/` → Auto-deploy via GitHub Pages
- Changes to `netlify/functions/` → Need to redeploy on Netlify

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Git push rejected | `git pull --rebase && git push` |
| Permission denied | Run `chmod 777` on submission directories |
| Form not submitting | Check Netlify env vars and function logs |
| No emails | Check sendmail config, verify email in submission.json |
| Workflow not running | Check Actions tab for errors, verify runner is online |

## Credits

- [AlphaFold3](https://github.com/google-deepmind/alphafold3) - Structure prediction
- [PDBe-Molstar](https://github.com/molstar/pdbe-molstar) - 3D visualization
- [SeokLab](https://seoklab.org)
