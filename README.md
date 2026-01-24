# Protein Design Competition Platform

A reusable platform for running protein design competitions using AlphaFold3 structure prediction.

## Quick Start for SeokLab Members

If you're in the SeokLab GitHub organization and want to run your own competition, the self-hosted runner on `galaxy4` is already available for all seoklab repos.

### Initial Setup

1. **Create your repository** under `seoklab` org
2. **Clone this template** and update paths (see [Setup Guide](#setup-guide) below)
3. **Replace target problems** with your actual targets (see [Replacing Target Problems](#replacing-target-problems))
4. **Set up Netlify** for the submission form
5. **Enable GitHub Pages** for the public site

---

## Replacing Target Problems

The platform comes with example problems. Here's how to replace them with your actual competition targets.

### Files to Modify

| File | Purpose |
|------|---------|
| `docs/targets/config.json` | Problem definitions (names, types, residue counts) |
| `docs/targets/*.pdb` | Reference structures for evaluation |
| `docs/targets/*.a3m` | Pre-computed MSA files (for binder targets) |
| `.github/workflows/check_completion.yml` | Problem-to-reference mapping for evaluation |
| `docs/index.html` | Problem descriptions shown to participants |

### Step 1: Prepare Reference Structures

For each problem, prepare a backbone-only PDB file:

```bash
# Extract backbone atoms (N, CA, C, O) from your reference structure
# Name convention: {problem_id}_bb.pdb or descriptive name

# For monomer problems:
grep -E "^ATOM.*(  N  |  CA |  C  |  O  )" full_structure.pdb > problem_1_bb.pdb

# For binder problems, include both target and binder chains:
# Chain A = participant's binder, Chain B = given target
```

Place all PDB files in `docs/targets/`.

### Step 2: Update config.json

Edit `docs/targets/config.json`:

```json
{
  "problems": [
    {
      "id": "problem_1",
      "name": "Problem 1 - Your Title",
      "description": "Description shown to participants",
      "target_file": "your_target_1.pdb",
      "residue_count": 50,
      "type": "monomer",
      "msa_mode": "none"
    },
    {
      "id": "problem_2",
      "name": "Problem 2 - Binder Design",
      "description": "Design a binder for target X",
      "type": "binder",
      "target_file": "binder_problem_x.pdb",
      "residue_count": 80,
      "target_sequence": "MKTAYIAK...",
      "target_msa_file": "/full/path/to/target_x.a3m",
      "participant_msa_mode": "none",
      "expected_binder_length": [50, 100]
    }
  ]
}
```

**Problem Types:**
- `monomer`: Participant designs a sequence to fold into the target structure
- `binder`: Participant designs a binder sequence for a given target protein

**MSA Modes:**
- `none`: No MSA search (faster, for de novo design)
- `search`: Run MSA search (default AF3 behavior)
- `precomputed`: Use pre-calculated MSA file

### Step 3: Update Workflow Evaluation Mapping

Edit `.github/workflows/check_completion.yml`, find the `PROBLEM_REFS` section (~lines 224-230):

```bash
declare -A PROBLEM_REFS=(
  ["problem_1"]="your_target_1.pdb:monomer"
  ["problem_2"]="binder_problem_x.pdb:binder"
  ["problem_3"]="your_target_3.pdb:monomer"
  # Add/remove as needed
)
```

Format: `["problem_id"]="reference_file.pdb:problem_type"`

### Step 4: Update Submission Form

Edit `docs/index.html` to update problem descriptions shown to participants:

```html
<div class="problem-section">
  <h3>Problem 1: Your Title</h3>
  <p>Description of what participants should design...</p>
  <p><strong>Target length:</strong> 50 residues</p>
</div>
```

### Step 5: For Binder Problems - Prepare MSA

If your binder problem uses a pre-computed MSA for the target:

```bash
# Generate MSA using your preferred tool (e.g., jackhmmer, hhblits)
# Save as .a3m format
# Reference the full path in config.json target_msa_file field
```

### Step 6: Clear Old Results (if any)

```bash
# Remove old evaluation results
rm -rf docs/results/*/

# Reset leaderboard
echo '{"problems": {}, "overall_rankings": [], "last_updated": ""}' > docs/leaderboard_data.json
```

### Example: Current Demo Problems

| Problem | Type | Reference | Residues |
|---------|------|-----------|----------|
| Problem 1 | monomer | 3v86_bb.pdb | 27 |
| Problem 2 | monomer | 4r80_bb.pdb | 76 |
| Problem 3 | monomer | 1qys_bb.pdb | 91 |
| Problem 4 | monomer | 6wi5_bb.pdb | 92 |
| Problem 5 | binder | binder_problem_9bk5.pdb | 78 |

---

## Setup Guide

### Step 1: Create Your Repository

```bash
git clone https://github.com/seoklab/design-test.git my-competition
cd my-competition
git remote set-url origin https://github.com/seoklab/my-competition.git
```

### Step 2: Update Paths

Replace paths with your username in these files:

**`.github/workflows/process_submission.yml`** (~lines 15, 58):
```yaml
SUBMISSIONS_BASE: /data/galaxy4/user/YOUR_USER/my-competition/submissions
QUEUE_DIR: /data/galaxy4/user/YOUR_USER/job_queue
```

**`.github/workflows/check_completion.yml`** (~lines 15-18):
```yaml
SUBMISSIONS_BASE: /data/galaxy4/user/YOUR_USER/my-competition/submissions
PUBLIC_RESULTS: /data/galaxy4/user/YOUR_USER/my-competition/public_results
SITE_URL: https://your-site.netlify.app
ADMIN_EMAIL: your-email@example.com
```

### Step 3: Create Directories on Galaxy4

```bash
mkdir -p /data/galaxy4/user/YOUR_USER/my-competition/submissions
mkdir -p /data/galaxy4/user/YOUR_USER/my-competition/public_results
mkdir -p /data/galaxy4/user/YOUR_USER/job_queue
chmod 777 /data/galaxy4/user/YOUR_USER/my-competition/submissions
chmod 777 /data/galaxy4/user/YOUR_USER/my-competition/public_results
```

### Step 4: Set Up Job Queue Cron

Add to crontab on galaxy4 (`crontab -e`):
```bash
*/15 * * * * for f in /data/galaxy4/user/YOUR_USER/job_queue/*.sh; do [ -f "$f" ] && sbatch "$f" && mv "$f" "$f.done"; done
```

### Step 5: Set Up Netlify

1. Create account at [netlify.com](https://netlify.com)
2. **Add new site** → **Import an existing project** → Connect to GitHub
3. Select your repository
4. Add environment variables in **Site settings**:
   - `GITHUB_TOKEN`: Personal access token with `repo` scope
   - `GITHUB_OWNER`: `seoklab`
   - `GITHUB_REPO`: Your repo name

### Step 6: Update Form Submit URL

Edit `docs/index.html`:
```javascript
const SUBMIT_URL = 'https://your-site.netlify.app/api/submit';
```

### Step 7: Enable GitHub Pages

1. **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, Folder: `/docs`

---

## Architecture

```
User → Web Form → Netlify Function → GitHub Actions
       (GitHub Pages)                     ↓
                                   Process Submission
                                   (Self-hosted runner on galaxy4)
                                          ↓
                                   SLURM Job Queue → AlphaFold3
                                          ↓
                                   Check Completion (every minute)
                                          ↓
                                   Evaluate + Update Leaderboard
                                          ↓
                              Email + Viewer Link → User
```

## File Structure

```
├── .github/workflows/
│   ├── process_submission.yml    # Handles new submissions
│   ├── check_completion.yml      # Checks jobs, evaluates, updates leaderboard
│   └── end_competition.yml       # Final evaluation workflow
├── docs/                         # Public site (GitHub Pages)
│   ├── index.html                # Submission form
│   ├── viewer.html               # Mol* structure viewer
│   ├── leaderboard.html          # Competition leaderboard
│   ├── leaderboard_data.json     # Leaderboard data
│   ├── targets/                  # Reference structures
│   │   ├── config.json           # Problem definitions
│   │   └── *.pdb                 # Reference PDB files
│   └── results/                  # Packaged results (per token)
├── netlify/functions/
│   └── submit.js                 # Form submission API
├── scripts/
│   ├── process_multi_submission.py  # Parse submission
│   ├── run_af3.py                   # Generate SLURM script
│   ├── package_results.py           # Package results with token
│   ├── evaluate_structure.py        # TMalign/lDDT evaluation
│   └── update_leaderboard.py        # Aggregate rankings
└── submissions/                  # (gitignored) On galaxy4
```

## Evaluation Metrics

### Monomer Problems
| Metric | Description |
|--------|-------------|
| BB-lDDT | Backbone local distance difference test (primary) |
| RMSD | Root mean square deviation after alignment |
| TM-score | Template modeling score |
| pTM | AlphaFold predicted TM-score |
| pLDDT | AlphaFold predicted lDDT |

### Binder Problems
| Category | Metrics |
|----------|---------|
| Binder Only | BB-lDDT, RMSD, TM-score (binder chain vs reference) |
| Complex | iLDDT, TM-score, RMSD (full complex alignment) |
| AlphaFold3 | ipTM, pTM, pLDDT |

## Maintenance

### Enable/Disable Scheduled Checks

In `.github/workflows/check_completion.yml`:
```yaml
on:
  schedule:
    - cron: '* * * * *'  # Comment out to disable
  workflow_dispatch:      # Keep for manual triggers
```

### Manual Workflow Trigger

**Actions** → **Check Job Completion** → **Run workflow**

### Netlify Auto-Deploy (Optional)

To auto-deploy when results are ready:
1. In Netlify: **Site settings** → **Build hooks** → Add hook
2. Add as GitHub secret: `NETLIFY_BUILD_HOOK`
3. Add step in `check_completion.yml` after commit:
```yaml
- name: Trigger Netlify deploy
  if: steps.check.outputs.results_updated == 'true'
  run: curl -X POST -d {} ${{ secrets.NETLIFY_BUILD_HOOK }}
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Git push rejected | `git pull --rebase && git push` |
| Permission denied | Run `chmod 777` on submission directories |
| Form not submitting | Check Netlify env vars and function logs |
| No emails | Check sendmail config, may have delay (5-10 min normal) |
| Workflow not running | Check Actions tab, verify runner is online |
| Wrong evaluation scores | Ensure reference PDB residue numbering starts at 1 |

## Credits

- [AlphaFold3](https://github.com/google-deepmind/alphafold3) - Structure prediction
- [TMalign/USalign](https://zhanggroup.org/TM-align/) - Structure alignment
- [PDBe-Molstar](https://github.com/molstar/pdbe-molstar) - 3D visualization
- [SeokLab](https://seoklab.org)
