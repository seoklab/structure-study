#!/usr/bin/env python3
"""
End competition and publish all results.

This script:
1. Collects all completed submissions
2. Generates a public leaderboard page
3. Creates a gallery of all structures
4. Updates all issues to mark competition as ended
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def collect_submissions(results_dir: Path) -> list[dict]:
    """Collect all completed submissions with their results."""
    submissions = []

    for submission_dir in results_dir.glob("submission_*"):
        if not submission_dir.is_dir():
            continue

        submission_file = submission_dir / "submission.json"
        status_file = submission_dir / "status.json"

        if not submission_file.exists():
            continue

        with open(submission_file) as f:
            submission = json.load(f)

        status = {}
        if status_file.exists():
            with open(status_file) as f:
                status = json.load(f)

        # Skip if not completed
        if status.get("status") != "completed":
            logger.warning(f"Skipping {submission_dir.name}: status={status.get('status', 'unknown')}")
            continue

        submission["submission_id"] = submission_dir.name
        submission["result_token"] = status.get("result_token")
        submission["completed_at"] = status.get("completed_at", "")

        submissions.append(submission)

    return submissions


def generate_leaderboard_html(submissions: list[dict], output_file: Path, results_url: str):
    """Generate HTML leaderboard/gallery page."""

    # Sort by participant_id, then sequence_name
    submissions.sort(key=lambda x: (x.get("participant_id", ""), x.get("sequence_name", "")))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Protein Design Competition - Results</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
            padding: 2rem;
        }}
        .header {{
            text-align: center;
            margin-bottom: 3rem;
        }}
        .header h1 {{
            font-size: 2.5rem;
            color: #e94560;
            margin-bottom: 0.5rem;
        }}
        .header p {{
            color: #aaa;
            font-size: 1.1rem;
        }}
        .stats {{
            display: flex;
            justify-content: center;
            gap: 2rem;
            margin-bottom: 2rem;
        }}
        .stat {{
            background: #16213e;
            padding: 1.5rem 2rem;
            border-radius: 10px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 2rem;
            font-weight: bold;
            color: #e94560;
        }}
        .stat-label {{
            color: #aaa;
            font-size: 0.9rem;
        }}
        .submissions {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 1.5rem;
            max-width: 1400px;
            margin: 0 auto;
        }}
        .submission-card {{
            background: #16213e;
            border-radius: 12px;
            overflow: hidden;
            transition: transform 0.2s;
        }}
        .submission-card:hover {{
            transform: translateY(-4px);
        }}
        .card-header {{
            background: #0f3460;
            padding: 1rem;
        }}
        .card-header h3 {{
            font-size: 1.1rem;
            margin-bottom: 0.25rem;
        }}
        .card-header .participant {{
            color: #aaa;
            font-size: 0.85rem;
        }}
        .card-body {{
            padding: 1rem;
        }}
        .card-body p {{
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
        }}
        .card-body .label {{
            color: #aaa;
        }}
        .card-actions {{
            padding: 1rem;
            display: flex;
            gap: 0.5rem;
        }}
        .btn {{
            flex: 1;
            padding: 0.6rem;
            border: none;
            border-radius: 6px;
            font-size: 0.85rem;
            cursor: pointer;
            text-decoration: none;
            text-align: center;
        }}
        .btn-primary {{
            background: #e94560;
            color: white;
        }}
        .btn-secondary {{
            background: #0f3460;
            color: white;
        }}
        .btn:hover {{
            opacity: 0.9;
        }}
        .footer {{
            text-align: center;
            margin-top: 3rem;
            color: #666;
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Protein Design Competition</h1>
        <p>Final Results - Generated {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
    </div>

    <div class="stats">
        <div class="stat">
            <div class="stat-value">{len(submissions)}</div>
            <div class="stat-label">Total Submissions</div>
        </div>
        <div class="stat">
            <div class="stat-value">{len(set(s.get('participant_id') for s in submissions))}</div>
            <div class="stat-label">Participants</div>
        </div>
    </div>

    <div class="submissions">
"""

    for sub in submissions:
        token = sub.get("result_token", "")
        viewer_url = f"viewer.html?token={token}" if token else "#"
        download_url = f"{results_url}/{token}/" if token else "#"

        html += f"""
        <div class="submission-card">
            <div class="card-header">
                <h3>{sub.get('sequence_name', 'Unknown')}</h3>
                <div class="participant">{sub.get('participant_id', 'Unknown')}</div>
            </div>
            <div class="card-body">
                <p><span class="label">Length:</span> {sub.get('sequence_length', 'N/A')} residues</p>
                <p><span class="label">Submission:</span> {sub.get('submission_id', 'N/A')}</p>
            </div>
            <div class="card-actions">
                <a href="{viewer_url}" class="btn btn-primary">View Structure</a>
                <a href="{download_url}" class="btn btn-secondary">Download</a>
            </div>
        </div>
"""

    html += """
    </div>

    <div class="footer">
        <p>Structures predicted using AlphaFold3</p>
    </div>
</body>
</html>
"""

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        f.write(html)

    logger.info(f"Generated leaderboard: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="End competition and publish all results"
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory containing submission results",
    )
    parser.add_argument(
        "--public-dir",
        type=Path,
        default=Path("docs"),
        help="Directory for public output (GitHub Pages)",
    )
    parser.add_argument(
        "--results-url",
        default="results",
        help="Base URL for results (relative or absolute)",
    )
    parser.add_argument(
        "--public-results-dir",
        type=Path,
        default=Path("public_results"),
        help="Directory containing packaged results with tokens",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    logger.info("Collecting submissions...")
    submissions = collect_submissions(args.results_dir)
    logger.info(f"Found {len(submissions)} completed submissions")

    if args.dry_run:
        logger.info("Dry run - would publish:")
        for sub in submissions:
            logger.info(f"  - {sub['participant_id']}/{sub['sequence_name']}")
        return

    # Generate leaderboard
    generate_leaderboard_html(
        submissions,
        args.public_dir / "index.html",
        args.results_url,
    )

    # Copy viewer template
    viewer_src = Path("templates/viewer.html")
    viewer_dst = args.public_dir / "viewer.html"
    if viewer_src.exists():
        import shutil
        shutil.copy2(viewer_src, viewer_dst)
        logger.info(f"Copied viewer to {viewer_dst}")

    # Copy public_results to docs/results for GitHub Pages
    if args.public_results_dir.exists():
        import shutil
        dest = args.public_dir / "results"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(args.public_results_dir, dest)
        logger.info(f"Copied results to {dest}")

    logger.info("Competition ended. Results published to docs/")
    logger.info("Enable GitHub Pages (Settings > Pages > Source: docs/) to make public")


if __name__ == "__main__":
    main()
