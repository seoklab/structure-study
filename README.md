# Protein Design Competition Platform

A GitHub-hosted platform for protein design competitions using AlphaFold3 structure prediction.

## Overview

Participants submit amino acid sequences via GitHub Issues. Sequences are validated and processed through AlphaFold3 on an HPC cluster, with results returned privately to participants.

## Project Structure

```
protein-competition/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── submit_sequence.yml    # Submission form template
│   │   └── config.yml             # Issue template configuration
│   └── workflows/
│       └── process_submission.yml # Submission processing workflow
├── scripts/
│   ├── parse_submission.py        # Parse and validate submissions
│   └── prepare_af3_input.py       # Generate AF3 input JSON
├── results/                       # AF3 outputs (gitignored)
├── templates/                     # HTML templates for viewer (Phase 3)
└── README.md
```

## Setup Instructions

### 1. Repository Setup

1. Create a new GitHub repository
2. Copy all files from this directory to the repository
3. Enable GitHub Actions in repository settings

### 2. Self-Hosted Runner Configuration

The workflow runs on a self-hosted runner with the `af3-runner` label. To set up:

1. Navigate to repository Settings > Actions > Runners
2. Click "New self-hosted runner"
3. Follow instructions for your HPC environment
4. Add the label `af3-runner` to the runner

### 3. Runner Requirements

The self-hosted runner needs:

- Python 3.11+
- Access to AlphaFold3 installation (for Phase 2)
- Sufficient disk space for results

### 4. Environment Variables (Phase 2)

For Phase 2, configure these secrets in repository settings:

- `AF3_PATH`: Path to AlphaFold3 installation
- `AF3_DATA_DIR`: Path to AF3 model weights

## Submission Process

1. Participants create a new issue using the "Submit Protein Sequence" template
2. They provide:
   - **Participant ID**: Unique identifier
   - **Sequence Name**: Descriptive name for the design
   - **Amino Acid Sequence**: The protein sequence (A-Y single letter codes)
3. GitHub Actions automatically:
   - Validates the sequence
   - Prepares AF3 input JSON
   - (Phase 2) Submits job to HPC via sbatch
   - Comments on the issue with status

## Valid Amino Acids

Sequences must contain only standard amino acid single-letter codes:

| Code | Amino Acid    | Code | Amino Acid    |
|------|---------------|------|---------------|
| A    | Alanine       | M    | Methionine    |
| C    | Cysteine      | N    | Asparagine    |
| D    | Aspartic acid | P    | Proline       |
| E    | Glutamic acid | Q    | Glutamine     |
| F    | Phenylalanine | R    | Arginine      |
| G    | Glycine       | S    | Serine        |
| H    | Histidine     | T    | Threonine     |
| I    | Isoleucine    | V    | Valine        |
| K    | Lysine        | W    | Tryptophan    |
| L    | Leucine       | Y    | Tyrosine      |

## Sequence Constraints

- Minimum length: 10 residues
- Maximum length: 5000 residues
- No non-standard amino acids

## Local Development

### Testing the parser

```bash
# Test with a sample issue body
python scripts/parse_submission.py \
  --issue-body "### Participant ID

participant_001

### Sequence Name

test_protein

### Amino Acid Sequence

MKTLLILAVVAAALA" \
  --issue-number 1 \
  --output-dir results/test
```

### Testing AF3 input generation

```bash
python scripts/prepare_af3_input.py \
  --submission-dir results/test \
  --submission-id submission_1
```

## Roadmap

- [x] **Phase 1**: Core structure and validation
- [ ] **Phase 2**: AlphaFold3 execution via sbatch
- [ ] **Phase 3**: Mol* web viewer with pLDDT coloring
- [ ] **Phase 4**: Results aggregation and leaderboard

## License

[Add your license here]
