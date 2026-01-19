#!/usr/bin/env python3
"""
Monitor SLURM job status and process completed AF3 jobs.

This script checks for completed AF3 jobs and prepares results for delivery.
Run via cron or scheduled GitHub Actions workflow.
"""

import argparse
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def get_job_status(job_id: str) -> dict:
    """Get SLURM job status using sacct."""
    try:
        result = subprocess.run(
            ["sacct", "-j", job_id, "--format=JobID,State,ExitCode,End", "--noheader", "-P"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {"status": "UNKNOWN", "error": result.stderr}

        # Parse output - get the main job (not steps)
        for line in result.stdout.strip().split("\n"):
            parts = line.split("|")
            if len(parts) >= 4 and not "." in parts[0]:  # Main job, not step
                return {
                    "job_id": parts[0],
                    "status": parts[1],
                    "exit_code": parts[2],
                    "end_time": parts[3],
                }
        return {"status": "UNKNOWN"}
    except subprocess.TimeoutExpired:
        return {"status": "UNKNOWN", "error": "timeout"}
    except FileNotFoundError:
        return {"status": "UNKNOWN", "error": "sacct not found"}


def find_af3_outputs(submission_dir: Path) -> dict:
    """Find AF3 output files in submission directory."""
    outputs = {
        "model_cif": None,
        "ranking_scores": None,
        "confidences": None,
        "summary": None,
    }

    # AF3 outputs structure varies - look for common patterns
    for cif_file in submission_dir.rglob("*.cif"):
        if "model" in cif_file.name.lower() or "fold" in cif_file.name.lower():
            outputs["model_cif"] = cif_file
            break

    for csv_file in submission_dir.rglob("ranking_scores.csv"):
        outputs["ranking_scores"] = csv_file
        break

    for json_file in submission_dir.rglob("*confidences*.json"):
        outputs["confidences"] = json_file
        break

    for json_file in submission_dir.rglob("*summary*.json"):
        outputs["summary"] = json_file
        break

    return outputs


def generate_result_token() -> str:
    """Generate a secure random token for result access."""
    return secrets.token_urlsafe(32)


def package_results(submission_dir: Path, output_dir: Path) -> Path | None:
    """Package AF3 results for delivery."""
    outputs = find_af3_outputs(submission_dir)

    if not outputs["model_cif"]:
        logger.error(f"No model CIF found in {submission_dir}")
        return None

    # Create package directory
    token = generate_result_token()
    package_dir = output_dir / token
    package_dir.mkdir(parents=True, exist_ok=True)

    # Copy relevant files
    files_copied = []
    for name, filepath in outputs.items():
        if filepath and filepath.exists():
            dest = package_dir / filepath.name
            shutil.copy2(filepath, dest)
            files_copied.append(filepath.name)

    # Also copy the input sequence for reference
    submission_json = submission_dir / "submission.json"
    if submission_json.exists():
        shutil.copy2(submission_json, package_dir / "submission.json")
        files_copied.append("submission.json")

    # Create metadata
    metadata = {
        "token": token,
        "files": files_copied,
        "submission_dir": str(submission_dir),
    }
    with open(package_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Packaged results to {package_dir}")
    return package_dir


def update_submission_status(submission_dir: Path, status: str, result_token: str = None):
    """Update submission status file."""
    status_file = submission_dir / "status.json"

    if status_file.exists():
        with open(status_file) as f:
            data = json.load(f)
    else:
        data = {}

    data["status"] = status
    if result_token:
        data["result_token"] = result_token

    with open(status_file, "w") as f:
        json.dump(data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Check AF3 job status and process completed jobs"
    )
    parser.add_argument(
        "--submission-dir",
        required=True,
        type=Path,
        help="Directory containing submission data",
    )
    parser.add_argument(
        "--job-id",
        required=True,
        help="SLURM job ID to check",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("public_results"),
        help="Directory for packaged results (default: public_results)",
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "text"],
        default="text",
        help="Output format",
    )

    args = parser.parse_args()

    # Get job status
    status = get_job_status(args.job_id)
    logger.info(f"Job {args.job_id} status: {status.get('status', 'UNKNOWN')}")

    result = {
        "job_id": args.job_id,
        "job_status": status.get("status", "UNKNOWN"),
        "submission_dir": str(args.submission_dir),
        "completed": False,
        "success": False,
        "result_token": None,
    }

    if status.get("status") == "COMPLETED":
        result["completed"] = True

        # Check exit code
        exit_code = status.get("exit_code", "")
        if exit_code.startswith("0:"):
            result["success"] = True

            # Package results
            package_dir = package_results(args.submission_dir, args.results_dir)
            if package_dir:
                result["result_token"] = package_dir.name
                update_submission_status(
                    args.submission_dir, "completed", package_dir.name
                )
            else:
                result["success"] = False
                result["error"] = "Failed to find AF3 outputs"
                update_submission_status(args.submission_dir, "failed")
        else:
            result["error"] = f"Job failed with exit code: {exit_code}"
            update_submission_status(args.submission_dir, "failed")

    elif status.get("status") in ["FAILED", "CANCELLED", "TIMEOUT"]:
        result["completed"] = True
        result["error"] = f"Job {status.get('status')}"
        update_submission_status(args.submission_dir, "failed")

    # Output
    if args.output_format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"Job ID: {result['job_id']}")
        print(f"Status: {result['job_status']}")
        print(f"Completed: {result['completed']}")
        print(f"Success: {result['success']}")
        if result.get("result_token"):
            print(f"Result Token: {result['result_token']}")
        if result.get("error"):
            print(f"Error: {result['error']}")

    # Exit code indicates completion status
    sys.exit(0 if result["completed"] else 1)


if __name__ == "__main__":
    main()
