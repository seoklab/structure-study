#!/usr/bin/env python3
"""
Update leaderboard data by aggregating evaluation results.

Scans docs/results/*/  directories for evaluation files and AF3 confidence metrics,
then generates docs/leaderboard_data.json with per-problem and overall rankings.

Usage:
    python update_leaderboard.py --results-dir docs/results --config docs/targets/config.json \
        --output docs/leaderboard_data.json
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import numpy as np


def extract_team_name(participant_id: str, submitted_at: str = None) -> str:
    """
    Extract team name from participant_id and append trial number based on submission time.

    Expected format: team1_day1_round1 -> team1_trial1 or team1_trial2
    
    Trial determination (KST, Feb 3, 2026):
      - Before 18:00 (6 PM): trial1
      - 18:00-20:00: trial1
      - After 20:00 (8 PM): trial2

    Falls back to full participant_id if pattern not matched.
    """
    # Pattern: teamname_day<N>_round<M>
    match = re.match(r'^([^_]+)_day\d+_round\d+$', participant_id)
    if match:
        team_base = match.group(1)
    else:
        # Legacy pattern: try to extract first segment before underscore
        # Only if it looks like a team name (alphanumeric)
        parts = participant_id.split('_')
        if len(parts) >= 1 and parts[0].isalnum():
            team_base = parts[0]
        else:
            return participant_id

    # Determine trial number from submission time
    if submitted_at:
        try:
            # Parse ISO timestamp (e.g., "2026-02-03T10:30:00Z")
            dt = datetime.fromisoformat(submitted_at.replace('Z', '+00:00'))
            # Convert to KST (UTC+9)
            kst_time = dt + timedelta(hours=9)
            
            # Check if it's Feb 3, 2026 (for trial logic)
            if kst_time.year == 2026 and kst_time.month == 2 and kst_time.day == 3:
                hour = kst_time.hour
                if hour < 18:
                    trial = "trial1"
                elif hour < 20:
                    trial = "trial1"  # 18:00-19:59
                else:
                    trial = "trial2"  # 20:00+
            else:
                # For other dates, default to trial1
                trial = "trial1"
            
            return f"{team_base}_{trial}"
        except Exception as e:
            # If parsing fails, return base team name without trial
            print(f"Warning: Could not parse timestamp '{submitted_at}': {e}", file=sys.stderr)
            return team_base
    
    # No timestamp provided, return base name only
    return team_base


def load_config(config_path: str) -> dict:
    """Load problem configuration."""
    with open(config_path) as f:
        return json.load(f)


def get_problem_info(config: dict) -> dict:
    """Extract problem metadata from config."""
    problems = {}
    for p in config.get("problems", []):
        if p["id"].startswith("_"):
            continue  # Skip example problems
        problems[p["id"]] = {
            "name": p["name"],
            "type": p.get("type", "monomer"),
            "residue_count": p.get("residue_count"),
            "description": p.get("description", ""),
            # Primary metric for z-score ranking (configurable per problem in config.json)
            # Options: bb_lddt, binder_lddt, interface_lddt, iptm, tm_score, etc.
            "primary_metric": p.get("primary_metric", "bb_lddt"),
            # Day and visibility for auto-hiding problems
            "day": p.get("day", 1),
            "hidden": p.get("hidden")  # None = auto, True = always hide, False = always show
        }
    return problems


def scan_results(results_dir: str, problem_info: dict) -> dict:
    """
    Scan results directories for evaluation data.

    Supports multi-sequence submissions - finds all sequence evaluations
    and keeps only the BEST per participant per problem.

    Returns dict mapping problem_id -> list of participant entries (best per participant)
    """
    results_path = Path(results_dir)
    # Collect all entries first, then deduplicate
    all_entries: dict[str, list] = {pid: [] for pid in problem_info}

    for token_dir in results_path.iterdir():
        if not token_dir.is_dir() or token_dir.name == ".gitkeep":
            continue

        token = token_dir.name

        # Load metadata and submission info
        metadata_file = token_dir / "metadata.json"
        submission_file = token_dir / "submission.json"

        if not metadata_file.exists():
            continue

        try:
            with open(metadata_file) as f:
                metadata = json.load(f)
            with open(submission_file) as f:
                submission = json.load(f)
        except Exception as e:
            print(f"Warning: Could not read metadata for {token}: {e}", file=sys.stderr)
            continue

        participant_id = submission.get("participant_id", "unknown")
        submitted_at = submission.get("submitted_at", "")

        # Check for evaluation files or extract AF3 metrics directly
        problems = metadata.get("problems", {})

        for problem_id in problems:
            if problem_id not in problem_info:
                continue

            ptype = problem_info[problem_id]["type"]
            problem_data = problems[problem_id]

            # Check if this problem has multiple sequences
            sequences = problem_data.get("sequences", {})
            if sequences:
                # Multi-sequence: process each sequence
                for seq_num in sequences:
                    entry = process_sequence_entry(
                        token_dir, token, participant_id, submitted_at,
                        problem_id, ptype, seq_num
                    )
                    if entry and entry.get("primary_score") is not None:
                        all_entries[problem_id].append(entry)
            else:
                # Single sequence (legacy format)
                entry = process_sequence_entry(
                    token_dir, token, participant_id, submitted_at,
                    problem_id, ptype, None
                )
                if entry and entry.get("primary_score") is not None:
                    all_entries[problem_id].append(entry)

    # Deduplicate: keep only best entry per participant per problem
    problem_results = {pid: [] for pid in problem_info}
    for problem_id, entries in all_entries.items():
        best_by_participant: dict[str, dict] = {}
        for entry in entries:
            pid = entry["participant_id"]
            score = entry.get("primary_score") or 0
            if pid not in best_by_participant or score > (best_by_participant[pid].get("primary_score") or 0):
                best_by_participant[pid] = entry
        problem_results[problem_id] = list(best_by_participant.values())

    return problem_results


def process_sequence_entry(
    token_dir: Path,
    token: str,
    participant_id: str,
    submitted_at: str,
    problem_id: str,
    ptype: str,
    seq_num: str | None
) -> dict | None:
    """
    Process a single sequence entry and extract metrics.

    Args:
        token_dir: Directory containing result files
        token: Result token
        participant_id: Participant identifier
        submitted_at: Submission timestamp
        problem_id: Problem identifier
        ptype: Problem type (monomer/binder)
        seq_num: Sequence number (None for legacy single-sequence format)

    Returns:
        Entry dict with metrics, or None if no data found
    """
    entry = {
        "participant_id": participant_id,
        "token": token,
        "submitted_at": submitted_at,
        "problem_type": ptype,
        "seq_num": seq_num
    }

    # Build file pattern based on whether this is multi-sequence
    if seq_num:
        seq_suffix = f"_seq{seq_num}"
        file_patterns = [
            f"{participant_id}_{problem_id}{seq_suffix}_evaluation.json",
            f"{participant_id}_{problem_id}_seq{seq_num}_evaluation.json",
            f"evaluation_{problem_id}_seq{seq_num}.json",
            # Fallback to legacy patterns (no seq suffix) for older submissions
            f"{participant_id}_{problem_id}_evaluation.json",
            f"evaluation_{problem_id}.json",
        ]
        conf_patterns = [
            f"*{problem_id}{seq_suffix}_summary_confidences.json",
            f"*{problem_id}_seq{seq_num}_summary_confidences.json",
            f"*{problem_id}_summary_confidences.json",
        ]
    else:
        file_patterns = [
            f"{participant_id}_{problem_id}_evaluation.json",
            f"evaluation_{problem_id}.json",
        ]
        conf_patterns = [
            f"*{problem_id}_summary_confidences.json",
        ]

    # Look for evaluation file
    eval_file = None
    for pattern in file_patterns:
        candidate = token_dir / pattern
        if candidate.exists():
            eval_file = candidate
            break

    if eval_file:
        try:
            with open(eval_file) as f:
                eval_data = json.load(f)
            entry["metrics"] = eval_data.get("metrics", {})
            entry["af3_metrics"] = eval_data.get("af3_metrics", {})
            entry["binder_metrics"] = eval_data.get("binder_metrics", {})
            entry["interface_metrics"] = eval_data.get("interface_metrics", {})
            entry["primary_score"] = eval_data.get("primary_score")
            entry["primary_metric"] = eval_data.get("primary_metric")
        except Exception as e:
            print(f"Warning: Could not read evaluation for {token}/{problem_id}: {e}",
                  file=sys.stderr)

    # Also try to load AF3 confidences directly if no evaluation file
    if "af3_metrics" not in entry or not entry["af3_metrics"]:
        for pattern in conf_patterns:
            for conf_file in token_dir.glob(pattern):
                try:
                    with open(conf_file) as f:
                        conf_data = json.load(f)
                    entry["af3_metrics"] = {
                        "ptm": conf_data.get("ptm"),
                        "iptm": conf_data.get("iptm"),
                        "ranking_score": conf_data.get("ranking_score"),
                        "chain_pair_iptm": conf_data.get("chain_pair_iptm"),
                        "fraction_disordered": conf_data.get("fraction_disordered")
                    }
                    break
                except Exception:
                    continue
            if entry.get("af3_metrics"):
                break

    # Determine primary score if not set
    if entry.get("primary_score") is None:
        af3 = entry.get("af3_metrics", {})

        if ptype == "binder":
            # For binders, use chain_pair_iptm or ranking_score
            chain_iptm = af3.get("chain_pair_iptm")
            if chain_iptm and isinstance(chain_iptm, list) and len(chain_iptm) > 0:
                if isinstance(chain_iptm[0], list) and len(chain_iptm[0]) > 0:
                    entry["primary_score"] = chain_iptm[0][0]
                    entry["primary_metric"] = "iptm"
            if entry.get("primary_score") is None:
                entry["primary_score"] = af3.get("ranking_score")
                entry["primary_metric"] = "ranking_score"
        else:
            # For monomers, use ptm or ranking_score
            metrics = entry.get("metrics", {})
            if metrics.get("bb_lddt"):
                entry["primary_score"] = metrics["bb_lddt"]
                entry["primary_metric"] = "bb_lddt"
            elif metrics.get("tm_score"):
                entry["primary_score"] = metrics["tm_score"]
                entry["primary_metric"] = "tm_score"
            elif af3.get("ptm"):
                entry["primary_score"] = af3["ptm"]
                entry["primary_metric"] = "ptm"
            else:
                entry["primary_score"] = af3.get("ranking_score")
                entry["primary_metric"] = "ranking_score"

    return entry


def get_metric_value(entry: dict, metric_name: str, problem_type: str) -> float | None:
    """
    Extract a metric value from an entry based on metric name.

    Supported metrics:
      - bb_lddt: backbone lDDT (from metrics or binder_metrics for binders)
      - bb_lddt_cov: coverage-weighted lDDT (lDDT × coverage, already computed)
      - binder_lddt: binder-only lDDT (binder problems)
      - interface_lddt: interface lDDT (binder problems)
      - tm_score: TM-score
      - binder_tm: binder TM-score (binder problems)
      - iptm: interface pTM from AF3
      - ptm: pTM from AF3
      - plddt: mean pLDDT from AF3

    To change the ranking metric for a problem, edit 'primary_metric' in config.json.
    """
    metrics = entry.get("metrics", {})
    binder_metrics = entry.get("binder_metrics", {})
    interface_metrics = entry.get("interface_metrics", {})
    af3_metrics = entry.get("af3_metrics", {})

    if metric_name == "bb_lddt":
        # For binder problems, use binder_lddt as bb_lddt
        if problem_type == "binder":
            return binder_metrics.get("binder_lddt") or metrics.get("bb_lddt")
        return metrics.get("bb_lddt")

    elif metric_name == "bb_lddt_cov":
        # Coverage-weighted lDDT (already computed as lDDT × coverage)
        return metrics.get("bb_lddt_cov")

    elif metric_name == "binder_lddt":
        return binder_metrics.get("binder_lddt")

    elif metric_name == "interface_lddt":
        return interface_metrics.get("interface_lddt")

    elif metric_name == "tm_score":
        # For binders, use binder_tm_score; for monomers, use tm_score
        if problem_type == "binder":
            return binder_metrics.get("binder_tm_score") or metrics.get("complex_tm_score") or metrics.get("tm_score")
        return metrics.get("tm_score")

    elif metric_name == "binder_tm":
        return binder_metrics.get("binder_tm_score")

    elif metric_name == "iptm":
        chain_iptm = af3_metrics.get("chain_pair_iptm")
        if chain_iptm and isinstance(chain_iptm, list) and len(chain_iptm) > 0:
            if isinstance(chain_iptm[0], list) and len(chain_iptm[0]) > 1:
                return chain_iptm[0][1]  # Off-diagonal element
        return af3_metrics.get("iptm")

    elif metric_name == "ptm":
        return af3_metrics.get("ptm")

    elif metric_name == "plddt":
        return af3_metrics.get("mean_plddt")

    return None


def rank_entries(entries: list[dict], descending: bool = True) -> list[dict]:
    """
    Rank entries by primary score.

    Returns sorted list with rank field added.
    """
    # Filter out entries without scores
    valid_entries = [e for e in entries if e.get("primary_score") is not None]

    # Sort by primary score
    sorted_entries = sorted(
        valid_entries,
        key=lambda x: (x.get("primary_score") or 0),
        reverse=descending
    )

    # Add ranks (handle ties)
    ranked = []
    prev_score = None
    prev_rank = 0
    for i, entry in enumerate(sorted_entries):
        score = entry.get("primary_score")
        if score == prev_score:
            rank = prev_rank
        else:
            rank = i + 1
            prev_rank = rank
        prev_score = score

        ranked_entry = entry.copy()
        ranked_entry["rank"] = rank
        ranked.append(ranked_entry)

    return ranked


def compute_overall_rankings(problem_results: dict[str, list], problem_info: dict) -> list[dict]:
    """
    Compute overall rankings by aggregating scores across problems.

    Groups submissions by TEAM (extracted from participant_id, e.g., team1_day1_round1 -> team1).
    Uses configurable primary_metric per problem for z-score calculation.
    Overall ranking = average z-score across all problems (higher is better).

    To change the primary metric for a problem:
      Edit 'primary_metric' in docs/targets/config.json for that problem.
      Options: bb_lddt, binder_lddt, interface_lddt, iptm, tm_score, etc.
    """
    # Step 1: Aggregate by team - find best score per team per problem
    team_data: dict[str, dict[str, Any]] = {}

    for problem_id, entries in problem_results.items():
        if not entries:
            continue

        pinfo = problem_info.get(problem_id, {})
        ptype = pinfo.get("type", "monomer")
        primary_metric = pinfo.get("primary_metric", "bb_lddt")

        # Group by team and keep best primary_metric score per team
        best_by_team: dict[str, dict] = {}
        for entry in entries:
            participant_id = entry["participant_id"]
            submitted_at = entry.get("submitted_at", "")
            team = extract_team_name(participant_id, submitted_at)

            # Get the configured primary metric value
            score = get_metric_value(entry, primary_metric, ptype)

            if score is None:
                continue

            if team not in best_by_team or score > (best_by_team[team].get("score") or 0):
                best_by_team[team] = {
                    "team": team,
                    "participant_id": participant_id,
                    "token": entry["token"],
                    "score": score,
                    "problem_id": problem_id,
                    "metric_name": primary_metric
                }

        # Add best scores to team data
        for team, best in best_by_team.items():
            if team not in team_data:
                team_data[team] = {
                    "team": team,
                    "problems_completed": 0,
                    "problem_scores": {},  # problem_id -> score
                    "problem_tokens": {}   # problem_id -> token (for reference)
                }

            team_data[team]["problems_completed"] += 1
            team_data[team]["problem_scores"][problem_id] = best["score"]
            team_data[team]["problem_tokens"][problem_id] = best["token"]

    # Step 2: Calculate z-scores for each problem
    problem_ids = sorted(problem_info.keys())
    problem_z_scores: dict[str, dict[str, float]] = {pid: {} for pid in problem_ids}

    for problem_id in problem_ids:
        scores = []
        teams_with_scores = []
        for team, data in team_data.items():
            score = data["problem_scores"].get(problem_id)
            if score is not None:
                scores.append(score)
                teams_with_scores.append(team)

        if len(scores) < 2:
            # Not enough data for z-score, use 0 (neutral)
            for team in teams_with_scores:
                problem_z_scores[problem_id][team] = 0.0
            continue

        # Calculate z-scores
        mean = np.mean(scores)
        std = np.std(scores)
        if std == 0:
            std = 1  # Avoid division by zero

        for team in teams_with_scores:
            score = team_data[team]["problem_scores"][problem_id]
            z = (score - mean) / std
            problem_z_scores[problem_id][team] = z

    # Step 3: Calculate overall z-score (average of z-scores across problems)
    for team, data in team_data.items():
        z_scores = []
        for problem_id in problem_ids:
            if problem_id in data["problem_scores"]:
                z = problem_z_scores[problem_id].get(team)
                if z is not None:
                    z_scores.append(z)

        if z_scores:
            data["overall_z_score"] = float(np.mean(z_scores))
        else:
            data["overall_z_score"] = 0.0

        # Store per-problem z-scores for display
        data["problem_z_scores"] = {
            pid: problem_z_scores[pid].get(team)
            for pid in problem_ids if pid in data["problem_scores"]
        }

    # Step 4: Sort by overall z-score (higher is better), with problems_completed as tiebreaker
    overall = sorted(
        team_data.values(),
        key=lambda x: (x["problems_completed"], x["overall_z_score"]),
        reverse=True
    )

    # Add overall ranks
    for i, entry in enumerate(overall):
        entry["rank"] = i + 1

    return overall


def generate_leaderboard(
    problem_results: dict[str, list],
    problem_info: dict,
    output_path: str
) -> dict:
    """Generate the leaderboard data structure."""
    leaderboard = {
        "last_updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "problems": {},
        "overall_rankings": []
    }

    # Generate per-problem rankings
    for problem_id, info in problem_info.items():
        entries = problem_results.get(problem_id, [])

        # Use configurable primary metric for ranking
        primary_metric = info.get("primary_metric", "bb_lddt")
        ptype = info.get("type", "monomer")

        # Re-score entries using the configured primary metric
        for entry in entries:
            entry["primary_score"] = get_metric_value(entry, primary_metric, ptype)
            entry["primary_metric"] = primary_metric

        ranked = rank_entries(entries)

        # Build simplified ranking entries
        rankings = []
        for entry in ranked:
            ranking_entry = {
                "rank": entry["rank"],
                "participant_id": entry["participant_id"],
                "token": entry["token"],
                "submitted_at": entry.get("submitted_at"),
                "primary_score": entry.get("primary_score"),
                "primary_metric": entry.get("primary_metric"),
                "best_seq": entry.get("seq_num")  # Which sequence was chosen as best
            }

            # Add relevant metrics based on problem type
            af3 = entry.get("af3_metrics", {})
            metrics = entry.get("metrics", {})

            if info["type"] == "binder":
                # AF3 metrics
                ranking_entry["iptm"] = af3.get("chain_pair_iptm", [[None]])[0][0] \
                    if af3.get("chain_pair_iptm") else None
                ranking_entry["ptm"] = af3.get("ptm")
                ranking_entry["plddt"] = af3.get("mean_plddt")
                ranking_entry["ranking_score"] = af3.get("ranking_score")
                # Complex metrics (USalign multimer mode)
                ranking_entry["complex_tm"] = metrics.get("complex_tm_score") or metrics.get("tm_score")
                ranking_entry["complex_rmsd"] = metrics.get("complex_rmsd") or metrics.get("rmsd")
                ranking_entry["complex_lddt"] = metrics.get("bb_lddt")
                # Binder-only metrics (chain A vs chain A, TMalign)
                binder_m = entry.get("binder_metrics", {})
                ranking_entry["binder_tm"] = binder_m.get("binder_tm_score")
                ranking_entry["binder_rmsd"] = binder_m.get("binder_rmsd")
                ranking_entry["binder_lddt"] = binder_m.get("binder_lddt")
                # Interface metrics
                interface_m = entry.get("interface_metrics", {})
                ranking_entry["interface_lddt"] = interface_m.get("interface_lddt")
                ranking_entry["interface_contacts"] = interface_m.get("total_interface_contacts")
            else:
                # Monomer metrics
                ranking_entry["bb_lddt"] = metrics.get("bb_lddt")
                ranking_entry["bb_lddt_cov"] = metrics.get("bb_lddt_cov")
                ranking_entry["tm_score"] = metrics.get("tm_score")
                ranking_entry["rmsd"] = metrics.get("rmsd")
                # AF3 metrics
                ranking_entry["ptm"] = af3.get("ptm")
                ranking_entry["plddt"] = af3.get("mean_plddt")
                ranking_entry["ranking_score"] = af3.get("ranking_score")

            rankings.append(ranking_entry)

        leaderboard["problems"][problem_id] = {
            "name": info["name"],
            "type": info["type"],
            "primary_metric": primary_metric,
            "day": info.get("day", 1),
            "hidden": info.get("hidden"),  # None = auto, True = always hide, False = always show
            "rankings": rankings
        }

    # Generate overall rankings
    leaderboard["overall_rankings"] = compute_overall_rankings(problem_results, problem_info)

    # Write output
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(leaderboard, f, indent=2)

    return leaderboard


def main():
    parser = argparse.ArgumentParser(description="Update leaderboard data")
    parser.add_argument("--results-dir", default="docs/results",
                        help="Directory containing result subdirectories")
    parser.add_argument("--config", default="docs/targets/config.json",
                        help="Problem configuration file")
    parser.add_argument("--output", default="docs/leaderboard_data.json",
                        help="Output JSON path")

    args = parser.parse_args()

    # Load config
    config = load_config(args.config)
    problem_info = get_problem_info(config)

    print(f"Loaded {len(problem_info)} problems from config")

    # Scan results
    problem_results = scan_results(args.results_dir, problem_info)

    total_entries = sum(len(entries) for entries in problem_results.values())
    print(f"Found {total_entries} total entries across all problems")

    for pid, entries in problem_results.items():
        print(f"  {pid}: {len(entries)} entries")

    # Generate leaderboard
    leaderboard = generate_leaderboard(problem_results, problem_info, args.output)

    print(f"\nLeaderboard saved to {args.output}")
    print(f"Last updated: {leaderboard['last_updated']}")

    # Print summary
    print("\n=== Overall Rankings (by Team) ===")
    for entry in leaderboard["overall_rankings"][:10]:
        z_score = entry.get('overall_z_score', 0)
        print(f"  #{entry['rank']}: {entry['team']} "
              f"({entry['problems_completed']} problems, "
              f"z-score: {z_score:+.2f})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
