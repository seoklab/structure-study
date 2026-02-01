# Protein Competition - Progress Summary

**Last updated:** 2025-01-19
**Status:** Phase 2 complete, ready for deployment

## Requirements Recap
1. ✅ Participants submit amino acid sequences via Netlify form (`repository_dispatch`) — GitHub Issues supported as an alternative
2. ✅ AF3 modeling via sbatch to gpu-micro.q
3. ✅ Private results with Mol* viewer (pLDDT coloring)
4. ✅ Unlimited resubmissions
5. ⚠️ Privacy: GitHub Issues are public (see alternatives below)
6. ✅ End competition → publish all results

## Completed Components

### GitHub Issue Template
- `.github/ISSUE_TEMPLATE/submit_sequence.yml` - YAML form
- Fields: participant_id, sequence_name, amino_acid_sequence
- Auto-labels: "submission"

### GitHub Actions Workflows
- `process_submission.yml` - Triggered on "submission" label
  - Runs on self-hosted runner (af3-runner)
  - Validates → AF3 JSON → sbatch to gpu-micro.q
  - Saves status.json with SLURM job ID

- `check_completion.yml` - Runs every 15 min (cron)
  - Checks sacct for completed jobs
  - Packages results with unique token
  - Comments private viewer link on issue

- `end_competition.yml` - Manual trigger (type "END")
  - Publishes all results to docs/ for GitHub Pages
  - Generates gallery page

### Python Scripts (scripts/)
- `parse_submission.py` - Parse issue body, validate amino acids
- `prepare_af3_input.py` - Generate AF3 JSON (dialect: alphafold3, version: 1)
- `run_af3.py` - Generate sbatch script, submit to SLURM
  - Partition: gpu-micro.q
  - Conda: /opt/conda/envs/alphafold3
- `check_job_status.py` - Check sacct, package results
- `end_competition.py` - Generate public gallery HTML
- `setup_runner.sh` - Self-hosted runner installation

### Mol* Viewer
- `templates/viewer.html` - Web viewer with pLDDT coloring
- Accessed via token: `viewer.html?token=<unique_token>`

## TODO / Not Yet Done
- [ ] Push latest changes to GitHub
- [ ] Set up self-hosted runner on HPC
- [ ] Enable GitHub Pages (Settings → Pages → docs/)
- [ ] Test end-to-end flow
- [ ] Consider GitHub Classroom for privacy (see below)

## Privacy Alternative: GitHub Classroom (RECOMMENDED)

**Why use it:**
- Each participant gets their own **PRIVATE** repo
- Participants **cannot** see each other's submissions
- Organizers can see all repos from dashboard
- Built-in assignment workflow
- Free for education

**Comparison:**

| Feature | Regular Repo | GitHub Classroom |
|---------|--------------|------------------|
| Privacy | Issues public | Each gets private repo |
| Visibility | Everyone sees all | Only own work visible |
| Setup | Single repo | Template + invite link |
| Runner | One self-hosted | Org-level runner |
| End reveal | Publish docs/ | Make all repos public |

**Setup Steps:**

1. **Create GitHub Organization** (if needed)
   - github.com → Settings → Organizations → New

2. **Set up GitHub Classroom**
   - Go to https://classroom.github.com
   - "New classroom" → Select your organization
   - Name it (e.g., "Protein Design Competition 2025")

3. **Make this repo a template**
   - Repo Settings → Check "Template repository"

4. **Create Assignment**
   - Classroom dashboard → "New assignment"
   - Title: "Protein Design Submission"
   - Visibility: Private
   - Template: this repo
   - Grant admin access: Yes (for workflow to work)

5. **Set up Org-level Runner**
   - Organization Settings → Actions → Runners → New runner
   - Label: `af3-runner`
   - This runner serves ALL repos in the org

6. **Share Invite Link**
   - Each participant clicks link → gets private repo clone
   - They create Issues in THEIR repo
   - Workflow runs on org runner

**Changes Needed for Classroom Approach:**

1. Workflow trigger stays same (issues labeled "submission")
2. Each repo has its own results/ directory
3. For end competition:
   - Option A: Make all student repos public
   - Option B: Collect results to central gallery repo
   - Option C: Use GitHub Classroom's "download all" feature

**Workflow for Collecting All Results (end of competition):**
```bash
# Clone all student repos using GitHub CLI
gh repo list YOUR_ORG --json name,url -q '.[] | select(.name | startswith("protein-design-")) | .url' | \
  xargs -I {} git clone {}

# Or use classroom assistant CLI
# pip install classroom-assistant
```

**Decision:** If privacy is important, switch to Classroom approach before launching.

## Key Paths
- Project: `/data/galaxy4/user/j2ho/kidds2026/protein-competition/`
- AF3 conda: `/opt/conda/envs/alphafold3`
- SLURM partition: `gpu-micro.q`

## Commands to Continue

```bash
# Go to project
cd /data/galaxy4/user/j2ho/kidds2026/protein-competition

# Check current status
git status

# Push changes
git add -A
git commit -m "Phase 2: AF3 execution, job monitoring, Mol* viewer"
git push

# Set up runner (on HPC)
./scripts/setup_runner.sh https://github.com/USERNAME/protein-competition RUNNER_TOKEN
```

## File Structure
```
protein-competition/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── submit_sequence.yml
│   │   └── config.yml
│   └── workflows/
│       ├── process_submission.yml
│       ├── check_completion.yml
│       └── end_competition.yml
├── scripts/
│   ├── parse_submission.py
│   ├── prepare_af3_input.py
│   ├── run_af3.py
│   ├── check_job_status.py
│   ├── end_competition.py
│   └── setup_runner.sh
├── templates/
│   └── viewer.html
├── results/          (gitignored, AF3 outputs)
├── public_results/   (packaged results with tokens)
├── docs/             (GitHub Pages output)
├── .gitignore
├── README.md
└── PROGRESS.md       (this file)
```
