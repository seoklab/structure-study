# Protein Design Competition Platform

A platform for running protein design competitions using AlphaFold3 structure prediction, hosted on GitHub Pages with GitHub Issues for submissions.

## How to Add a New Problem

### Method 1: GitHub Issue (Recommended)

1. Go to **Issues** → **New issue** → **New Competition Problem**
2. Fill in the form fields (name, type, session, server path to PDB, etc.)
3. Submit — the workflow automatically:
   - Copies the PDB file to `docs/targets/`
   - Updates `docs/targets/config.json`
   - Comments the new problem ID on the issue

### Method 2: Manual

1. Place your reference PDB file in `docs/targets/`
2. Add the problem entry to the `problems` array in `docs/targets/config.json`
3. Add the problem ID to the appropriate session's `problems` list
4. Commit and push

---

## Problem Fields Reference

| Field | Required | Description |
|-------|----------|-------------|
| `id` | auto | `problem_N` (auto-assigned via Issue, manual otherwise) |
| `name` | yes | Display name shown to participants |
| `type` | yes | `monomer` or `binder` |
| `session` | yes | Session key (e.g. `week1`) |
| `description` | yes | Problem description |
| `target_file` | auto | PDB filename in `docs/targets/` |
| `residue_count` | auto | Counted from PDB CA atoms |
| `primary_metric` | yes | Metric used for ranking (see below) |
| `msa_mode` | yes | `none`, `search`, or `precomputed` |

**Binder-only fields:**

| Field | Description |
|-------|-------------|
| `target_sequence` | Full amino acid sequence of the target protein |
| `target_msa_file` | Absolute path to precomputed `.a3m` file on the server |
| `participant_msa_mode` | MSA mode for the participant's binder chain |
| `expected_binder_length` | `[min, max]` residue count for the designed binder |

---

## Session Management

Sessions are defined in `config.json` under `sessions`. Each has:
- `status`: `active` (accepting submissions), `upcoming`, or `archived`
- `problems`: list of problem IDs belonging to that session

The `active_session` field controls which session is shown by default in the submission form. Only problems in an `active` or `upcoming` session accept submissions.

---

## Metrics Reference

Available values for `primary_metric`:

| Metric | Type | Description |
|--------|------|-------------|
| `bb_lddt` | monomer | Backbone lDDT |
| `bb_lddt_cov` | monomer | lDDT × Coverage (penalizes partial matches) |
| `tm_score` | both | Template modeling score |
| `binder_lddt` | binder | Binder chain lDDT |
| `interface_lddt` | binder | Interface lDDT |
| `iptm` | binder | AlphaFold3 interface pTM |

---

## File Structure

```
├── .github/
│   ├── ISSUE_TEMPLATE/         # Issue forms (submission, new problem)
│   └── workflows/
│       ├── process_submission.yml   # Handles sequence submissions
│       ├── check_completion.yml     # Monitors SLURM jobs, evaluates, updates leaderboard
│       ├── add_problem.yml          # Adds new problem from issue
│       └── end_competition.yml      # Final evaluation
├── docs/                            # GitHub Pages site
│   ├── index.html                   # Main page
│   ├── submit.html                  # Submission form
│   ├── leaderboard.html             # Leaderboard
│   ├── viewer.html                  # Mol* structure viewer
│   ├── targets/
│   │   ├── config.json              # Problem + session definitions
│   │   └── *.pdb                    # Reference structures
│   └── results/                     # Per-submission results
└── scripts/
    ├── parse_issue_submission.py     # Parse sequence submission issues
    ├── parse_new_problem.py          # Parse new problem issues
    ├── process_multi_submission.py   # Prepare AF3 SLURM jobs
    ├── evaluate_structure.py         # TMalign/lDDT evaluation
    └── update_leaderboard.py         # Aggregate rankings
```

## Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `process_submission.yml` | Issue opened with `submission` label | Parse sequences, prepare AF3 jobs |
| `check_completion.yml` | Schedule (every minute) + manual | Check SLURM jobs, evaluate, update leaderboard |
| `add_problem.yml` | Issue opened with `new-problem` label | Add new competition problem |
| `end_competition.yml` | Manual | Final evaluation and archival |

## Credits

- [AlphaFold3](https://github.com/google-deepmind/alphafold3) — Structure prediction
- [TMalign/USalign](https://zhanggroup.org/TM-align/) — Structure alignment
- [PDBe-Molstar](https://github.com/molstar/pdbe-molstar) — 3D visualization
- [SeokLab](https://seoklab.org)
