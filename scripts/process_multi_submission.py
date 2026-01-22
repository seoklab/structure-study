#!/usr/bin/env python3
"""
Process multi-problem submission data.

This script reads submission data containing multiple sequences (one per problem)
and creates the directory structure and AF3 input files for each problem.
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


def create_af3_input(job_name: str, sequence: str, model_seeds: list[int] | None = None) -> dict:
    """
    Create AlphaFold3-compatible input JSON structure.

    Args:
        job_name: Unique identifier for this job
        sequence: Amino acid sequence string
        model_seeds: List of random seeds for model runs

    Returns:
        dict: AF3 input JSON structure
    """
    if model_seeds is None:
        model_seeds = DEFAULT_MODEL_SEEDS

    return {
        "name": job_name,
        "modelSeeds": model_seeds,
        "sequences": [
            {
                "protein": {
                    "id": "A",
                    "sequence": sequence,
                }
            }
        ],
        "dialect": "alphafold3",
        "version": 1,
    }


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

        # Create AF3 input JSON
        af3_input = create_af3_input(job_name, sequence)
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
        }
        problem_submission_file = problem_dir / "submission.json"
        with open(problem_submission_file, "w") as f:
            json.dump(problem_submission, f, indent=2)

        # Create FASTA file
        fasta_file = problem_dir / "sequence.fasta"
        with open(fasta_file, "w") as f:
            f.write(f">{job_name}\n")
            for i in range(0, len(sequence), 80):
                f.write(sequence[i : i + 80] + "\n")
        logger.info(f"  Created: {fasta_file}")

        # Create problem status file
        status_file = problem_dir / "status.json"
        with open(status_file, "w") as f:
            json.dump({"status": "pending", "problem_id": problem_id}, f, indent=2)

    logger.info(f"Successfully processed {len(sequences)} problems")


if __name__ == "__main__":
    main()
