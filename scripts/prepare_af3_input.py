#!/usr/bin/env python3
"""
Prepare AlphaFold3 input JSON from parsed submission data.

This script reads the validated submission data and generates the
AF3-compatible input JSON file for structure prediction.
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


def create_af3_input(
    submission_id: str,
    sequence: str,
    model_seeds: list[int] | None = None,
) -> dict:
    """
    Create AlphaFold3-compatible input JSON structure.

    Args:
        submission_id: Unique identifier for this submission
        sequence: Amino acid sequence string
        model_seeds: List of random seeds for model runs

    Returns:
        dict: AF3 input JSON structure
    """
    if model_seeds is None:
        model_seeds = DEFAULT_MODEL_SEEDS

    af3_input = {
        "name": submission_id,
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

    return af3_input


def main():
    parser = argparse.ArgumentParser(
        description="Generate AlphaFold3 input JSON from submission data"
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
    parser.add_argument(
        "--model-seeds",
        type=int,
        nargs="+",
        default=DEFAULT_MODEL_SEEDS,
        help="Random seeds for AF3 model runs (default: 1 2 3 4 5)",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=None,
        help="Output file path (default: submission_dir/af3_input.json)",
    )

    args = parser.parse_args()

    logger.info(f"Preparing AF3 input for {args.submission_id}")

    # Read submission data
    submission_file = args.submission_dir / "submission.json"
    if not submission_file.exists():
        logger.error(f"Submission file not found: {submission_file}")
        sys.exit(1)

    with open(submission_file) as f:
        submission_data = json.load(f)

    logger.info(
        f"Loaded submission: {submission_data['participant_id']} / "
        f"{submission_data['sequence_name']} "
        f"({submission_data['sequence_length']} residues)"
    )

    # Create AF3 input structure
    af3_input = create_af3_input(
        submission_id=args.submission_id,
        sequence=submission_data["sequence"],
        model_seeds=args.model_seeds,
    )

    # Determine output file path
    output_file = args.output_file or (args.submission_dir / "af3_input.json")

    # Ensure parent directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Write AF3 input JSON
    with open(output_file, "w") as f:
        json.dump(af3_input, f, indent=2)

    logger.info(f"AF3 input saved to {output_file}")

    # Log summary
    logger.info("AF3 Input Summary:")
    logger.info(f"  Name: {af3_input['name']}")
    logger.info(f"  Sequence length: {len(af3_input['sequences'][0]['protein']['sequence'])}")
    logger.info(f"  Model seeds: {af3_input['modelSeeds']}")


if __name__ == "__main__":
    main()
