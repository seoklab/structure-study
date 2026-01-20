# KIDDS 2026 Winter Workshop - Protein Design Competition

A platform for protein design competitions using AlphaFold3 structure prediction.

**"Become the best human ProteinMPNN!"**

## Quick Links

| Resource | URL |
|----------|-----|
| Submission Form | [seoklab.github.io/design-test](https://seoklab.github.io/design-test/) |
| Structure Viewer | [seoklab.github.io/design-test/viewer.html](https://seoklab.github.io/design-test/viewer.html?token=TOKEN) |
| System Documentation | [docs/SYSTEM_OVERVIEW.md](docs/SYSTEM_OVERVIEW.md) |

## How It Works

1. **Submit** - Participants submit amino acid sequences via web form
2. **Validate** - System validates sequence and queues for processing
3. **Predict** - AlphaFold3 runs on HPC cluster
4. **Notify** - Results emailed privately to participant
5. **View** - Interactive 3D structure viewer with pLDDT coloring

## Project Structure

```
protein-competition/
├── .github/workflows/
│   ├── process_submission.yml    # Handles new submissions
│   └── check_completion.yml      # Checks for completed jobs
├── docs/                         # GitHub Pages
│   ├── index.html                # Submission form
│   ├── viewer.html               # Mol* structure viewer
│   └── results/                  # Packaged results
├── netlify/functions/
│   └── submit.js                 # Form submission API
├── scripts/
│   ├── parse_submission.py       # Parse submissions
│   ├── prepare_af3_input.py      # Generate AF3 input
│   ├── run_af3.py                # Generate SLURM script
│   └── package_results.py        # Package results with token
├── submissions/                  # (gitignored) Active submissions
└── public_results/               # (gitignored) Packaged results
```

## Sequence Requirements

- **Length**: 10 - 5,000 residues
- **Valid amino acids**: A C D E F G H I K L M N P Q R S T V W Y

## For Administrators

### Enable/Disable Scheduled Checks

Edit `.github/workflows/check_completion.yml`:
```yaml
on:
  # Uncomment when competition starts
  # schedule:
  #   - cron: '* * * * *'
  workflow_dispatch:
```

### Manual Workflow Triggers

- **Actions** → **Check Job Completion** → **Run workflow**

### Deploy Changes

- **GitHub Pages** (index.html, viewer.html): Auto-deploys on push
- **Netlify Function** (submit.js): Requires manual redeploy

## Technology Stack

- **Frontend**: HTML/CSS/JavaScript (GitHub Pages)
- **API**: Netlify Functions
- **CI/CD**: GitHub Actions (self-hosted runner)
- **Structure Prediction**: AlphaFold3 on SLURM cluster
- **Visualization**: PDBe-Molstar
- **Notifications**: sendmail

## Roadmap

- [x] Web submission form
- [x] GitHub Issues integration
- [x] AlphaFold3 execution via SLURM
- [x] Mol* viewer with pLDDT coloring
- [x] Email notifications
- [x] Private results with token URLs
- [ ] Results aggregation and leaderboard
- [ ] Competition end: publish all results

## Supported by

[SeokLab](https://seoklab.org)
