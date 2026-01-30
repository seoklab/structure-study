#!/usr/bin/env python3
"""
Package AF3 results with a secret token for private access.

This script handles multi-problem submissions:
1. Finds AF3 output files in each problem subdirectory
2. Generates a unique secret token for the entire submission
3. Copies relevant files to public_results/<token>/
4. Renames files to include problem ID for clarity
5. Updates status.json with the token
"""

import argparse
import json
import secrets
import shutil
import sys
from pathlib import Path


def generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(24)


def find_af3_outputs(seq_dir: Path) -> dict:
    """Find AF3 output files in a sequence directory."""
    outputs = {}

    # Look for main output files
    for f in seq_dir.glob("*_model.cif"):
        outputs["model_cif"] = f
        break

    for f in seq_dir.glob("*_confidences.json"):
        outputs["confidences"] = f
        break

    for f in seq_dir.glob("*_summary_confidences.json"):
        outputs["summary"] = f
        break

    for f in seq_dir.glob("*_ranking_scores.csv"):
        outputs["ranking"] = f
        break

    # Also check one level deeper (AF3 sometimes nests outputs)
    if "model_cif" not in outputs:
        for f in seq_dir.glob("*/*_model.cif"):
            outputs["model_cif"] = f
            # Also get other files from same dir
            parent = f.parent
            for conf in parent.glob("*_confidences.json"):
                outputs["confidences"] = conf
                break
            for summ in parent.glob("*_summary_confidences.json"):
                outputs["summary"] = summ
                break
            for rank in parent.glob("*_ranking_scores.csv"):
                outputs["ranking"] = rank
                break
            break

    return outputs


def find_all_sequence_outputs(problem_dir: Path) -> dict:
    """
    Find AF3 output files for all sequences in a problem directory.

    Returns dict: {seq_num: {file_type: path}}
    """
    all_outputs = {}

    # Check for seq_N subdirectories (multi-sequence format)
    seq_dirs = sorted(problem_dir.glob("seq_*"))
    if seq_dirs:
        for seq_dir in seq_dirs:
            if not seq_dir.is_dir():
                continue
            seq_num = seq_dir.name.replace("seq_", "")
            outputs = find_af3_outputs(seq_dir)
            if outputs:
                all_outputs[seq_num] = outputs
    else:
        # Backward compatibility: check problem_dir directly
        outputs = find_af3_outputs(problem_dir)
        if outputs:
            all_outputs["1"] = outputs

    return all_outputs


