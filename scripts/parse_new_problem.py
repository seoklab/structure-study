#!/usr/bin/env python3
"""
Parse GitHub issue body for new competition problem submissions.

Parses the structured markdown format produced by the new-problem issue template,
validates fields, copies the PDB file to docs/targets/, and updates config.json.

Issue body format (GitHub issue form):
    ### Problem Name
    3-Helix Bundle

    ### Problem Type
    monomer

    ### Session
    week2

    ### Description
    Design a sequence for a 3-helix bundle scaffold

    ### Primary Metric
    bb_lddt_cov

    ### MSA Mode
    none

    ### PDB File Path
    /data/galaxy4/user/.../my-scaffold.pdb
"""

import argparse
import json
import os
import re
import shutil
import sys


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


def count_residues_from_pdb(pdb_path: str) -> int:
    """Count residues by counting CA atoms in a PDB file."""
    count = 0
    with open(pdb_path) as f:
        for line in f:
            if (line.startswith("ATOM") or line.startswith("HETATM")) and " CA " in line:
                count += 1
    return count


def pdb_has_atoms(pdb_path: str) -> bool:
    """Check if a PDB file has any ATOM lines."""
    with open(pdb_path) as f:
        for line in f:
            if line.startswith("ATOM"):
                return True
    return False


def get_next_problem_id(problems: list) -> str:
    """Scan existing problem IDs and return the next one (problem_N+1)."""
    max_num = 0
    for p in problems:
        match = re.match(r"problem_(\d+)", p.get("id", ""))
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"problem_{max_num + 1}"


def validate_problem(fields: dict, config: dict) -> list:
    """Validate required fields and return a list of errors."""
    errors = []

    # Required fields
    for field in ["problem_name", "problem_type", "session", "description",
                  "primary_metric", "msa_mode", "pdb_file_path"]:
        val = fields.get(field, "").strip()
        if not val or val == "_No response_":
            errors.append(f"Missing required field: {field}")

    if errors:
        return errors

    # Session must exist
    session = fields["session"].strip()
    sessions = config.get("sessions", {})
    if session not in sessions:
        errors.append(f"Unknown session: '{session}'. Available: {', '.join(sessions.keys())}")

    # Problem type
    ptype = fields["problem_type"].strip()
    if ptype not in ("monomer", "binder"):
        errors.append(f"Invalid problem type: '{ptype}' (must be monomer or binder)")

    # PDB path must exist and be a file
    pdb_path = fields["pdb_file_path"].strip()
    if not os.path.isabs(pdb_path):
        errors.append(f"PDB path must be absolute: '{pdb_path}'")
    elif not os.path.isfile(pdb_path):
        errors.append(f"PDB file not found: '{pdb_path}'")
    else:
        if not pdb_has_atoms(pdb_path):
            errors.append(f"PDB file has no ATOM lines: '{pdb_path}'")
        elif count_residues_from_pdb(pdb_path) == 0:
            errors.append(f"PDB file has no CA atoms: '{pdb_path}'")

    # Binder-specific fields
    if ptype == "binder":
        target_seq = fields.get("target_sequence", "").strip()
        if not target_seq or target_seq == "_No response_":
            errors.append("Binder problems require target_sequence")

        binder_len = fields.get("expected_binder_length", "").strip()
        if not binder_len or binder_len == "_No response_":
            errors.append("Binder problems require expected_binder_length")
        else:
            parts = [x.strip() for x in binder_len.split(",")]
            if len(parts) != 2:
                errors.append(f"expected_binder_length must be two numbers separated by comma, got: '{binder_len}'")
            else:
                try:
                    min_len, max_len = int(parts[0]), int(parts[1])
                    if min_len >= max_len:
                        errors.append(f"expected_binder_length min ({min_len}) must be less than max ({max_len})")
                except ValueError:
                    errors.append(f"expected_binder_length must be integers, got: '{binder_len}'")

    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Parse GitHub issue body for new competition problem"
    )
    parser.add_argument("--issue-body", required=True, help="Issue body text")
    parser.add_argument("--issue-number", required=True, type=int, help="Issue number")
    parser.add_argument("--config", default="docs/targets/config.json", help="Config file path")
    parser.add_argument("--targets-dir", default="docs/targets", help="Targets directory")

    args = parser.parse_args()

    # Parse issue body
    fields = parse_issue_body(args.issue_body)
    print(f"Parsed fields: {list(fields.keys())}")

    # Load config
    with open(args.config) as f:
        config = json.load(f)

    # Validate
    errors = validate_problem(fields, config)
    if errors:
        print("Validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    # Extract validated fields
    problem_name = fields["problem_name"].strip()
    problem_type = fields["problem_type"].strip()
    session = fields["session"].strip()
    description = fields["description"].strip()
    primary_metric = fields["primary_metric"].strip()
    msa_mode = fields["msa_mode"].strip()
    pdb_src_path = fields["pdb_file_path"].strip()
    pdb_filename = os.path.basename(pdb_src_path)

    # Generate problem ID
    problem_id = get_next_problem_id(config.get("problems", []))
    display_name = f"{problem_id.replace('_', ' ').title()} - {problem_name}"
    print(f"New problem: {problem_id} ({display_name})")

    # Copy PDB file to targets dir
    pdb_dest = os.path.join(args.targets_dir, pdb_filename)
    shutil.copy2(pdb_src_path, pdb_dest)
    residue_count = count_residues_from_pdb(pdb_dest)
    print(f"Copied PDB: {pdb_src_path} -> {pdb_dest} ({residue_count} residues)")

    # Build problem entry
    problem_entry = {
        "id": problem_id,
        "name": display_name,
        "description": description,
        "target_file": pdb_filename,
        "residue_count": residue_count,
        "type": problem_type,
        "primary_metric": primary_metric,
        "msa_mode": msa_mode,
        "session": session,
    }

    # Binder-specific fields
    if problem_type == "binder":
        problem_entry["target_sequence"] = fields["target_sequence"].strip()
        problem_entry["participant_msa_mode"] = "none"

        binder_len = fields["expected_binder_length"].strip()
        parts = [x.strip() for x in binder_len.split(",")]
        problem_entry["expected_binder_length"] = [int(parts[0]), int(parts[1])]

        msa_path = fields.get("target_msa_path", "").strip()
        if msa_path and msa_path != "_No response_":
            problem_entry["target_msa_file"] = msa_path

    # Update config.json
    config["problems"].append(problem_entry)

    # Add to session's problems list
    if session in config.get("sessions", {}):
        session_problems = config["sessions"][session].get("problems", [])
        if problem_id not in session_problems:
            session_problems.append(problem_id)
            config["sessions"][session]["problems"] = session_problems

    with open(args.config, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    print(f"Updated config: {args.config}")

    # Output env vars
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a") as f:
            f.write(f"PROBLEM_ID={problem_id}\n")
            f.write(f"PROBLEM_NAME={display_name}\n")
            f.write(f"SESSION={session}\n")
            f.write(f"PDB_FILENAME={pdb_filename}\n")
            f.write(f"RESIDUE_COUNT={residue_count}\n")
            f.write(f"ISSUE_NUMBER={args.issue_number}\n")

    print(f"Done: {problem_id} added to session '{session}'")


if __name__ == "__main__":
    main()
