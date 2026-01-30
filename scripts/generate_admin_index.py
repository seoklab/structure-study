#!/usr/bin/env python3
"""
Generate index.json for the admin page.

Scans docs/results/*/ directories and creates a JSON index of all submissions
with their status, problems, and metadata.

Usage:
    python scripts/generate_admin_index.py
"""

import json
import os
import sys
from pathlib import Path


def scan_results(results_dir: str = "docs/results") -> list[dict]:
    """Scan result directories and extract submission info."""
    results_path = Path(results_dir)
    submissions = []

    if not results_path.exists():
        print(f"Results directory not found: {results_dir}", file=sys.stderr)
        return []

    for token_dir in results_path.iterdir():
        if not token_dir.is_dir() or token_dir.name.startswith('.'):
            continue

        token = token_dir.name

        # Load submission info
        submission_file = token_dir / "submission.json"
        status_file = token_dir / "status.json"
        metadata_file = token_dir / "metadata.json"

        if not submission_file.exists():
            continue

        try:
            with open(submission_file) as f:
                submission = json.load(f)

            status_data = {}
            if status_file.exists():
                with open(status_file) as f:
                    status_data = json.load(f)

            metadata = {}
            if metadata_file.exists():
                with open(metadata_file) as f:
                    metadata = json.load(f)

            # Extract problem info
            problems = []
            for problem_id, problem_data in metadata.get("problems", {}).items():
                problems.append({
                    "problem_id": problem_id,
                    "status": problem_data.get("status", "unknown"),
                    "sequences": list(problem_data.get("sequences", {}).keys())
                })

            submissions.append({
                "token": token,
                "participant_id": submission.get("participant_id", "unknown"),
                "email": submission.get("email", ""),
                "submitted_at": submission.get("submitted_at", ""),
                "status": status_data.get("status", "unknown"),
                "problems": sorted(problems, key=lambda p: p["problem_id"])
            })

        except Exception as e:
            print(f"Warning: Error processing {token}: {e}", file=sys.stderr)
            continue

    return submissions


def main():
    results_dir = "docs/results"
    output_file = "docs/results/index.json"

    submissions = scan_results(results_dir)

    # Sort by submitted_at descending
    submissions.sort(key=lambda s: s.get("submitted_at", ""), reverse=True)

    # Write index
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(submissions, f, indent=2)

    print(f"Generated {output_file} with {len(submissions)} submissions")

    # Print summary
    for sub in submissions[:10]:
        print(f"  {sub['participant_id']}: {sub['status']} ({len(sub['problems'])} problems)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
