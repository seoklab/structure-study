#!/usr/bin/env python3
"""
Process multi-problem submission data.

This script reads submission data containing multiple sequences (one per problem)
and creates the directory structure and AF3 input files for each problem.

Supports:
- Monomer problems: Single chain structure prediction
- Binder problems: Two chains (participant binder + given target)
- MSA modes: none, search, or precomputed
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Default model seeds for reproducibility
DEFAULT_MODEL_SEEDS = [1, 2, 3, 4, 5]

# Path to problem config
CONFIG_PATH = Path(__file__).parent.parent / "docs" / "targets" / "config.json"


def load_problem_config() -> dict:
    """Load problem configuration from config.json."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"problems": [], "msa_modes": {}}


def get_problem_settings(config: dict, problem_id: str) -> dict:
    """Get settings for a specific problem from config."""
    for problem in config.get("problems", []):
        if problem.get("id") == problem_id:
            return problem
    return {}


def create_af3_input_monomer(
    job_name: str,
    sequence: str,
    msa_mode: str = "none",
    msa_file: str | None = None,
    model_seeds: list[int] | None = None,
) -> dict:
    """
    Create AlphaFold3-compatible input JSON for monomer prediction.

    Args:
        job_name: Unique identifier for this job
        sequence: Amino acid sequence string
        msa_mode: "none", "search", or "precomputed"
        msa_file: Path to pre-computed MSA file (for msa_mode="precomputed")
        model_seeds: List of random seeds for model runs

    Returns:
        dict: AF3 input JSON structure
    """
    if model_seeds is None:
        model_seeds = DEFAULT_MODEL_SEEDS

    protein_entry = {
        "id": "A",
        "sequence": sequence,
    }

    # Apply MSA mode
    if msa_mode == "none":
        protein_entry["unpairedMsaPath"] = ""
    elif msa_mode == "precomputed" and msa_file:
        protein_entry["unpairedMsaPath"] = msa_file

    # If msa_mode == "search", don't add unpairedMsaPath field (AF3 default behavior)

    return {
        "name": job_name,
        "modelSeeds": model_seeds,
        "sequences": [{"protein": protein_entry}],
        "dialect": "alphafold3",
        "version": 1,
    }


def create_af3_input_binder(
    job_name: str,
    binder_sequence: str,
    target_sequence: str,
    binder_msa_mode: str = "none",
    target_msa_mode: str = "precomputed",
    target_msa_file: str | None = None,
    model_seeds: list[int] | None = None,
) -> dict:
    """
    Create AlphaFold3-compatible input JSON for binder design.

    Args:
        job_name: Unique identifier for this job
        binder_sequence: Participant's binder sequence (chain A)
        target_sequence: Given target sequence (chain B)
        binder_msa_mode: MSA mode for binder ("none" typically)
        target_msa_mode: MSA mode for target ("precomputed" typically)
        target_msa_file: Path to pre-computed MSA for target
        model_seeds: List of random seeds for model runs

    Returns:
        dict: AF3 input JSON structure
    """
    if model_seeds is None:
        model_seeds = DEFAULT_MODEL_SEEDS

    # Chain A: Participant's binder (typically no MSA for designed sequences)
    binder_entry = {
        "id": "A",
        "sequence": binder_sequence,
    }
    if binder_msa_mode == "none":
        binder_entry["unpairedMsaPath"] = ""

    # Chain B: Given target (typically with pre-computed MSA)
    target_entry = {
        "id": "B",
        "sequence": target_sequence,
    }
    if target_msa_mode == "none":
        target_entry["unpairedMsaPath"] = ""
    elif target_msa_mode == "precomputed" and target_msa_file:
        target_entry["unpairedMsaPath"] = target_msa_file

    return {
        "name": job_name,
        "modelSeeds": model_seeds,
        "sequences": [
            {"protein": binder_entry},
            {"protein": target_entry},
        ],
        "dialect": "alphafold3",
        "version": 1,
    }


# Backward-compatible alias
def create_af3_input(job_name: str, sequence: str, model_seeds: list[int] | None = None) -> dict:
    """Backward-compatible function - creates monomer input with no MSA."""
    return create_af3_input_monomer(job_name, sequence, msa_mode="none", model_seeds=model_seeds)


