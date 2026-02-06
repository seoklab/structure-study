# Protein Design Competition Platform

A platform for running protein design competitions using AlphaFold3 structure prediction. Hosted on GitHub Pages, with all admin actions (new sessions, new problems, sequence submissions) handled via GitHub Issues.

**Site:** https://seoklab.github.io/structure-study

---

## Quick Start (Admin Workflow)

The typical flow for running a competition round:

1. **Create a session** — groups problems into a round (e.g. "Week 3")
2. **Add problems** — define target structures for participants to design sequences for
3. Participants **submit sequences** — via the web form or GitHub Issue
4. AlphaFold3 runs automatically, results appear on the leaderboard

All three steps are done through GitHub Issues. Each action has its own issue template with a dedicated label.

---

## Step 1: Create a New Session

A session is a competition round (e.g. `week3`). Creating a new session automatically archives the previous active session.

### Via GitHub Issue (recommended)

1. Go to [Issues → New issue](https://github.com/seoklab/structure-study/issues/new/choose)
2. Select **"New Session"**
3. Fill in:
   - **Session Key** — short identifier like `week3`, `round2` (no spaces)
   - **Session Name** — display name like "Week 3 - De Novo Design"
   - **Description** — shown to participants
4. Submit the issue

The `new-session` workflow will:
- Add the session to `config.json` with `status: active`
- Set it as the `active_session`
- Archive the previous active session
- Comment on the issue with confirmation

### Via manual edit

Edit `docs/targets/config.json` directly:
```json
"sessions": {
  "week3": {
    "name": "Week 3 - De Novo Design",
    "status": "active",
    "description": "De novo protein design challenges",
    "problems": []
  }
}
```
Set `"active_session": "week3"` and change the old session's status to `"archived"`.

---

## Step 2: Add Problems to the Session

A problem defines a target structure that participants will design sequences for.

### Via GitHub Issue (recommended)

1. Go to [Issues → New issue](https://github.com/seoklab/structure-study/issues/new/choose)
2. Select **"New Competition Problem"**
3. Fill in the required fields:
   - **Problem Name** — e.g. "3-Helix Bundle"
   - **Problem Type** — `monomer` (scaffold design) or `binder` (binder design)
   - **Session** — which session this belongs to (e.g. `week3`)
   - **Description** — shown to participants
   - **Primary Metric** — metric used for ranking (see [Metrics Reference](#metrics-reference))
   - **MSA Mode** — `none`, `search`, or `precomputed`
4. Provide the PDB structure using **one** of three methods:

   | Method | When to use | What to fill in |
   |--------|-------------|-----------------|
   | **Server Path** | PDB already exists on the server | Absolute path, e.g. `/data/galaxy4/user/.../scaffold.pdb` |
   | **File Upload** | You have the PDB file locally | Drag-and-drop the `.pdb` file into the upload field |
   | **Paste Content** | Copy-paste from another source | Enter a filename + paste the raw PDB text |

5. For **binder** problems, also fill in:
   - **Target Sequence** — full amino acid sequence of the target protein
   - **Expected Binder Length** — min,max residue count (e.g. `20,50`)
   - **Target MSA Path** — absolute server path to precomputed `.a3m` file (optional)
6. Submit the issue

The `new-problem` workflow will:
- Write the PDB file to `docs/targets/`
- Assign a problem ID (`problem_6`, `problem_7`, ...)
- Update `config.json` with the problem entry and add it to the session
- Comment on the issue with the new problem ID

### Via the web form

Go to https://seoklab.github.io/structure-study/new-problem.html — this is a GUI that builds the same GitHub Issue for you.

### Via manual edit

1. Place the PDB file in `docs/targets/`
2. Add an entry to the `"problems"` array in `docs/targets/config.json`
3. Add the problem ID to the session's `"problems"` list
4. Commit and push

---

## Step 3: Submit Sequences (Participants)

Participants design amino acid sequences and submit them for AlphaFold3 structure prediction.

### Via the web form (recommended for participants)

1. Go to https://seoklab.github.io/structure-study/submit.html
2. Enter a **Participant ID** (e.g. `team1_week3`)
3. Select the **Session**
4. For each problem, enter 1-5 amino acid sequences
5. Click **Submit** — this creates a GitHub Issue automatically

### What happens after submission

1. The `process_submission` workflow parses the sequences and queues AlphaFold3 SLURM jobs
2. A confirmation comment is posted on the issue with the submission ID
3. The `check_completion` workflow runs every 5 minutes to monitor SLURM jobs
4. When predictions finish, results are evaluated (TMalign, lDDT) and the leaderboard updates
5. A final comment is posted on the issue with a link to view results in the 3D viewer

---

## Tracking Progress via Issues

Every action creates a GitHub Issue with a specific label. You can filter issues to see what's happening:

| Filter | URL | What it shows |
|--------|-----|---------------|
| All submissions | [label:submission](https://github.com/seoklab/structure-study/issues?q=label%3Asubmission) | Every sequence submission |
| Completed | [label:submission label:completed](https://github.com/seoklab/structure-study/issues?q=label%3Asubmission+label%3Acompleted) | Submissions with results ready |
| Errors | [label:error](https://github.com/seoklab/structure-study/issues?q=label%3Aerror) | Any failed workflow (submission, problem, or session) |
| New problems | [label:new-problem](https://github.com/seoklab/structure-study/issues?q=label%3Anew-problem) | All problem additions |
| New sessions | [label:new-session](https://github.com/seoklab/structure-study/issues?q=label%3Anew-session) | All session creations |

Each issue contains the full history as comments:
- **Submission issues** get a confirmation comment when queued, then a results comment with viewer links when done
- **Problem issues** get a comment with the assigned problem ID, session, and residue count
- **Session issues** get a comment confirming which session was archived

Issues with the `error` label had a workflow failure — click through to the linked workflow run for details.

---

## Metrics Reference

Available values for `primary_metric` (used for ranking):

| Metric | Problem Type | Description |
|--------|-------------|-------------|
| `bb_lddt` | monomer | Backbone lDDT |
| `bb_lddt_cov` | monomer | lDDT x Coverage (penalizes partial matches) |
| `tm_score` | both | Template modeling score |
| `binder_lddt` | binder | Binder chain lDDT |
| `interface_lddt` | binder | Interface lDDT |
| `iptm` | binder | AlphaFold3 interface pTM |

---

## File Structure

```
├── .github/
│   ├── ISSUE_TEMPLATE/              # Issue forms
│   │   ├── new-session.yml          # New session form
│   │   └── new-problem.yml          # New problem form
│   └── workflows/
│       ├── new_session.yml          # Creates session from issue
│       ├── add_problem.yml          # Adds problem from issue
│       ├── process_submission.yml   # Parses submissions, queues AF3
│       ├── check_completion.yml     # Monitors SLURM, evaluates, updates leaderboard
│       └── end_competition.yml      # Final evaluation and archival
├── docs/                            # GitHub Pages site
│   ├── index.html                   # Main page
│   ├── submit.html                  # Sequence submission form
│   ├── new-problem.html             # Problem submission form
│   ├── leaderboard.html             # Leaderboard
│   ├── viewer.html                  # Mol* 3D structure viewer
│   ├── targets/
│   │   ├── config.json              # All sessions + problems
│   │   └── *.pdb                    # Reference structures
│   └── results/                     # Per-submission results
└── scripts/
    ├── parse_new_session.py         # Parse new session issues
    ├── parse_new_problem.py         # Parse new problem issues
    ├── parse_issue_submission.py    # Parse sequence submission issues
    ├── process_multi_submission.py  # Prepare AF3 SLURM jobs
    ├── evaluate_structure.py        # TMalign/lDDT evaluation
    └── update_leaderboard.py        # Aggregate rankings
```

## Credits

- [AlphaFold3](https://github.com/google-deepmind/alphafold3) — Structure prediction
- [TMalign/USalign](https://zhanggroup.org/TM-align/) — Structure alignment
- [PDBe-Molstar](https://github.com/molstar/pdbe-molstar) — 3D visualization
- [SeokLab](https://seoklab.org)
