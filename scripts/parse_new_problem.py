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

Supports three PDB input methods:
  1. Server path  — copies from absolute path on the server
  2. File upload   — downloads from GitHub attachment URL (drag-and-drop)
  3. Paste content — writes pasted PDB text with a given filename
"""

import argparse
import json
import os
import re
import shutil
import sys
import urllib.request


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


def is_empty_field(val: str) -> bool:
    """Check if an issue form field is empty or the default no-response."""
    return not val or val.strip() == "" or val.strip() == "_No response_"


def extract_attachment_url(text: str) -> str | None:
    """Extract a GitHub attachment URL from an issue form upload field.

    GitHub renders drag-and-drop uploads as markdown links like:
      [filename.pdb](https://github.com/user-attachments/assets/...)
    or plain URLs.
    """
    # Markdown link: [name](url)
    m = re.search(r'\[.*?\]\((https://github\.com/user-attachments/assets/[^\)]+)\)', text)
    if m:
        return m.group(1)
    # Plain URL
    m = re.search(r'(https://github\.com/user-attachments/assets/\S+)', text)
    if m:
        return m.group(1)
    return None


def extract_filename_from_upload(text: str) -> str | None:
    """Extract the original filename from a GitHub upload markdown link."""
    m = re.search(r'\[([^\]]+\.pdb)\]', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def download_file(url: str, dest: str) -> None:
    """Download a file from a URL."""
    urllib.request.urlretrieve(url, dest)


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


def sanitize_pdb(pdb_path: str) -> None:
    """Sanitize a PDB file: mask residues to ALA, keep only backbone atoms, strip headers.

    Overwrites the file in-place. Removes all identifying records (HEADER, TITLE,
    SEQRES, HELIX, REMARK, DBREF, JRNL, etc.) and keeps only CRYST1, ORIGX, SCALE,
    ATOM (backbone N/CA/C/O only), TER, and END.
    """
    keep_prefixes = ("CRYST1", "ORIGX", "SCALE")
    backbone_atoms = {"N", "CA", "C", "O"}

    with open(pdb_path) as f:
        lines = f.readlines()

    out = []
    atom_serial = 1

    for line in lines:
        rec = line[:6].strip()

        if rec in ("ATOM", "HETATM"):
            atom_name = line[12:16].strip()
            if atom_name not in backbone_atoms:
                continue
            # Renumber atom serial and mask residue name to ALA
            new_line = f"ATOM  {atom_serial:>5}{line[11:17]}ALA{line[20:]}"
            out.append(new_line)
            atom_serial += 1
        elif rec == "TER":
            ter_line = f"TER   {atom_serial:>5}      ALA{line[20:]}"
            out.append(ter_line)
            atom_serial += 1
        elif rec == "END":
            out.append(line)
        elif any(line.startswith(p) for p in keep_prefixes):
            out.append(line)
        # All other records (HEADER, TITLE, SEQRES, HELIX, REMARK, etc.) are dropped

    with open(pdb_path, "w") as f:
        f.writelines(out)

    print(f"Sanitized PDB: masked to ALA, backbone only, headers stripped ({atom_serial - 1} atoms)")


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
                  "primary_metric", "msa_mode"]:
        if is_empty_field(fields.get(field, "")):
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

    # PDB input: exactly one method must be provided
    has_server_path = not is_empty_field(fields.get("method_1:_server_path", ""))
    has_upload = not is_empty_field(fields.get("method_2:_file_upload", ""))
    has_paste = not is_empty_field(fields.get("method_3:_pasted_pdb_content", ""))

    method_count = sum([has_server_path, has_upload, has_paste])
    if method_count == 0:
        errors.append("No PDB provided. Use one of: server path, file upload, or paste content")
    elif method_count > 1:
        errors.append("Multiple PDB methods provided. Use only one of: server path, file upload, or paste content")

    # Validate server path if provided
    if has_server_path:
        pdb_path = fields["method_1:_server_path"].strip()
        if not os.path.isabs(pdb_path):
            errors.append(f"PDB server path must be absolute: '{pdb_path}'")
        elif not os.path.isfile(pdb_path):
            errors.append(f"PDB file not found: '{pdb_path}'")
        else:
            if not pdb_has_atoms(pdb_path):
                errors.append(f"PDB file has no ATOM lines: '{pdb_path}'")
            elif count_residues_from_pdb(pdb_path) == 0:
                errors.append(f"PDB file has no CA atoms: '{pdb_path}'")

    # Validate upload field if provided
    if has_upload:
        upload_text = fields["method_2:_file_upload"].strip()
        url = extract_attachment_url(upload_text)
        if not url:
            errors.append("File upload field does not contain a valid GitHub attachment URL")

    # Validate paste: need both filename and content
    if has_paste:
        pdb_content = fields["method_3:_pasted_pdb_content"].strip()
        pdb_filename = fields.get("method_3:_filename", "").strip()
        if is_empty_field(pdb_filename):
            errors.append("PDB filename is required when pasting content")
        elif not pdb_filename.endswith(".pdb"):
            errors.append(f"PDB filename must end with .pdb: '{pdb_filename}'")
        if not any(line.startswith("ATOM") for line in pdb_content.split("\n")):
            errors.append("Pasted PDB content has no ATOM lines")

    # Validate filename safety (for all methods that produce a filename)
    pdb_filename = None
    if has_server_path:
        pdb_filename = os.path.basename(fields["method_1:_server_path"].strip())
    elif has_upload:
        pdb_filename = extract_filename_from_upload(fields["method_2:_file_upload"].strip())
    elif has_paste:
        pdb_filename = fields.get("method_3:_filename", "").strip()

    if pdb_filename and not re.match(r'^[\w\-\.]+\.pdb$', pdb_filename, re.IGNORECASE):
        errors.append(f"Unsafe PDB filename: '{pdb_filename}' (use letters, numbers, hyphens, underscores)")

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

    # Backward compat: old template used "pdb_file_path" as a single server path field
    if "pdb_file_path" in fields and "method_1:_server_path" not in fields:
        fields["method_1:_server_path"] = fields.pop("pdb_file_path")

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

    # Validate: precomputed requires an msa_file; fall back to none for monomer
    if msa_mode == "precomputed" and problem_type == "monomer":
        print("WARNING: msa_mode 'precomputed' set for monomer without msa_file field. Falling back to 'none'.")
        msa_mode = "none"

    # Determine PDB method and write file
    has_server_path = not is_empty_field(fields.get("method_1:_server_path", ""))
    has_upload = not is_empty_field(fields.get("method_2:_file_upload", ""))
    has_paste = not is_empty_field(fields.get("method_3:_pasted_pdb_content", ""))

    pdb_filename = ""
    pdb_dest = ""

    if has_server_path:
        pdb_src_path = fields["method_1:_server_path"].strip()
        pdb_filename = os.path.basename(pdb_src_path)
        pdb_dest = os.path.join(args.targets_dir, pdb_filename)
        shutil.copy2(pdb_src_path, pdb_dest)
        print(f"Copied PDB from server: {pdb_src_path} -> {pdb_dest}")
    elif has_upload:
        upload_text = fields["method_2:_file_upload"].strip()
        url = extract_attachment_url(upload_text)
        assert url is not None, "No attachment URL found (should have been caught by validation)"
        pdb_filename = extract_filename_from_upload(upload_text) or "uploaded.pdb"
        pdb_dest = os.path.join(args.targets_dir, pdb_filename)
        download_file(url, pdb_dest)
        print(f"Downloaded PDB from upload: {url} -> {pdb_dest}")
    elif has_paste:
        pdb_filename = fields["method_3:_filename"].strip()
        pdb_content = fields["method_3:_pasted_pdb_content"].strip()
        pdb_dest = os.path.join(args.targets_dir, pdb_filename)
        with open(pdb_dest, "w") as f:
            f.write(pdb_content)
            f.write("\n")
        print(f"Wrote pasted PDB content to: {pdb_dest}")

    # Count residues before sanitizing (CA atoms are preserved either way)
    residue_count = count_residues_from_pdb(pdb_dest)
    print(f"PDB: {pdb_filename} ({residue_count} residues)")

    # Sanitize: mask to ALA, backbone only, strip headers
    sanitize_pdb(pdb_dest)

    # Generate problem ID and rename file to generic name
    problem_id = get_next_problem_id(config.get("problems", []))
    generic_filename = f"{problem_id}.pdb"
    generic_dest = os.path.join(args.targets_dir, generic_filename)
    os.rename(pdb_dest, generic_dest)
    pdb_filename = generic_filename
    pdb_dest = generic_dest
    print(f"Renamed to generic filename: {pdb_filename}")

    display_name = f"{problem_id.replace('_', ' ').title()} - {problem_name}"
    print(f"New problem: {problem_id} ({display_name})")

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
