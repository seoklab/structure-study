#!/usr/bin/env python3
"""
Parse GitHub issue body for multi-problem protein sequence submissions.

Parses the structured markdown format produced by the submission form,
validates sequences, and writes submission.json for process_multi_submission.py.

Issue body format:
    ### participant_id
    team1_week2

    ### session
    week2

    ### sequences
    ```json
    {"problem_4": ["ACDEF..."], "problem_5": ["MKLQR..."]}
    ```

    ### submitted_at
    2026-02-10T09:30:00.000Z
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
VALID_AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWY")
MIN_LENGTH = 10
MAX_LENGTH = 5000
MAX_SEQUENCES_PER_PROBLEM = 5


def parse_issue_body(body: str) -> dict:
    """
    Parse ### field / value markdown format from GitHub issue body.

    Returns dict mapping normalized field names to their string values.
    """
    fields = {}
    current_field = None
    current_value = []

    for line in body.split("\n"):
        if line.startswith("### "):
            if current_field is not None:
                fields[current_field] = "\n".join(current_value).strip()
            current_field = line[4:].strip().lower().replace(" ", "_")
            current_value = []
        elif current_field is not None:
            current_value.append(line)

    if current_field is not None:
        fields[current_field] = "\n".join(current_value).strip()

    return fields


def extract_json_from_codeblock(text: str) -> str:
    """Extract JSON content from a markdown code-fenced block."""
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # No code block found - try parsing the raw text as JSON
    return text.strip()


def validate_sequence(seq: str) -> tuple[str, list[str]]:
    """Validate and clean an amino acid sequence. Returns (cleaned, errors)."""
    cleaned = re.sub(r"[^A-Z]", "", seq.upper())
    errors = []

    if not cleaned:
        errors.append("Sequence is empty")
        return cleaned, errors

    invalid_chars = set(cleaned) - VALID_AMINO_ACIDS
    if invalid_chars:
        errors.append(f"Invalid amino acid characters: {', '.join(sorted(invalid_chars))}")

    if len(cleaned) < MIN_LENGTH:
        errors.append(f"Sequence too short ({len(cleaned)} residues, minimum {MIN_LENGTH})")

    if len(cleaned) > MAX_LENGTH:
        errors.append(f"Sequence too long ({len(cleaned)} residues, maximum {MAX_LENGTH})")

    return cleaned, errors


def validate_participant_id(pid: str) -> list[str]:
    """Validate participant ID format."""
    errors = []
    if not pid:
        errors.append("participant_id is required")
        return errors
    if not re.match(r"^[A-Za-z0-9_-]+$", pid):
        errors.append("participant_id contains invalid characters (use letters, numbers, _, -)")
    if len(pid) > 100:
        errors.append("participant_id too long (max 100 characters)")
    return errors


def generate_submission_id(participant_id: str, issue_number: int) -> str:
    """Generate unique submission ID: {sanitized_participant}_{issue}_{timestamp}_{random}."""
    import random
    import string

    sanitized = re.sub(r"[^a-z0-9]", "", participant_id.lower())[:20]
    timestamp = hex(int(datetime.now(timezone.utc).timestamp()))[2:]
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{sanitized}_{issue_number}_{timestamp}_{rand}"


def load_config(config_path: str) -> dict:
    """Load config.json and return it."""
    with open(config_path) as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Parse GitHub issue body for multi-problem sequence submission"
    )
    parser.add_argument("--issue-body", required=True, help="Issue body text")
    parser.add_argument("--issue-number", required=True, type=int, help="Issue number")
    parser.add_argument("--config", default="docs/targets/config.json", help="Config file path")
    parser.add_argument(
        "--submissions-base",
        required=True,
        help="Base directory for submissions",
    )

    args = parser.parse_args()

    # Parse issue body
    fields = parse_issue_body(args.issue_body)
    print(f"Parsed fields: {list(fields.keys())}")

    # Extract fields
    participant_id = fields.get("participant_id", "").strip()
    session = fields.get("session", "").strip()
    sequences_raw = fields.get("sequences", "")
    submitted_at = fields.get("submitted_at", datetime.now(timezone.utc).isoformat())

    # Validate participant_id
    all_errors = validate_participant_id(participant_id)

    # Load config for session/problem validation
    config = load_config(args.config)

    # Validate session
    sessions = config.get("sessions", {})
    if not session:
        all_errors.append("session is required")
    elif session not in sessions:
        all_errors.append(f"Unknown session: {session}")
    elif sessions[session].get("status") not in ("active", "upcoming"):
        # Allow submissions to active or upcoming sessions
        all_errors.append(f"Session '{session}' is not accepting submissions (status: {sessions[session].get('status')})")

    # Parse sequences JSON
    try:
        sequences_json = extract_json_from_codeblock(sequences_raw)
        sequences = json.loads(sequences_json)
    except (json.JSONDecodeError, ValueError) as e:
        all_errors.append(f"Invalid sequences JSON: {e}")
        sequences = {}

    if not isinstance(sequences, dict) or not sequences:
        all_errors.append("No sequences provided")
        sequences = {}

    # Validate problem IDs belong to the session
    session_problem_ids = set()
    if session and session in sessions:
        session_problem_ids = set(sessions[session].get("problems", []))

    validated_sequences = {}
    for problem_id, seq_data in sequences.items():
        # Validate problem ID format
        if not re.match(r"^[A-Za-z0-9_-]+$", problem_id):
            all_errors.append(f"Invalid problem ID: {problem_id}")
            continue

        # Check problem belongs to session
        if session_problem_ids and problem_id not in session_problem_ids:
            all_errors.append(f"Problem '{problem_id}' does not belong to session '{session}'")
            continue

        # Normalize to array
        seq_array = seq_data if isinstance(seq_data, list) else [seq_data]

        if not seq_array:
            all_errors.append(f"{problem_id}: At least one sequence required")
            continue

        if len(seq_array) > MAX_SEQUENCES_PER_PROBLEM:
            all_errors.append(f"{problem_id}: Maximum {MAX_SEQUENCES_PER_PROBLEM} sequences allowed")
            continue

        # Validate each sequence
        validated_seqs = []
        for i, seq in enumerate(seq_array):
            if not isinstance(seq, str):
                all_errors.append(f"{problem_id} seq {i+1}: Sequence must be a string")
                continue
            cleaned, seq_errors = validate_sequence(seq)
            if seq_errors:
                for err in seq_errors:
                    suffix = f" (seq {i+1})" if len(seq_array) > 1 else ""
                    all_errors.append(f"{problem_id}{suffix}: {err}")
            else:
                validated_seqs.append(cleaned)

        if validated_seqs:
            validated_sequences[problem_id] = validated_seqs

    # Report errors
    if all_errors:
        print("Validation errors:", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    if not validated_sequences:
        print("No valid sequences after validation", file=sys.stderr)
        sys.exit(1)

    # Generate submission ID
    submission_id = generate_submission_id(participant_id, args.issue_number)
    print(f"Submission ID: {submission_id}")

    # Create submission directory
    submission_dir = os.path.join(args.submissions_base, submission_id)
    os.makedirs(submission_dir, exist_ok=True)
    os.chmod(submission_dir, 0o775)

    # Write submission.json (same format process_multi_submission.py expects)
    submission_data = {
        "submission_id": submission_id,
        "participant_id": participant_id,
        "session": session,
        "issue_number": args.issue_number,
        "sequences": validated_sequences,
        "submitted_at": submitted_at,
    }

    submission_file = os.path.join(submission_dir, "submission.json")
    with open(submission_file, "w") as f:
        json.dump(submission_data, f, indent=2)
    print(f"Wrote {submission_file}")

    # Output env vars to GITHUB_ENV
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a") as f:
            f.write(f"SUBMISSION_ID={submission_id}\n")
            f.write(f"SUBMISSION_DIR={submission_dir}\n")
            f.write(f"PARTICIPANT_ID={participant_id}\n")
            f.write(f"SESSION={session}\n")
            f.write(f"ISSUE_NUMBER={args.issue_number}\n")

    print(f"Submission parsed successfully: {len(validated_sequences)} problems, "
          f"{sum(len(v) for v in validated_sequences.values())} total sequences")


if __name__ == "__main__":
    main()
