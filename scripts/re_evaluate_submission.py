#!/usr/bin/env python3
"""
Re-evaluate an existing submission with updated evaluation metrics.

Usage:
    python scripts/re_evaluate_submission.py --token URFIfPqnl-4zKO6x7xYUBiN85nNA2S1i
    python scripts/re_evaluate_submission.py --token URFIfPqnl-4zKO6x7xYUBiN85nNA2S1i --problem problem_1
    python scripts/re_evaluate_submission.py --all  # Re-evaluate all submissions
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def load_config():
    """Load problem configuration."""
    config_path = Path("docs/targets/config.json")
    with open(config_path) as f:
        return json.load(f)


def get_result_dirs(token=None):
    """Get result directories to process."""
    results_dir = Path("docs/results")
    
    if token:
        token_dir = results_dir / token
        if not token_dir.exists():
            print(f"Error: Token directory not found: {token_dir}")
            sys.exit(1)
        return [token_dir]
    else:
        # Get all result directories except .gitkeep and index.json
        return [d for d in results_dir.iterdir() 
                if d.is_dir() and d.name not in ['.git', '__pycache__']]


def find_submissions(result_dir: Path):
    """Find all submission files in a result directory."""
    submissions = []
    
    # Find all model.cif files
    for model_file in result_dir.glob("*_model.cif"):
        # Parse filename: {participant_id}_{problem_id}_{seq_id}_model.cif
        parts = model_file.stem.replace("_model", "").split("_")
        
        # Try to identify problem_id (look for "problem_" pattern)
        problem_id = None
        seq_id = None
        
        for i, part in enumerate(parts):
            if part == "problem" and i + 1 < len(parts):
                problem_id = f"problem_{parts[i+1]}"
                # Check if there's a seq_id after problem
                if i + 2 < len(parts):
                    seq_id = parts[i+2]
                break
        
        if not problem_id:
            print(f"Warning: Could not parse problem_id from {model_file.name}")
            continue
        
        participant_id = "_".join(parts[:parts.index("problem")])
        
        submissions.append({
            "model_file": model_file,
            "problem_id": problem_id,
            "participant_id": participant_id,
            "seq_id": seq_id,
            "token": result_dir.name
        })
    
    return submissions


def get_reference_file(problem_id: str, config: dict) -> Path:
    """Get reference file path for a problem."""
    for problem in config["problems"]:
        if problem["id"] == problem_id:
            target_file = problem["target_file"]
            ref_path = Path("docs/targets") / target_file
            if ref_path.exists():
                return ref_path
            else:
                print(f"Warning: Reference file not found: {ref_path}")
                return None
    return None


def get_problem_type(problem_id: str, config: dict) -> str:
    """Get problem type (monomer/binder)."""
    for problem in config["problems"]:
        if problem["id"] == problem_id:
            return problem.get("type", "monomer")
    return "monomer"


def run_evaluation(submission: dict, reference_file: Path, problem_type: str):
    """Run evaluation for a single submission."""
    model_file = submission["model_file"]
    result_dir = model_file.parent
    
    # Build output filename
    if submission["seq_id"]:
        output_file = result_dir / f"{submission['participant_id']}_{submission['problem_id']}_{submission['seq_id']}_evaluation.json"
    else:
        output_file = result_dir / f"{submission['participant_id']}_{submission['problem_id']}_evaluation.json"
    
    cmd = [
        sys.executable, "scripts/evaluate_structure.py",
        "--model", str(model_file),
        "--reference", str(reference_file),
        "--problem-id", submission["problem_id"],
        "--problem-type", problem_type,
        "--participant-id", submission["participant_id"],
        "--token", submission["token"],
        "--result-dir", str(result_dir),
        "--output", str(output_file)
    ]
    
    if submission["seq_id"]:
        cmd.extend(["--seq-id", submission["seq_id"]])
    
    print(f"Evaluating: {model_file.name}")
    print(f"  Problem: {submission['problem_id']} ({problem_type})")
    print(f"  Output: {output_file.name}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"  ✓ Success")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Error: {e}")
        print(f"  stderr: {e.stderr}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Re-evaluate existing submissions")
    parser.add_argument("--token", help="Specific token to re-evaluate")
    parser.add_argument("--problem", help="Specific problem ID to re-evaluate (e.g., problem_1)")
    parser.add_argument("--all", action="store_true", help="Re-evaluate all submissions")
    
    args = parser.parse_args()
    
    if not args.token and not args.all:
        parser.error("Must specify either --token <TOKEN> or --all")
    
    # Load configuration
    config = load_config()
    
    # Get result directories
    result_dirs = get_result_dirs(args.token)
    
    print(f"Found {len(result_dirs)} result directories to process")
    print()
    
    total = 0
    success = 0
    
    for result_dir in result_dirs:
        print(f"Processing: {result_dir.name}")
        submissions = find_submissions(result_dir)
        
        # Filter by problem if specified
        if args.problem:
            submissions = [s for s in submissions if s["problem_id"] == args.problem]
        
        print(f"  Found {len(submissions)} submissions")
        
        for submission in submissions:
            total += 1
            
            # Get reference file and problem type
            reference_file = get_reference_file(submission["problem_id"], config)
            if not reference_file:
                print(f"  Skipping {submission['model_file'].name} - no reference file")
                continue
            
            problem_type = get_problem_type(submission["problem_id"], config)
            
            # Run evaluation
            if run_evaluation(submission, reference_file, problem_type):
                success += 1
        
        print()
    
    print(f"Completed: {success}/{total} evaluations successful")
    
    # Update leaderboard if any evaluations succeeded
    if success > 0:
        print("\nUpdating leaderboard...")
        subprocess.run([sys.executable, "scripts/update_leaderboard.py"], check=False)
        print("Done!")


if __name__ == "__main__":
    main()