def main():
    parser = argparse.ArgumentParser(
        description="Process multi-problem submission and create AF3 inputs"
    )
    parser.add_argument(
        "--submission-dir",
        required=True,
        type=Path,
        help="Directory containing submission.json",
    )
    parser.add_argument(
        "--submission-id",
        required=True,
        help="Unique submission identifier",
    )

    args = parser.parse_args()

    logger.info(f"Processing multi-problem submission: {args.submission_id}")

    # Load problem configuration
    config = load_problem_config()
    logger.info(f"Loaded config with {len(config.get('problems', []))} problem definitions")

    # Read submission data
    submission_file = args.submission_dir / "submission.json"
    if not submission_file.exists():
        logger.error(f"Submission file not found: {submission_file}")
        sys.exit(1)

    with open(submission_file) as f:
        submission_data = json.load(f)

    participant_id = submission_data.get("participant_id", "unknown")
    email = submission_data.get("email", "")
    sequences = submission_data.get("sequences", {})

    if not sequences:
        logger.error("No sequences found in submission")
        sys.exit(1)

    logger.info(f"Participant: {participant_id}")
    logger.info(f"Number of problems: {len(sequences)}")

    # Process each problem
    for problem_id, sequence in sequences.items():
        logger.info(f"Processing {problem_id}: {len(sequence)} residues")

        # Get problem-specific settings from config
        problem_settings = get_problem_settings(config, problem_id)
        problem_type = problem_settings.get("type", "monomer")
        msa_mode = problem_settings.get("msa_mode", "none")
        msa_file = problem_settings.get("msa_file")

        logger.info(f"  Type: {problem_type}, MSA mode: {msa_mode}")

        # Create problem directory with group write permissions for j2ho SLURM jobs
        problem_dir = args.submission_dir / problem_id
        problem_dir.mkdir(parents=True, exist_ok=True)
        problem_dir.chmod(0o775)
        (problem_dir / "scripts").mkdir(exist_ok=True)
        (problem_dir / "scripts").chmod(0o775)
        (problem_dir / "logs").mkdir(exist_ok=True)
        (problem_dir / "logs").chmod(0o775)

        # Create job name: participant_problem
        job_name = f"{participant_id}_{problem_id}"

        # Create AF3 input JSON based on problem type
        if problem_type == "binder":
            # Binder design: participant sequence + given target
            target_sequence = problem_settings.get("target_sequence", "")
            target_msa_file = problem_settings.get("target_msa_file")
            participant_msa_mode = problem_settings.get("participant_msa_mode", "none")

            if not target_sequence:
                logger.error(f"  Binder problem {problem_id} missing target_sequence in config!")
                continue

            af3_input = create_af3_input_binder(
                job_name=job_name,
                binder_sequence=sequence,
                target_sequence=target_sequence,
                binder_msa_mode=participant_msa_mode,
                target_msa_mode="precomputed" if target_msa_file else "none",
                target_msa_file=target_msa_file,
            )
            logger.info(f"  Created binder input: {len(sequence)} (binder) + {len(target_sequence)} (target) residues")
        else:
            # Monomer prediction
            af3_input = create_af3_input_monomer(
                job_name=job_name,
                sequence=sequence,
                msa_mode=msa_mode,
                msa_file=msa_file,
            )

        af3_input_file = problem_dir / "af3_input.json"
        with open(af3_input_file, "w") as f:
            json.dump(af3_input, f, indent=2)
        logger.info(f"  Created: {af3_input_file}")

        # Create problem-specific submission info
        problem_submission = {
            "submission_id": args.submission_id,
            "participant_id": participant_id,
            "email": email,
            "problem_id": problem_id,
            "sequence": sequence,
            "sequence_length": len(sequence),
            "problem_type": problem_type,
            "msa_mode": msa_mode,
        }

        # Add binder-specific info
        if problem_type == "binder":
            problem_submission["target_sequence"] = problem_settings.get("target_sequence", "")
            problem_submission["target_length"] = len(problem_settings.get("target_sequence", ""))

        problem_submission_file = problem_dir / "submission.json"
        with open(problem_submission_file, "w") as f:
            json.dump(problem_submission, f, indent=2)

        # Create FASTA file
        fasta_file = problem_dir / "sequence.fasta"
        with open(fasta_file, "w") as f:
            f.write(f">{job_name}\n")
            for i in range(0, len(sequence), 80):
                f.write(sequence[i : i + 80] + "\n")

            # Add target sequence for binder problems
            if problem_type == "binder":
                target_seq = problem_settings.get("target_sequence", "")
                f.write(f">{job_name}_target\n")
                for i in range(0, len(target_seq), 80):
                    f.write(target_seq[i : i + 80] + "\n")

        logger.info(f"  Created: {fasta_file}")

        # Create problem status file
        status_file = problem_dir / "status.json"
        with open(status_file, "w") as f:
            json.dump({"status": "pending", "problem_id": problem_id, "type": problem_type}, f, indent=2)

    logger.info(f"Successfully processed {len(sequences)} problems")


if __name__ == "__main__":
    main()