def package_multi_results(submission_dir: Path, output_dir: Path, status_file: Path, incremental: bool = True):
    """
    Package results from multi-problem submission.

    Supports multiple sequences per problem (seq_1, seq_2, etc.)

    Args:
        submission_dir: Directory containing problem subdirectories
        output_dir: Base directory for packaged results
        status_file: Path to status.json
        incremental: If True, reuse existing token and add new results

    Returns the token and list of newly packaged items if successful, (None, []) otherwise.
    """
    # Check if this is a multi-problem submission
    problem_dirs = sorted(submission_dir.glob("problem_*"))

    if not problem_dirs:
        # Fall back to single-problem behavior for backward compatibility
        token = package_single_result(submission_dir, output_dir, status_file)
        return token, ["single"] if token else []

    # Check which problems/sequences are complete
    # Structure: {problem_id: {seq_num: outputs}}
    completed_sequences = {}
    total_expected_sequences = 0

    for problem_dir in problem_dirs:
        if not problem_dir.is_dir():
            continue
        problem_id = problem_dir.name
        seq_outputs = find_all_sequence_outputs(problem_dir)
        if seq_outputs:
            completed_sequences[problem_id] = seq_outputs

        # Count expected sequences from problem_meta.json if available
        meta_file = problem_dir / "problem_meta.json"
        if meta_file.exists():
            with open(meta_file) as f:
                meta = json.load(f)
            total_expected_sequences += meta.get("num_sequences", 1)
        else:
            total_expected_sequences += 1

    if not completed_sequences:
        print(f"No completed sequences found in {submission_dir}", file=sys.stderr)
        return None, []

    # Count total completed sequences
    total_completed_sequences = sum(len(seqs) for seqs in completed_sequences.values())

    # Read main submission.json
    main_submission = submission_dir / "submission.json"
    if main_submission.exists():
        with open(main_submission) as f:
            submission_data = json.load(f)
    else:
        submission_data = {}

    participant_id = submission_data.get("participant_id", "unknown")
    total_problems = len(submission_data.get("sequences", {}))

    # Check if all sequences are complete
    all_complete = total_completed_sequences >= total_expected_sequences

    # Check for existing token (incremental mode)
    existing_token = None
    already_packaged = set()
    if status_file.exists():
        with open(status_file) as f:
            existing_status = json.load(f)
        existing_token = existing_status.get("result_token")
        already_packaged = set(existing_status.get("packaged_items", existing_status.get("packaged_problems", [])))

    # Determine which items are newly completed (problem_id_seq_num format)
    newly_completed = {}
    for problem_id, seq_outputs in completed_sequences.items():
        for seq_num, outputs in seq_outputs.items():
            item_key = f"{problem_id}_seq{seq_num}"
            if item_key not in already_packaged:
                if problem_id not in newly_completed:
                    newly_completed[problem_id] = {}
                newly_completed[problem_id][seq_num] = outputs

    if not newly_completed and existing_token:
        print(f"No new sequences to package (already packaged: {already_packaged})")
        return existing_token, []

    # Use existing token or generate new one
    if incremental and existing_token:
        token = existing_token
        token_dir = output_dir / token
    else:
        token = generate_token()
        token_dir = output_dir / token
        newly_completed = completed_sequences  # Package all if not incremental

    token_dir.mkdir(parents=True, exist_ok=True)

    copied_files = []
    problem_results = {}
    newly_packaged = []

    # Copy files from newly completed sequences
    for problem_id, seq_outputs in newly_completed.items():
        if problem_id not in problem_results:
            problem_results[problem_id] = {"files": [], "sequences": {}}

        for seq_num, outputs in seq_outputs.items():
            item_key = f"{problem_id}_seq{seq_num}"
            newly_packaged.append(item_key)

            seq_files = []
            for file_type, filepath in outputs.items():
                if filepath and filepath.exists():
                    # Rename file to include participant, problem ID, and sequence number
                    # e.g., team_alpha_problem_1_seq1_model.cif
                    suffix = filepath.suffix
                    stem = filepath.stem

                    # Determine sequence suffix (only add if multiple sequences)
                    num_seqs = len(seq_outputs)
                    seq_suffix = f"_seq{seq_num}" if num_seqs > 1 or int(seq_num) > 1 else ""

                    # Extract the file type (model, confidences, etc.)
                    if "_model" in stem:
                        new_name = f"{participant_id}_{problem_id}{seq_suffix}_model{suffix}"
                    elif "_summary_confidences" in stem:
                        new_name = f"{participant_id}_{problem_id}{seq_suffix}_summary_confidences{suffix}"
                    elif "_confidences" in stem:
                        new_name = f"{participant_id}_{problem_id}{seq_suffix}_confidences{suffix}"
                    elif "_ranking_scores" in stem:
                        new_name = f"{participant_id}_{problem_id}{seq_suffix}_ranking_scores{suffix}"
                    else:
                        new_name = f"{participant_id}_{problem_id}{seq_suffix}_{filepath.name}"

                    dest = token_dir / new_name
                    shutil.copy2(filepath, dest)
                    copied_files.append(new_name)
                    seq_files.append(new_name)
                    print(f"Copied {filepath.name} -> {new_name}")

            problem_results[problem_id]["sequences"][seq_num] = {"files": seq_files}
            problem_results[problem_id]["files"].extend(seq_files)

    # Copy main submission.json
    if main_submission.exists():
        shutil.copy2(main_submission, token_dir / "submission.json")
        copied_files.append("submission.json")

    # Load existing metadata if incremental
    existing_metadata = {}
    metadata_file = token_dir / "metadata.json"
    if metadata_file.exists():
        with open(metadata_file) as f:
            existing_metadata = json.load(f)

    # Merge with existing files and problems
    all_files = list(set(existing_metadata.get("files", []) + copied_files))
    all_problem_results = existing_metadata.get("problems", {})
    for problem_id, results in problem_results.items():
        if problem_id in all_problem_results:
            # Merge sequences
            existing_seqs = all_problem_results[problem_id].get("sequences", {})
            existing_seqs.update(results.get("sequences", {}))
            all_problem_results[problem_id]["sequences"] = existing_seqs
            all_problem_results[problem_id]["files"] = list(set(
                all_problem_results[problem_id].get("files", []) + results.get("files", [])
            ))
        else:
            all_problem_results[problem_id] = results

    # Create/update metadata file
    metadata = {
        "token": token,
        "participant_id": participant_id,
        "total_problems": total_problems,
        "completed_problems": len(completed_sequences),
        "total_sequences": total_completed_sequences,
        "all_complete": all_complete,
        "files": all_files,
        "problems": all_problem_results,
        "source_dir": str(submission_dir),
    }
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    # Update main status.json
    if status_file.exists():
        with open(status_file) as f:
            status = json.load(f)
    else:
        status = {}

    # Use "packaged" status - the workflow will set "completed" after copying to docs/results/
    # This prevents a race condition where status is "completed" but files aren't in docs/results/
    status["status"] = "packaged" if all_complete else "partial"
    status["result_token"] = token
    status["completed_problems"] = len(completed_sequences)
    status["completed_sequences"] = total_completed_sequences
    status["total_problems"] = total_problems
    status["packaged_items"] = list(already_packaged | set(newly_packaged))

    with open(status_file, "w") as f:
        json.dump(status, f, indent=2)

    print(f"Results packaged to {token_dir}")
    print(f"Completed: {len(completed_sequences)}/{total_problems} problems, {total_completed_sequences} sequences")
    print(f"Newly packaged: {newly_packaged}")
    return token, newly_packaged


