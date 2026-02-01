# KIDDS 2026 Protein Design Competition - System Overview

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Web Form       │────▶│  Netlify        │────▶│  GitHub Issue   │
│  (GitHub Pages) │     │  Function       │     │  (submission)   │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Email Results  │◀────│  Check Job      │◀────│  Process        │
│  to User        │     │  Completion     │     │  Submission     │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                │                        │
                                ▼                        ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │  Mol* Viewer    │     │  SLURM/AF3      │
                        │  (GitHub Pages) │     │  (HPC Cluster)  │
                        └─────────────────┘     └─────────────────┘
```

## Components

### 1. Web Form (`docs/index.html`)
- **URL**: `https://seoklab.github.io/design-test/`
- Collects: Participant ID, Email, Sequence Name, Amino Acid Sequence
- Submits to Netlify Function
- Shows success message with email notification reminder

### 2. Netlify Function (`netlify/functions/submit.js`)
- **Endpoint**: `https://kidds2026.netlify.app/api/submit`
- Validates input and triggers a GitHub `repository_dispatch` event (`event_type`: `new_submission`)
- Does **not** create a public GitHub Issue by default (avoids exposing sequences)
- Returns success/error to user

### 3. Process Submission Workflow (`.github/workflows/process_submission.yml`)
- **Trigger**: `repository_dispatch` event (`new_submission`) — or (optional) GitHub Issue labeled `submission` for issue-based submissions
- **Runner**: Self-hosted on galaxy4 HPC
- Steps:
  1. Create submission directory
  2. Parse submission payload → `submission.json`
  3. Prepare AF3 input → `af3_input.json`
  4. Generate SLURM script → copy to job queue
  5. Send confirmation email
  6. Comment on issue

### 4. Job Queue & Cron
- **Queue directory**: `/data/galaxy4/user/j2ho/job_queue/`
- **Cron** (j2ho): Submits queued jobs every 15 minutes via `sbatch`
- Jobs run AlphaFold3 on `gpu-micro.q` partition

### 5. Check Completion Workflow (`.github/workflows/check_completion.yml`)
- **Trigger**: Manual (`workflow_dispatch`) or scheduled cron (currently disabled)
- Scans submission directories for completed models
- Packages results with secret token
- Sends results email to user
- Comments on GitHub issue with viewer link
- Commits results to `docs/results/<token>/`

### 6. Structure Viewer (`docs/viewer.html`)
- **URL**: `https://seoklab.github.io/design-test/viewer.html?token=<TOKEN>`
- Uses PDBe-Molstar for 3D visualization
- Displays pLDDT confidence coloring
- Provides download links

## File Structure

```
protein-competition/
├── .github/
│   └── workflows/
│       ├── process_submission.yml   # Handles new submissions
│       └── check_completion.yml     # Checks for completed jobs
├── docs/                            # GitHub Pages (public)
│   ├── index.html                   # Submission form
│   ├── viewer.html                  # Mol* structure viewer
│   └── results/<token>/             # Packaged results (public but unlisted)
├── netlify/
│   └── functions/
│       └── submit.js                # Form submission handler
├── scripts/
│   ├── parse_submission.py          # Parse issue → submission.json
│   ├── prepare_af3_input.py         # Generate AF3 input JSON
│   ├── run_af3.py                   # Generate SLURM script
│   └── package_results.py           # Package results with token
├── submissions/                     # (gitignored) Active submissions
│   └── submission_<N>/
│       ├── submission.json
│       ├── af3_input.json
│       ├── status.json
│       └── submission_<N>/          # AF3 output
└── public_results/                  # (gitignored) Packaged results
```

## URLs

| Purpose | URL |
|---------|-----|
| Submission Form | `https://seoklab.github.io/design-test/` |
| Netlify API | `https://kidds2026.netlify.app/api/submit` |
| Results Viewer | `https://seoklab.github.io/design-test/viewer.html?token=<TOKEN>` |
| GitHub Repo | `https://github.com/seoklab/design-test` |

## Email Notifications

Users receive emails at two points:

1. **Submission Received**
   - Sent by: `process_submission.yml`
   - Contains: Confirmation, Submission ID

2. **Results Ready**
   - Sent by: `check_completion.yml`
   - Contains: Viewer link, Download link

Both sent via `sendmail` from HPC with `From: noreply@seoklab.org`

## Privacy Model

- Submissions create GitHub Issues (visible to repo watchers)
- Results are stored with random tokens (32-char alphanumeric)
- Only the submitter receives the token via email
- Results are publicly accessible IF you know the token
- All results become fully public when competition ends

## Configuration

### To Enable/Disable Scheduled Checks

In `.github/workflows/check_completion.yml`:
```yaml
on:
  # Uncomment to enable scheduled checks
  # schedule:
  #   - cron: '* * * * *'
  workflow_dispatch:  # Always allow manual trigger
```

### Environment Variables

Set in workflow files:
- `SUBMISSIONS_BASE`: `/data/galaxy4/user/j2ho/kidds2026/protein-competition/submissions`
- `PUBLIC_RESULTS`: `/data/galaxy4/user/j2ho/kidds2026/protein-competition/public_results`
- `SITE_URL`: `https://seoklab.github.io/design-test`

## Maintenance

### Manual Workflow Triggers

- **Check Job Completion**: Actions → Check Job Completion → Run workflow
- **Process Submission**: Add `submission` label to an issue

### Common Issues

1. **Git push rejected**: Run `git pull --rebase && git push`
2. **Permission denied on status.json**: File owned by different user
3. **Netlify changes not reflected**: Need to redeploy Netlify
4. **GitHub Pages changes**: Auto-deploy on push (1-2 min delay)
