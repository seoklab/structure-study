#!/usr/bin/env python3
"""
Generate and optionally submit sbatch scripts for AlphaFold3 jobs.

This script creates SLURM batch scripts for running AF3 in two phases:
1. CPU phase: Data pipeline (MSA generation, template search)
2. GPU phase: Model inference

For the competition, we run both phases sequentially in a single job.
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# SLURM configuration
SLURM_CONFIG = {
    "partition_gpu": "gpu-micro.q",
    "partition_cpu": "normal.q",
    "cpus": 6,
}


def generate_sbatch_script(
    submission_id: str,
    json_path: Path,
    output_dir: Path,
    log_dir: Path,
    mode: str = "full",
    participant_id: str | None = None,
    partition: str | None = None,
    exclude_nodes: str | None = None,
) -> str:
    """
    Generate sbatch script content for AF3 job.

    Args:
        submission_id: Unique submission identifier
        json_path: Path to AF3 input JSON
        output_dir: Directory for AF3 outputs
        log_dir: Directory for SLURM logs
        mode: "full" (both phases), "cpu" (data pipeline only), "gpu" (inference only)
        participant_id: Team/participant ID for singleton job grouping
        partition: Override default GPU partition (e.g., gpu-super.q for larger jobs)
        exclude_nodes: Comma-separated list of nodes to exclude

    Returns:
        str: sbatch script content
    """
    log_file = log_dir / f"{submission_id}.log"

    # Use participant_id as job name for singleton grouping (1 job per team at a time)
    # If not provided, fall back to submission_id
    job_name = participant_id if participant_id else submission_id

    # Add singleton dependency if participant_id is provided
    singleton_line = "#SBATCH --dependency=singleton\n" if participant_id else ""

    # Add node exclusion if specified
    exclude_line = f"#SBATCH --exclude={exclude_nodes}\n" if exclude_nodes else ""

    # Determine GPU partition (allow override)
    gpu_partition = partition if partition else SLURM_CONFIG["partition_gpu"]

    script = f"""#!/bin/bash
#SBATCH -J {job_name}
#SBATCH -o {log_file}
#SBATCH -e {log_file}
#SBATCH --nice={SLURM_CONFIG['nice']}
{singleton_line}{exclude_line}"""

    # Conda environment activation
    conda_activate = "source /opt/conda/etc/profile.d/conda.sh && conda activate /opt/conda/envs/alphafold3"

    if mode == "cpu":
        # CPU-only: data pipeline
        script += f"""#SBATCH -p {SLURM_CONFIG['partition_cpu']}
#SBATCH --nodes=1
#SBATCH -c {SLURM_CONFIG['cpus']}

echo "Starting AF3 data pipeline for {submission_id}"
echo "Start time: $(date)"

{conda_activate}

af3 --norun_inference \\
    --flash_attention_implementation=xla \\
    --json_path={json_path} \\
    --output_dir={output_dir}

echo "End time: $(date)"
echo "Data pipeline complete for {submission_id}"
"""
    elif mode == "gpu":
        # GPU-only: inference (assumes data pipeline already ran)
        script += f"""#SBATCH -p {gpu_partition}
#SBATCH --gres=gpu:1
#SBATCH -N 1
#SBATCH -c {SLURM_CONFIG['cpus']}

echo "Starting AF3 inference for {submission_id}"
echo "Start time: $(date)"

{conda_activate}

af3 --norun_data_pipeline \\
    --run_inference \\
    --flash_attention_implementation=xla \\
    --json_path={json_path} \\
    --output_dir={output_dir}

echo "End time: $(date)"
echo "Inference complete for {submission_id}"
"""
    else:
        # Full: both phases in sequence (GPU partition)
        script += f"""#SBATCH -p {gpu_partition}
#SBATCH --gres=gpu:1
#SBATCH -N 1
#SBATCH -c {SLURM_CONFIG['cpus']}

echo "Starting AF3 full pipeline for {submission_id}"
echo "Start time: $(date)"

{conda_activate}

af3 --flash_attention_implementation=xla \\
    --json_path={json_path} \\
    --output_dir={output_dir}

echo "End time: $(date)"
echo "AF3 complete for {submission_id}"
"""

    return script


def main():
    parser = argparse.ArgumentParser(
        description="Generate sbatch scripts for AF3 jobs"
    )
    parser.add_argument(
        "--submission-dir",
        required=True,
        type=Path,
        help="Directory containing af3_input.json",
    )
    parser.add_argument(
        "--submission-id",
        required=True,
        help="Unique submission identifier",
    )
    parser.add_argument(
        "--participant-id",
        default=None,
        help="Participant/team ID for singleton job grouping (limits to 1 concurrent job per team)",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "cpu", "gpu"],
        default="full",
        help="Run mode: full (both phases), cpu (data pipeline), gpu (inference)",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit job to SLURM after generating script",
    )
    parser.add_argument(
        "--scripts-dir",
        type=Path,
        default=None,
        help="Directory to save sbatch scripts (default: submission_dir/scripts)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="Directory for SLURM logs (default: submission_dir/logs)",
    )
    parser.add_argument(
        "--partition",
        default=None,
        help="Override GPU partition (default: gpu-micro.q)",
    )
    parser.add_argument(
        "--exclude",
        default=None,
        help="Comma-separated list of nodes to exclude",
    )

    args = parser.parse_args()

    # Validate input
    json_path = args.submission_dir / "af3_input.json"
    if not json_path.exists():
        logger.error(f"AF3 input not found: {json_path}")
        sys.exit(1)

    # Set up directories
    scripts_dir = args.scripts_dir or (args.submission_dir / "scripts")
    log_dir = args.log_dir or (args.submission_dir / "logs")
    scripts_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Generate script
    script_content = generate_sbatch_script(
        submission_id=args.submission_id,
        json_path=json_path.resolve(),
        output_dir=args.submission_dir.resolve(),
        log_dir=log_dir.resolve(),
        mode=args.mode,
        participant_id=args.participant_id,
        partition=args.partition,
        exclude_nodes=args.exclude,
    )

    # Save script
    script_file = scripts_dir / f"run_{args.submission_id}_{args.mode}.sh"
    with open(script_file, "w") as f:
        f.write(script_content)
    script_file.chmod(0o755)

    logger.info(f"Generated sbatch script: {script_file}")

    # Submit if requested
    if args.submit:
        logger.info(f"Submitting job to SLURM...")
        result = subprocess.run(
            ["sbatch", str(script_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info(f"Job submitted: {result.stdout.strip()}")
        else:
            logger.error(f"Failed to submit job: {result.stderr}")
            sys.exit(1)


if __name__ == "__main__":
    main()
