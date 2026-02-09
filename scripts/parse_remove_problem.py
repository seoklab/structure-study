#!/usr/bin/env python3
"""
Parse GitHub issue body for problem removal.

Removes a problem ID from a session's problems list in config.json.
The problem entry and PDB file are preserved.
"""

import argparse
import json
import os
import sys


def parse_issue_body(body: str) -> dict:
    """Parse ### field / value markdown format from GitHub issue body."""
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


def main():
    parser = argparse.ArgumentParser(
        description="Parse GitHub issue body for problem removal"
    )
    parser.add_argument("--issue-body", required=True, help="Issue body text")
    parser.add_argument("--issue-number", required=True, type=int, help="Issue number")
    parser.add_argument("--config", default="docs/targets/config.json", help="Config file path")

    args = parser.parse_args()

    # Parse issue body
    fields = parse_issue_body(args.issue_body)
    print(f"Parsed fields: {list(fields.keys())}")

    # Extract fields
    problem_id = fields.get("problem_id", "").strip()
    session_key = fields.get("session_key", "").strip()

    # Validate inputs
    errors = []
    if not problem_id or problem_id == "_No response_":
        errors.append("Missing required field: problem_id")

    if not session_key or session_key == "_No response_":
        errors.append("Missing required field: session")

    if errors:
        print("Validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    # Load config
    with open(args.config) as f:
        config = json.load(f)

    sessions = config.get("sessions", {})

    # Validate session exists
    if session_key not in sessions:
        print(f"Session '{session_key}' not found in config", file=sys.stderr)
        sys.exit(1)

    session = sessions[session_key]
    problems_list = session.get("problems", [])

    # Validate problem is in the session
    if problem_id not in problems_list:
        print(
            f"Problem '{problem_id}' not found in session '{session_key}' "
            f"(current problems: {problems_list})",
            file=sys.stderr,
        )
        sys.exit(1)

    # Remove the problem from the session's problems list
    problems_list.remove(problem_id)
    session["problems"] = problems_list

    # Write config
    with open(args.config, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    print(f"Updated config: {args.config}")

    # Output env vars
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a") as f:
            f.write(f"PROBLEM_ID={problem_id}\n")
            f.write(f"SESSION_KEY={session_key}\n")

    print(f"Done: removed '{problem_id}' from session '{session_key}'")


if __name__ == "__main__":
    main()
