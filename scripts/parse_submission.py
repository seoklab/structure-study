#!/usr/bin/env python3
"""
Parse GitHub issue body and extract protein sequence submission data.

This script parses the structured issue body from GitHub's YAML form template,
validates the amino acid sequence, and saves the parsed data for AF3 processing.
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

# Valid single-letter amino acid codes
VALID_AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWY")

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def parse_issue_body(body: str) -> dict:
    """
    Parse the GitHub issue body from YAML form template.

    The issue body format from GitHub forms looks like:
    ### Field Label

    value

    ### Another Field

    another value
    """
    fields = {}
    current_field = None
    current_value = []

    for line in body.split("\n"):
        # Check for field header (### Field Name)
        if line.startswith("### "):
            # Save previous field if exists
            if current_field is not None:
                fields[current_field] = "\n".join(current_value).strip()

            # Extract field name and normalize it
            field_name = line[4:].strip()
            current_field = normalize_field_name(field_name)
            current_value = []
        elif current_field is not None:
            current_value.append(line)

    # Save last field
    if current_field is not None:
        fields[current_field] = "\n".join(current_value).strip()

    return fields


def normalize_field_name(name: str) -> str:
    """Convert field label to snake_case identifier."""
    # Remove special characters, convert to lowercase, replace spaces with underscore
    normalized = re.sub(r"[^\w\s]", "", name.lower())
    normalized = re.sub(r"\s+", "_", normalized.strip())
    return normalized


def validate_amino_acid_sequence(sequence: str) -> tuple[str, list[str]]:
    """
    Validate and clean an amino acid sequence.

    Returns:
        tuple: (cleaned_sequence, list_of_errors)
    """
    errors = []

    # Remove whitespace and convert to uppercase
    cleaned = "".join(sequence.split()).upper()

    if not cleaned:
        errors.append("Sequence is empty")
        return cleaned, errors

    # Check for invalid characters
    invalid_chars = set(cleaned) - VALID_AMINO_ACIDS
    if invalid_chars:
        errors.append(
            f"Invalid amino acid characters found: {', '.join(sorted(invalid_chars))}"
        )

    # Check minimum length (reasonable minimum for a protein)
    if len(cleaned) < 10:
        errors.append(f"Sequence too short ({len(cleaned)} residues). Minimum is 10.")

    # Check maximum length (AF3 has limits)
    if len(cleaned) > 5000:
        errors.append(
            f"Sequence too long ({len(cleaned)} residues). Maximum is 5000."
        )

    return cleaned, errors


def validate_identifier(value: str, field_name: str) -> list[str]:
    """Validate an identifier field (participant_id, sequence_name)."""
    errors = []

    if not value:
        errors.append(f"{field_name} is required")
        return errors

    # Check for valid characters (alphanumeric, underscore, hyphen)
    if not re.match(r"^[\w\-]+$", value):
        errors.append(
            f"{field_name} contains invalid characters. "
            "Use only letters, numbers, underscores, and hyphens."
        )

    # Check length
    if len(value) > 100:
        errors.append(f"{field_name} is too long. Maximum is 100 characters.")

    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Parse GitHub issue body and extract sequence submission data"
    )
    parser.add_argument(
        "--issue-body",
        required=True,
        help="The body text of the GitHub issue",
    )
    parser.add_argument(
        "--issue-number",
        required=True,
        type=int,
        help="The GitHub issue number",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory to save parsed submission data",
    )

    args = parser.parse_args()

    logger.info(f"Processing submission from issue #{args.issue_number}")

    # Parse the issue body
    fields = parse_issue_body(args.issue_body)
    logger.info(f"Parsed fields: {list(fields.keys())}")

    # Extract required fields
    participant_id = fields.get("participant_id", "").strip()
    sequence_name = fields.get("sequence_name", "").strip()
    amino_acid_sequence = fields.get("amino_acid_sequence", "")

    # Collect all validation errors
    all_errors = []

    # Validate identifiers
    all_errors.extend(validate_identifier(participant_id, "participant_id"))
    all_errors.extend(validate_identifier(sequence_name, "sequence_name"))

    # Validate and clean sequence
    cleaned_sequence, seq_errors = validate_amino_acid_sequence(amino_acid_sequence)
    all_errors.extend(seq_errors)

    # Report errors and exit if validation failed
    if all_errors:
        for error in all_errors:
            logger.error(f"Validation error: {error}")
        sys.exit(1)

    logger.info(f"Sequence validated: {len(cleaned_sequence)} residues")

    # Prepare output data
    submission_data = {
        "issue_number": args.issue_number,
        "participant_id": participant_id,
        "sequence_name": sequence_name,
        "sequence": cleaned_sequence,
        "sequence_length": len(cleaned_sequence),
    }

    # Ensure output directory exists
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Save parsed data
    output_file = args.output_dir / "submission.json"
    with open(output_file, "w") as f:
        json.dump(submission_data, f, indent=2)

    logger.info(f"Submission data saved to {output_file}")

    # Also save raw sequence to a FASTA file for reference
    fasta_file = args.output_dir / "sequence.fasta"
    with open(fasta_file, "w") as f:
        f.write(f">{participant_id}_{sequence_name}\n")
        # Write sequence in 80-character lines
        for i in range(0, len(cleaned_sequence), 80):
            f.write(cleaned_sequence[i : i + 80] + "\n")

    logger.info(f"FASTA file saved to {fasta_file}")


if __name__ == "__main__":
    main()