def package_single_result(submission_dir: Path, output_dir: Path, status_file: Path):
    """
    Package results from single-problem submission (backward compatibility).
    """
    outputs = find_af3_outputs(submission_dir)

    if "model_cif" not in outputs:
        print(f"No model.cif found in {submission_dir}", file=sys.stderr)
        return None

    # Generate token and create output directory
    token = generate_token()
    token_dir = output_dir / token
    token_dir.mkdir(parents=True, exist_ok=True)

    # Copy output files
    copied = []
    for name, filepath in outputs.items():
        if filepath and filepath.exists():
            dest = token_dir / filepath.name
            shutil.copy2(filepath, dest)
            copied.append(filepath.name)
            print(f"Copied {filepath.name}")

    # Copy submission.json for metadata
    submission_json = submission_dir / "submission.json"
    if submission_json.exists():
        shutil.copy2(submission_json, token_dir / "submission.json")
        copied.append("submission.json")

    # Create metadata file
    metadata = {
        "token": token,
        "files": copied,
        "source_dir": str(submission_dir),
    }
    with open(token_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # Update status.json
    if status_file.exists():
        with open(status_file) as f:
            status = json.load(f)
    else:
        status = {}

    status["status"] = "completed"
    status["result_token"] = token

    with open(status_file, "w") as f:
        json.dump(status, f, indent=2)

    print(f"Results packaged to {token_dir}")
    return token


def main():
    parser = argparse.ArgumentParser(description="Package AF3 results with secret token")
    parser.add_argument("--submission-dir", required=True, type=Path,
                        help="Directory containing AF3 outputs")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="Base directory for packaged results")
    parser.add_argument("--status-file", required=True, type=Path,
                        help="Path to status.json file")
    parser.add_argument("--incremental", action="store_true", default=True,
                        help="Reuse existing token and add new results (default: True)")

    args = parser.parse_args()

    token, newly_packaged = package_multi_results(
        args.submission_dir, args.output_dir, args.status_file, args.incremental
    )

    if token:
        print(f"Token: {token}")
        print(f"Newly packaged: {','.join(newly_packaged) if newly_packaged else 'none'}")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
