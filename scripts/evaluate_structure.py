#!/usr/bin/env python3
"""
Evaluate predicted protein structures against reference structures.

Uses:
- TMalign/USalign for TM-score and RMSD (standalone binaries)
- USalign with -mm 1 for multimer complex alignment
- Pure Python implementation for lDDT (backbone) and interface lDDT

Usage:
    python evaluate_structure.py --model path/to/model.cif --reference path/to/reference.pdb \
        --problem-id problem_1 --problem-type monomer --output evaluation.json

For binder problems:
    - Complex TM-score: USalign -mm 1 -ter 1 (multimer alignment)
    - Binder-only TM-score: TMalign on extracted chain A
    - Interface lDDT: lDDT computed only for interface residues (within 8A of other chain)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

# Global flag for keeping temp files
KEEP_TEMP_FILES = False
TEMP_OUTPUT_DIR = None
# Persistent storage for converted PDBs (always saved for verification)
CONVERTED_PDB_DIR = None


def parse_pdb_ca_coords(pdb_path: str) -> tuple[np.ndarray, list[str]]:
    """
    Parse CA atom coordinates from PDB file.

    Returns:
        coords: Nx3 array of CA coordinates
        residue_ids: List of residue identifiers (chain_resnum)
    """
    coords = []
    residue_ids = []

    with open(pdb_path) as f:
        for line in f:
            if line.startswith(("ATOM", "HETATM")):
                atom_name = line[12:16].strip()
                if atom_name == "CA":
                    x = float(line[30:38])
                    y = float(line[38:46])
                    z = float(line[46:54])
                    chain = line[21]
                    resnum = line[22:26].strip()
                    coords.append([x, y, z])
                    residue_ids.append(f"{chain}_{resnum}")

    return np.array(coords), residue_ids


def parse_cif_ca_coords(cif_path: str) -> tuple[np.ndarray, list[str]]:
    """
    Parse CA atom coordinates from mmCIF file.

    Returns:
        coords: Nx3 array of CA coordinates
        residue_ids: List of residue identifiers (chain_resnum)
    """
    coords = []
    residue_ids = []

    with open(cif_path) as f:
        in_atom_site = False
        col_indices = {}

        for line in f:
            line = line.strip()

            if line.startswith("_atom_site."):
                in_atom_site = True
                col_name = line.split(".")[1].split()[0]
                col_indices[col_name] = len(col_indices)
                continue

            if in_atom_site and (line.startswith("_") or line.startswith("#") or line == ""):
                in_atom_site = False
                continue

            if in_atom_site and line.startswith(("ATOM", "HETATM")):
                parts = line.split()

                # Get column indices
                atom_col = col_indices.get("label_atom_id", col_indices.get("auth_atom_id", 3))
                x_col = col_indices.get("Cartn_x", 10)
                y_col = col_indices.get("Cartn_y", 11)
                z_col = col_indices.get("Cartn_z", 12)
                chain_col = col_indices.get("label_asym_id", col_indices.get("auth_asym_id", 6))
                resnum_col = col_indices.get("label_seq_id", col_indices.get("auth_seq_id", 8))

                if len(parts) > max(atom_col, x_col, y_col, z_col, chain_col, resnum_col):
                    atom_name = parts[atom_col]
                    if atom_name == "CA":
                        x = float(parts[x_col])
                        y = float(parts[y_col])
                        z = float(parts[z_col])
                        chain = parts[chain_col]
                        resnum = parts[resnum_col]
                        coords.append([x, y, z])
                        residue_ids.append(f"{chain}_{resnum}")

    return np.array(coords), residue_ids


def parse_structure_ca(file_path: str, chain: str = None) -> tuple[np.ndarray, list[str]]:
    """Parse CA coordinates from PDB or CIF file, optionally filtering by chain."""
    if file_path.endswith(".cif"):
        coords, res_ids = parse_cif_ca_coords(file_path)
    else:
        coords, res_ids = parse_pdb_ca_coords(file_path)

    if chain is not None and len(coords) > 0:
        # Filter by chain
        mask = [rid.startswith(f"{chain}_") for rid in res_ids]
        coords = coords[mask]
        res_ids = [r for r, m in zip(res_ids, mask) if m]

    return coords, res_ids


def extract_chain_to_pdb(input_path: str, output_path: str, chain: str) -> bool:
    """Extract a specific chain from PDB/CIF to a new PDB file."""
    try:
        if input_path.endswith(".cif"):
            # Parse CIF and write only the specified chain
            atoms = []
            with open(input_path) as f:
                in_atom_site = False
                col_indices = {}

                for line in f:
                    line_stripped = line.strip()

                    if line_stripped.startswith("_atom_site."):
                        in_atom_site = True
                        col_name = line_stripped.split(".")[1].split()[0]
                        col_indices[col_name] = len(col_indices)
                        continue

                    if in_atom_site and (line_stripped.startswith("_") or
                                          line_stripped.startswith("#") or
                                          line_stripped == "" or
                                          line_stripped.startswith("loop_")):
                        if atoms:
                            break
                        in_atom_site = False
                        continue

                    if in_atom_site and line_stripped.startswith(("ATOM", "HETATM")):
                        parts = line_stripped.split()
                        chain_col = col_indices.get("label_asym_id", 6)
                        if len(parts) > chain_col and parts[chain_col] == chain:
                            atoms.append(parts)

            if not atoms:
                return False

            # Write PDB
            with open(output_path, "w") as f:
                for i, parts in enumerate(atoms):
                    record = parts[0]
                    atom_id = i + 1
                    atom_name = parts[col_indices.get("label_atom_id", 3)]
                    res_name = parts[col_indices.get("label_comp_id", 5)]
                    res_num = parts[col_indices.get("label_seq_id", 8)]
                    x = float(parts[col_indices.get("Cartn_x", 10)])
                    y = float(parts[col_indices.get("Cartn_y", 11)])
                    z = float(parts[col_indices.get("Cartn_z", 12)])
                    element = parts[col_indices.get("type_symbol", 2)] if "type_symbol" in col_indices else atom_name[0]

                    if len(atom_name) < 4:
                        atom_name_fmt = f" {atom_name:<3}"
                    else:
                        atom_name_fmt = atom_name[:4]

                    f.write(f"{record:<6}{atom_id:>5} {atom_name_fmt}{res_name:>3} {chain[0]}{int(res_num):>4}    {x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00  0.00          {element:>2}\n")
                f.write("END\n")
            return True
        else:
            # Parse PDB and filter by chain
            with open(input_path) as f_in, open(output_path, "w") as f_out:
                for line in f_in:
                    if line.startswith(("ATOM", "HETATM")):
                        if line[21] == chain:
                            f_out.write(line)
                    elif line.startswith("END"):
                        f_out.write(line)
            return True
    except Exception as e:
        print(f"Chain extraction failed: {e}", file=sys.stderr)
        return False


def cif_to_pdb(cif_path: str, pdb_path: str) -> bool:
    """
    Convert CIF to PDB format for TMalign compatibility.
    Simple conversion focusing on ATOM records.
    """
    try:
        coords, _ = parse_cif_ca_coords(cif_path)

        # Re-read to get all atoms
        with open(cif_path) as f:
            content = f.read()

        # Try using gemmi if available
        try:
            import gemmi
            structure = gemmi.read_structure(cif_path)
            structure.write_pdb(pdb_path)
            return True
        except ImportError:
            pass

        # Fallback: manual conversion
        atoms = []
        with open(cif_path) as f:
            in_atom_site = False
            col_indices = {}

            for line in f:
                line_stripped = line.strip()

                if line_stripped.startswith("_atom_site."):
                    in_atom_site = True
                    col_name = line_stripped.split(".")[1].split()[0]
                    col_indices[col_name] = len(col_indices)
                    continue

                if in_atom_site and (line_stripped.startswith("_") or line_stripped.startswith("#") or line_stripped == "" or line_stripped.startswith("loop_")):
                    if atoms:  # We've collected atoms, stop
                        break
                    in_atom_site = False
                    continue

                if in_atom_site and line_stripped.startswith(("ATOM", "HETATM")):
                    parts = line_stripped.split()
                    atoms.append(parts)

        if not atoms or not col_indices:
            return False

        # Write PDB
        with open(pdb_path, "w") as f:
            for i, parts in enumerate(atoms):
                record = parts[0]
                atom_id = i + 1
                atom_name = parts[col_indices.get("label_atom_id", 3)]
                res_name = parts[col_indices.get("label_comp_id", 5)]
                chain = parts[col_indices.get("label_asym_id", 6)]
                res_num = parts[col_indices.get("label_seq_id", 8)]
                x = float(parts[col_indices.get("Cartn_x", 10)])
                y = float(parts[col_indices.get("Cartn_y", 11)])
                z = float(parts[col_indices.get("Cartn_z", 12)])
                element = parts[col_indices.get("type_symbol", 2)] if "type_symbol" in col_indices else atom_name[0]

                # Format atom name (4 chars, right-justified for 1-char elements)
                if len(atom_name) < 4:
                    atom_name_fmt = f" {atom_name:<3}"
                else:
                    atom_name_fmt = atom_name[:4]

                f.write(f"{record:<6}{atom_id:>5} {atom_name_fmt}{res_name:>3} {chain[0]}{int(res_num):>4}    {x:>8.3f}{y:>8.3f}{z:>8.3f}  1.00  0.00          {element:>2}\n")
            f.write("END\n")

        return True
    except Exception as e:
        print(f"CIF to PDB conversion failed: {e}", file=sys.stderr)
        return False


def maybe_keep_temp(temp_path: str, label: str) -> str:
    """Optionally preserve temp file for inspection."""
    global KEEP_TEMP_FILES, TEMP_OUTPUT_DIR
    if KEEP_TEMP_FILES and TEMP_OUTPUT_DIR and os.path.exists(temp_path):
        dest = os.path.join(TEMP_OUTPUT_DIR, f"{label}_{os.path.basename(temp_path)}")
        shutil.copy2(temp_path, dest)
        print(f"  Saved temp file: {dest}")
        return dest
    return temp_path


def save_converted_pdb(temp_path: str, label: str, problem_id: str, participant_id: str) -> str:
    """Save converted PDB to persistent storage for verification."""
    global CONVERTED_PDB_DIR
    if CONVERTED_PDB_DIR and os.path.exists(temp_path):
        os.makedirs(CONVERTED_PDB_DIR, exist_ok=True)
        filename = f"{participant_id}_{problem_id}_{label}.pdb"
        dest = os.path.join(CONVERTED_PDB_DIR, filename)
        shutil.copy2(temp_path, dest)
        print(f"  Saved converted PDB: {dest}")
        return dest
    return temp_path


def parse_tmalign_alignment(output: str) -> list[tuple[int, int]]:
    """
    Parse TMalign/USalign output to extract aligned residue pairs.

    Returns list of (model_idx, ref_idx) tuples for aligned residues.
    Indices are 0-based.
    """
    lines = output.split("\n")
    alignment_lines = []

    # Find the alignment block (3 consecutive lines with sequence/alignment)
    for i, line in enumerate(lines):
        # Look for the alignment marker line (contains : and/or .)
        if line and all(c in ' :.X-ACDEFGHIKLMNPQRSTVWY' for c in line):
            # Check if this looks like an alignment block
            if i > 0 and i < len(lines) - 1:
                prev_line = lines[i - 1]
                next_line = lines[i + 1]
                # The alignment block has sequence chars and gaps
                if (any(c in 'ACDEFGHIKLMNPQRSTVWYX' for c in prev_line) and
                    any(c in 'ACDEFGHIKLMNPQRSTVWYX-' for c in next_line)):
                    alignment_lines = [prev_line, line, next_line]
                    break

    if len(alignment_lines) != 3:
        return []

    seq1 = alignment_lines[0]  # Model sequence
    seq2 = alignment_lines[2]  # Reference sequence

    # Parse alignment to get corresponding residue indices
    aligned_pairs = []
    model_idx = 0
    ref_idx = 0

    # Align the sequences by position
    max_len = max(len(seq1), len(seq2))
    seq1 = seq1.ljust(max_len)
    seq2 = seq2.ljust(max_len)

    for i in range(max_len):
        c1 = seq1[i] if i < len(seq1) else ' '
        c2 = seq2[i] if i < len(seq2) else ' '

        has_model = c1 not in ' -'
        has_ref = c2 not in ' -'

        if has_model and has_ref:
            # Both have residues at this position - aligned pair
            aligned_pairs.append((model_idx, ref_idx))

        if has_model:
            model_idx += 1
        if has_ref:
            ref_idx += 1

    return aligned_pairs


def run_tmalign(model_path: str, reference_path: str, multimer: bool = False,
                return_alignment: bool = False) -> dict:
    """
    Run TMalign/USalign to compute TM-score and RMSD.

    Args:
        model_path: Path to model structure
        reference_path: Path to reference structure
        multimer: If True, use USalign with -mm 1 -ter 1 for multimer alignment
        return_alignment: If True, also return aligned residue pairs

    Returns dict with tm_score, rmsd, aligned_length, seq_identity, and optionally alignment
    """
    result = {
        "tm_score": None,
        "tm_score_ref": None,
        "rmsd": None,
        "aligned_length": None,
        "seq_identity": None,
        "aligned_pairs": None
    }

    # Convert CIF to PDB if needed
    temp_files = []

    try:
        if model_path.endswith(".cif"):
            model_pdb = tempfile.NamedTemporaryFile(suffix=".pdb", delete=False)
            temp_files.append(model_pdb.name)
            model_pdb.close()
            if not cif_to_pdb(model_path, model_pdb.name):
                return {"error": "Failed to convert model CIF to PDB"}
            maybe_keep_temp(model_pdb.name, "model_converted")
            model_path = model_pdb.name

        if reference_path.endswith(".cif"):
            ref_pdb = tempfile.NamedTemporaryFile(suffix=".pdb", delete=False)
            temp_files.append(ref_pdb.name)
            ref_pdb.close()
            if not cif_to_pdb(reference_path, ref_pdb.name):
                return {"error": "Failed to convert reference CIF to PDB"}
            maybe_keep_temp(ref_pdb.name, "reference_converted")
            reference_path = ref_pdb.name

        # Build command based on mode
        if multimer:
            # Use USalign with multimer mode for complex alignment
            cmd_options = [
                (["/applic/bin/USalign", model_path, reference_path, "-mm", "1", "-ter", "1"], "USalign multimer"),
                (["USalign", model_path, reference_path, "-mm", "1", "-ter", "1"], "USalign multimer (PATH)"),
            ]
        else:
            # Standard monomer alignment
            cmd_options = [
                (["/applic/bin/USalign", model_path, reference_path], "USalign"),
                (["/applic/bin/TMalign", model_path, reference_path], "TMalign"),
                (["USalign", model_path, reference_path], "USalign (PATH)"),
                (["TMalign", model_path, reference_path], "TMalign (PATH)"),
            ]

        proc = None
        for cmd, desc in cmd_options:
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if proc.returncode == 0:
                    break
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        if proc is None or proc.returncode != 0:
            return {"error": "TMalign/USalign not found or failed"}

        # Parse output
        for line in proc.stdout.split("\n"):
            line = line.strip()

            if line.startswith("Aligned length="):
                # Aligned length= 123, RMSD= 1.23, Seq_ID=n_identical/n_aligned= 0.456
                parts = line.split(",")
                for part in parts:
                    part = part.strip()
                    if part.startswith("Aligned length="):
                        result["aligned_length"] = int(part.split("=")[1].strip())
                    elif part.startswith("RMSD="):
                        result["rmsd"] = float(part.split("=")[1].strip())
                    elif "Seq_ID" in part and "=" in part:
                        # Get the last number after =
                        val = part.split("=")[-1].strip()
                        try:
                            result["seq_identity"] = float(val)
                        except ValueError:
                            pass

            elif line.startswith("TM-score="):
                # TM-score= 0.12345 (normalized by length of Chain_1)
                parts = line.split()
                if len(parts) >= 2:
                    tm = float(parts[1])
                    if "Chain_1" in line or "first" in line.lower():
                        result["tm_score"] = tm
                    elif "Chain_2" in line or "second" in line.lower():
                        result["tm_score_ref"] = tm
                    elif result["tm_score"] is None:
                        result["tm_score"] = tm

        # Parse alignment if requested
        if return_alignment:
            result["aligned_pairs"] = parse_tmalign_alignment(proc.stdout)

        return result

    finally:
        if not KEEP_TEMP_FILES:
            for f in temp_files:
                if os.path.exists(f):
                    os.unlink(f)


def compute_lddt(model_coords: np.ndarray, ref_coords: np.ndarray,
                 cutoff: float = 15.0, thresholds: tuple = (0.5, 1.0, 2.0, 4.0),
                 aligned_pairs: list[tuple[int, int]] = None) -> float:
    """
    Compute lDDT (Local Distance Difference Test) score.

    This is a backbone-only lDDT using CA atoms.

    Args:
        model_coords: Nx3 array of model CA coordinates
        ref_coords: Mx3 array of reference CA coordinates
        cutoff: Distance cutoff for considering residue pairs (default 15A)
        thresholds: Distance difference thresholds (default 0.5, 1, 2, 4 A)
        aligned_pairs: List of (model_idx, ref_idx) tuples from TMalign alignment.
                      If provided, uses these pairs for lDDT calculation.
                      If None, falls back to simple index-based comparison.

    Returns:
        lDDT score between 0 and 1
    """
    if aligned_pairs is not None and len(aligned_pairs) > 0:
        # Use TMalign alignment for proper residue correspondence
        n_aligned = len(aligned_pairs)
        if n_aligned < 2:
            return 0.0

        # Extract aligned coordinates
        model_indices = [p[0] for p in aligned_pairs]
        ref_indices = [p[1] for p in aligned_pairs]

        # Validate indices
        if max(model_indices) >= len(model_coords) or max(ref_indices) >= len(ref_coords):
            print(f"  Warning: Alignment indices out of bounds, falling back to simple comparison")
            aligned_pairs = None
        else:
            aligned_model_coords = model_coords[model_indices]
            aligned_ref_coords = ref_coords[ref_indices]

            # Compute lDDT on aligned coordinates
            return _compute_lddt_core(aligned_model_coords, aligned_ref_coords, cutoff, thresholds)

    # Fallback: simple index-based comparison (truncate to min length)
    if len(model_coords) != len(ref_coords):
        min_len = min(len(model_coords), len(ref_coords))
        model_coords = model_coords[:min_len]
        ref_coords = ref_coords[:min_len]

    return _compute_lddt_core(model_coords, ref_coords, cutoff, thresholds)


def compute_global_rmsd(model_coords: np.ndarray, ref_coords: np.ndarray,
                        aligned_pairs: list[tuple[int, int]] = None) -> dict:
    """
    Compute global RMSD (on all residues) after superposition using aligned residues.

    This differs from TMalign's RMSD which is only on aligned residues.
    Here we:
    1. Use aligned residues to compute the optimal rotation/translation
    2. Apply that transformation to the model
    3. Compute RMSD on all residues (not just aligned ones)

    Args:
        model_coords: Nx3 array of model CA coordinates
        ref_coords: Mx3 array of reference CA coordinates
        aligned_pairs: List of (model_idx, ref_idx) tuples from alignment

    Returns:
        dict with global_rmsd, aligned_rmsd, transformation info
    """
    result = {
        "global_rmsd": None,
        "aligned_rmsd": None,
        "n_model": len(model_coords),
        "n_ref": len(ref_coords),
        "n_aligned": 0
    }

    if len(model_coords) == 0 or len(ref_coords) == 0:
        return result

    # Determine aligned coordinates for superposition
    if aligned_pairs is not None and len(aligned_pairs) > 1:
        model_indices = [p[0] for p in aligned_pairs]
        ref_indices = [p[1] for p in aligned_pairs]

        # Validate indices
        if max(model_indices) >= len(model_coords) or max(ref_indices) >= len(ref_coords):
            aligned_pairs = None
        else:
            aligned_model = model_coords[model_indices]
            aligned_ref = ref_coords[ref_indices]
            result["n_aligned"] = len(aligned_pairs)
    
    if aligned_pairs is None or len(aligned_pairs) < 2:
        # Fallback: use min length for simple alignment
        min_len = min(len(model_coords), len(ref_coords))
        aligned_model = model_coords[:min_len]
        aligned_ref = ref_coords[:min_len]
        result["n_aligned"] = min_len

    # Compute optimal rotation using Kabsch algorithm
    # Center the structures
    centroid_model = np.mean(aligned_model, axis=0)
    centroid_ref = np.mean(aligned_ref, axis=0)

    centered_model = aligned_model - centroid_model
    centered_ref = aligned_ref - centroid_ref

    # Compute covariance matrix and SVD
    H = centered_model.T @ centered_ref
    U, S, Vt = np.linalg.svd(H)

    # Compute rotation matrix
    R = Vt.T @ U.T

    # Handle reflection case
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T

    # Apply transformation to all model coordinates
    transformed_model = (model_coords - centroid_model) @ R.T + centroid_ref

    # Compute aligned RMSD (after Kabsch superposition, on aligned residues only)
    if aligned_pairs is not None and len(aligned_pairs) > 1:
        transformed_aligned = transformed_model[model_indices]
        diff_aligned = transformed_aligned - ref_coords[ref_indices]
    else:
        min_len = min(len(transformed_model), len(ref_coords))
        diff_aligned = transformed_model[:min_len] - ref_coords[:min_len]
    
    aligned_rmsd = np.sqrt(np.mean(np.sum(diff_aligned ** 2, axis=1)))
    result["aligned_rmsd"] = round(float(aligned_rmsd), 3)

    # For global RMSD, compute RMSD on ALL residues (not just aligned)
    # Always use min length for global RMSD calculation
    min_len = min(len(transformed_model), len(ref_coords))
    diff_global = transformed_model[:min_len] - ref_coords[:min_len]
    global_rmsd = np.sqrt(np.mean(np.sum(diff_global ** 2, axis=1)))

    result["global_rmsd"] = round(float(global_rmsd), 3)

    return result


def _compute_lddt_core(model_coords: np.ndarray, ref_coords: np.ndarray,
                       cutoff: float = 15.0, thresholds: tuple = (0.5, 1.0, 2.0, 4.0)) -> float:
    """Core lDDT computation on aligned coordinates."""
    n_residues = len(ref_coords)
    if n_residues < 2:
        return 0.0

    # Compute distance matrices
    def pairwise_distances(coords):
        diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
        return np.sqrt(np.sum(diff ** 2, axis=-1))

    ref_dists = pairwise_distances(ref_coords)
    model_dists = pairwise_distances(model_coords)

    # Find pairs within cutoff in reference (excluding self and immediate neighbors)
    mask = (ref_dists < cutoff) & (ref_dists > 0)
    # Exclude immediate sequence neighbors (i, i+1)
    for i in range(n_residues - 1):
        mask[i, i + 1] = False
        mask[i + 1, i] = False

    if not np.any(mask):
        return 0.0

    # Compute distance differences for valid pairs
    ref_valid = ref_dists[mask]
    model_valid = model_dists[mask]

    diff = np.abs(model_valid - ref_valid)

    # Count preserved distances for each threshold
    preserved = sum(np.mean(diff < t) for t in thresholds) / len(thresholds)

    return float(preserved)


def compute_lddt_per_residue(model_coords: np.ndarray, ref_coords: np.ndarray,
                              cutoff: float = 15.0, thresholds: tuple = (0.5, 1.0, 2.0, 4.0)) -> np.ndarray:
    """
    Compute per-residue lDDT scores.

    Returns array of per-residue lDDT scores.
    """
    if len(model_coords) != len(ref_coords):
        min_len = min(len(model_coords), len(ref_coords))
        model_coords = model_coords[:min_len]
        ref_coords = ref_coords[:min_len]

    n_residues = len(ref_coords)
    if n_residues < 2:
        return np.zeros(n_residues)

    # Compute distance matrices
    def pairwise_distances(coords):
        diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
        return np.sqrt(np.sum(diff ** 2, axis=-1))

    ref_dists = pairwise_distances(ref_coords)
    model_dists = pairwise_distances(model_coords)

    per_residue_lddt = np.zeros(n_residues)

    for i in range(n_residues):
        # Find neighbors within cutoff (excluding self and immediate neighbor)
        neighbors = (ref_dists[i] < cutoff) & (ref_dists[i] > 0)
        if i > 0:
            neighbors[i - 1] = False
        if i < n_residues - 1:
            neighbors[i + 1] = False

        if not np.any(neighbors):
            per_residue_lddt[i] = 0.0
            continue

        ref_neighbor_dists = ref_dists[i, neighbors]
        model_neighbor_dists = model_dists[i, neighbors]

        diff = np.abs(model_neighbor_dists - ref_neighbor_dists)
        preserved = sum(np.mean(diff < t) for t in thresholds) / len(thresholds)
        per_residue_lddt[i] = preserved

    return per_residue_lddt


def identify_interface_residues(coords_a: np.ndarray, coords_b: np.ndarray,
                                 interface_cutoff: float = 8.0) -> tuple[np.ndarray, np.ndarray]:
    """
    Identify interface residues between two chains.

    Args:
        coords_a: Nx3 array of chain A CA coordinates
        coords_b: Mx3 array of chain B CA coordinates
        interface_cutoff: Distance cutoff to define interface (default 8A)

    Returns:
        mask_a: Boolean array indicating interface residues in chain A
        mask_b: Boolean array indicating interface residues in chain B
    """
    if len(coords_a) == 0 or len(coords_b) == 0:
        return np.array([], dtype=bool), np.array([], dtype=bool)

    # Compute cross-chain distances
    diff = coords_a[:, np.newaxis, :] - coords_b[np.newaxis, :, :]
    distances = np.sqrt(np.sum(diff ** 2, axis=-1))  # Shape: (N, M)

    # Interface residues are those within cutoff of any residue in other chain
    mask_a = np.any(distances < interface_cutoff, axis=1)
    mask_b = np.any(distances < interface_cutoff, axis=0)

    return mask_a, mask_b


def compute_interface_lddt(model_coords_a: np.ndarray, model_coords_b: np.ndarray,
                           ref_coords_a: np.ndarray, ref_coords_b: np.ndarray,
                           interface_cutoff: float = 8.0,
                           lddt_cutoff: float = 15.0,
                           thresholds: tuple = (0.5, 1.0, 2.0, 4.0),
                           aligned_pairs_a: list[tuple[int, int]] | None = None,
                           aligned_pairs_b: list[tuple[int, int]] | None = None) -> dict:
    """
    Compute interface lDDT (iLDDT) between two chains.

    Interface residues are identified based on the reference structure.
    lDDT is computed for interface residues considering cross-chain contacts.

    Args:
        model_coords_a: Model chain A CA coordinates
        model_coords_b: Model chain B CA coordinates
        ref_coords_a: Reference chain A CA coordinates
        ref_coords_b: Reference chain B CA coordinates
        interface_cutoff: Distance cutoff to define interface residues (default 8A)
        lddt_cutoff: Distance cutoff for lDDT calculation (default 15A)
        thresholds: Distance difference thresholds for lDDT
        aligned_pairs_a: List of (model_idx, ref_idx) for chain A alignment (for length mismatch)
        aligned_pairs_b: List of (model_idx, ref_idx) for chain B alignment (for length mismatch)

    Returns:
        dict with interface_lddt, interface_residue_counts, etc.
    """
    result = {
        "interface_lddt": None,
        "interface_lddt_a": None,
        "interface_lddt_b": None,
        "interface_count_a": 0,
        "interface_count_b": 0,
        "total_interface_contacts": 0
    }

    if len(ref_coords_a) == 0 or len(ref_coords_b) == 0:
        result["error"] = "Empty chain coordinates"
        return result

    # Handle length mismatch using alignments
    length_mismatch = (len(model_coords_a) != len(ref_coords_a) or
                       len(model_coords_b) != len(ref_coords_b))

    if length_mismatch:
        if aligned_pairs_a is None or aligned_pairs_b is None:
            result["error"] = "Chain length mismatch and no alignment provided"
            return result

        # Build index mappings from alignment
        # model_to_ref_a[model_idx] = ref_idx (or -1 if not aligned)
        model_to_ref_a = {m: r for m, r in aligned_pairs_a}
        model_to_ref_b = {m: r for m, r in aligned_pairs_b}
        ref_to_model_a = {r: m for m, r in aligned_pairs_a}
        ref_to_model_b = {r: m for m, r in aligned_pairs_b}

        # Identify interface residues in reference
        interface_a, interface_b = identify_interface_residues(ref_coords_a, ref_coords_b, interface_cutoff)

        result["interface_count_a"] = int(np.sum(interface_a))
        result["interface_count_b"] = int(np.sum(interface_b))

        if result["interface_count_a"] == 0 and result["interface_count_b"] == 0:
            result["error"] = "No interface residues found"
            return result

        # Compute interface lDDT using aligned residues only
        total_preserved = 0
        total_contacts = 0

        # For chain A interface residues (in reference)
        for ref_i in np.where(interface_a)[0]:
            if ref_i not in ref_to_model_a:
                continue  # This reference residue has no aligned model residue
            model_i = ref_to_model_a[ref_i]

            # Find cross-chain contacts in reference
            for ref_j in range(len(ref_coords_b)):
                if ref_j not in ref_to_model_b:
                    continue  # This reference residue has no aligned model residue
                model_j = ref_to_model_b[ref_j]

                ref_dist = np.linalg.norm(ref_coords_a[ref_i] - ref_coords_b[ref_j])
                if ref_dist < lddt_cutoff:
                    model_dist = np.linalg.norm(model_coords_a[model_i] - model_coords_b[model_j])
                    diff = abs(model_dist - ref_dist)

                    preserved = sum(1 for t in thresholds if diff < t) / len(thresholds)
                    total_preserved += preserved
                    total_contacts += 1

        # For chain B interface residues (avoid double counting)
        for ref_j in np.where(interface_b)[0]:
            if ref_j not in ref_to_model_b:
                continue
            model_j = ref_to_model_b[ref_j]

            for ref_i in range(len(ref_coords_a)):
                if interface_a[ref_i]:
                    continue  # Already counted above
                if ref_i not in ref_to_model_a:
                    continue
                model_i = ref_to_model_a[ref_i]

                ref_dist = np.linalg.norm(ref_coords_a[ref_i] - ref_coords_b[ref_j])
                if ref_dist < lddt_cutoff:
                    model_dist = np.linalg.norm(model_coords_a[model_i] - model_coords_b[model_j])
                    diff = abs(model_dist - ref_dist)

                    preserved = sum(1 for t in thresholds if diff < t) / len(thresholds)
                    total_preserved += preserved
                    total_contacts += 1

        result["total_interface_contacts"] = total_contacts

        if total_contacts > 0:
            result["interface_lddt"] = round(total_preserved / total_contacts, 4)
        else:
            result["interface_lddt"] = 0.0

        return result

    # Original logic for matching lengths
    # Identify interface residues in reference
    interface_a, interface_b = identify_interface_residues(ref_coords_a, ref_coords_b, interface_cutoff)

    result["interface_count_a"] = int(np.sum(interface_a))
    result["interface_count_b"] = int(np.sum(interface_b))

    if result["interface_count_a"] == 0 and result["interface_count_b"] == 0:
        result["error"] = "No interface residues found"
        return result

    # Combine all coordinates for distance calculations
    n_a, n_b = len(ref_coords_a), len(ref_coords_b)
    ref_all = np.vstack([ref_coords_a, ref_coords_b])
    model_all = np.vstack([model_coords_a, model_coords_b])

    # Compute full distance matrices
    def pairwise_distances(coords):
        diff = coords[:, np.newaxis, :] - coords[np.newaxis, :, :]
        return np.sqrt(np.sum(diff ** 2, axis=-1))

    ref_dists = pairwise_distances(ref_all)
    model_dists = pairwise_distances(model_all)

    # Compute interface lDDT: for interface residues, count preserved cross-chain contacts
    total_preserved = 0
    total_contacts = 0

    # For chain A interface residues
    for i in np.where(interface_a)[0]:
        # Find cross-chain contacts in reference (residues in chain B within lddt_cutoff)
        for j in range(n_a, n_a + n_b):
            if ref_dists[i, j] < lddt_cutoff:
                ref_dist = ref_dists[i, j]
                model_dist = model_dists[i, j]
                diff = abs(model_dist - ref_dist)

                # Count preserved at each threshold
                preserved = sum(1 for t in thresholds if diff < t) / len(thresholds)
                total_preserved += preserved
                total_contacts += 1

    # For chain B interface residues
    for j in np.where(interface_b)[0]:
        j_idx = n_a + j
        # Find cross-chain contacts in reference (residues in chain A within lddt_cutoff)
        for i in range(n_a):
            # Avoid double counting - only count if this pair wasn't counted above
            if not interface_a[i]:  # Only count if i is not an interface residue
                if ref_dists[i, j_idx] < lddt_cutoff:
                    ref_dist = ref_dists[i, j_idx]
                    model_dist = model_dists[i, j_idx]
                    diff = abs(model_dist - ref_dist)

                    preserved = sum(1 for t in thresholds if diff < t) / len(thresholds)
                    total_preserved += preserved
                    total_contacts += 1

    result["total_interface_contacts"] = total_contacts

    if total_contacts > 0:
        result["interface_lddt"] = round(total_preserved / total_contacts, 4)
    else:
        result["interface_lddt"] = 0.0

    return result


def get_af3_metrics(result_dir: str, problem_id: str, participant_id: str,
                    seq_id: str = None) -> dict:
    """
    Extract AF3 confidence metrics from summary_confidences.json and confidences.json.

    Args:
        result_dir: Directory containing AF3 result files
        problem_id: Problem ID (e.g., problem_5)
        participant_id: Participant ID
        seq_id: Optional sequence ID (e.g., seq1, seq2) for multi-sequence submissions
    """
    result = {}

    # Build pattern with optional seq_id
    if seq_id:
        base_pattern = f"{participant_id}_{problem_id}_{seq_id}"
    else:
        base_pattern = f"{participant_id}_{problem_id}"

    # First try summary_confidences.json
    patterns = [
        f"{base_pattern}_summary_confidences.json",
        f"*_{problem_id}_{seq_id}_summary_confidences.json" if seq_id else f"*_{problem_id}_summary_confidences.json",
        f"*{problem_id}*_summary_confidences.json"
    ]

    for pattern in patterns:
        for f in Path(result_dir).glob(pattern):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    result = {
                        "ptm": data.get("ptm"),
                        "iptm": data.get("iptm"),
                        "ranking_score": data.get("ranking_score"),
                        "chain_pair_iptm": data.get("chain_pair_iptm"),
                        "fraction_disordered": data.get("fraction_disordered")
                    }
                    break
            except Exception:
                continue
        if result:
            break

    # Try to get mean pLDDT from full confidences.json
    plddt_patterns = [
        f"{base_pattern}_confidences.json",
        f"*_{problem_id}_{seq_id}_confidences.json" if seq_id else f"*_{problem_id}_confidences.json",
        f"*{problem_id}*_confidences.json"
    ]

    for pattern in plddt_patterns:
        for f in Path(result_dir).glob(pattern):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    atom_plddts = data.get("atom_plddts")
                    if atom_plddts and len(atom_plddts) > 0:
                        result["mean_plddt"] = round(sum(atom_plddts) / len(atom_plddts), 2)
                    break
            except Exception:
                continue
        if result.get("mean_plddt") is not None:
            break

    return result


def main():
    global KEEP_TEMP_FILES, TEMP_OUTPUT_DIR

    parser = argparse.ArgumentParser(description="Evaluate protein structure predictions")
    parser.add_argument("--model", required=True, help="Path to predicted model (CIF/PDB)")
    parser.add_argument("--reference", required=True, help="Path to reference structure (PDB)")
    parser.add_argument("--problem-id", required=True, help="Problem ID (e.g., problem_1)")
    parser.add_argument("--problem-type", default="monomer", choices=["monomer", "binder"],
                        help="Problem type")
    parser.add_argument("--participant-id", required=True, help="Participant ID")
    parser.add_argument("--token", required=True, help="Result token")
    parser.add_argument("--result-dir", help="Directory containing AF3 result files")
    parser.add_argument("--seq-id", help="Sequence ID (e.g., seq1, seq2) for multi-sequence submissions")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--keep-temp", action="store_true",
                        help="Keep temporary PDB files for manual inspection")
    parser.add_argument("--temp-dir", help="Directory to save temp files (requires --keep-temp)")
    parser.add_argument("--save-converted-pdbs", help="Directory to save converted PDB files for verification")

    args = parser.parse_args()

    # Set up temp file handling and persistent storage for converted PDBs
    if args.save_converted_pdbs:
        # When saving converted PDBs, also enable keep_temp
        KEEP_TEMP_FILES = True
        TEMP_OUTPUT_DIR = args.save_converted_pdbs
        os.makedirs(TEMP_OUTPUT_DIR, exist_ok=True)
        print(f"Converted PDBs will be saved to: {TEMP_OUTPUT_DIR}")
    elif args.keep_temp:
        KEEP_TEMP_FILES = True
        if args.temp_dir:
            TEMP_OUTPUT_DIR = args.temp_dir
        else:
            TEMP_OUTPUT_DIR = os.path.dirname(args.output) or "."
        os.makedirs(TEMP_OUTPUT_DIR, exist_ok=True)
        print(f"Temp files will be saved to: {TEMP_OUTPUT_DIR}")

    # Initialize result
    result = {
        "problem_id": args.problem_id,
        "problem_type": args.problem_type,
        "participant_id": args.participant_id,
        "token": args.token,
        "model_file": os.path.basename(args.model),
        "reference_file": os.path.basename(args.reference),
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "metrics": {},
        "af3_metrics": {}
    }

    # Get AF3 metrics
    if args.result_dir:
        result["af3_metrics"] = get_af3_metrics(
            args.result_dir, args.problem_id, args.participant_id, args.seq_id
        )

    # Run TMalign for TM-score, RMSD, and alignment
    print(f"Running TMalign on {args.model} vs {args.reference}...")
    tm_result = run_tmalign(args.model, args.reference, return_alignment=True)

    aligned_pairs = None
    if "error" not in tm_result:
        result["metrics"]["tm_score"] = tm_result.get("tm_score")
        result["metrics"]["tm_score_ref"] = tm_result.get("tm_score_ref")
        result["metrics"]["rmsd"] = tm_result.get("rmsd")
        result["metrics"]["aligned_length"] = tm_result.get("aligned_length")
        result["metrics"]["seq_identity"] = tm_result.get("seq_identity")
        aligned_pairs = tm_result.get("aligned_pairs")
        if aligned_pairs:
            print(f"  Got {len(aligned_pairs)} aligned residue pairs from TMalign")
    else:
        print(f"TMalign error: {tm_result['error']}", file=sys.stderr)
        result["metrics"]["tm_error"] = tm_result["error"]

    # Compute lDDT using TMalign alignment
    print("Computing backbone lDDT...")
    try:
        model_coords, model_res = parse_structure_ca(args.model)
        ref_coords, ref_res = parse_structure_ca(args.reference)

        if len(model_coords) > 0 and len(ref_coords) > 0:
            lddt_score = compute_lddt(model_coords, ref_coords, aligned_pairs=aligned_pairs)
            result["metrics"]["bb_lddt"] = round(lddt_score, 4)
            result["metrics"]["model_ca_count"] = len(model_coords)
            result["metrics"]["ref_ca_count"] = len(ref_coords)
            if aligned_pairs:
                result["metrics"]["lddt_aligned_count"] = len(aligned_pairs)
                # Coverage-weighted lDDT: penalize for unaligned residues
                coverage = len(aligned_pairs) / len(ref_coords)
                cov_lddt = lddt_score * coverage
                result["metrics"]["bb_lddt_cov"] = round(cov_lddt, 4)
                result["metrics"]["coverage"] = round(coverage, 4)
                print(f"  bb-lDDT: {lddt_score:.4f} (model: {len(model_coords)} CA, ref: {len(ref_coords)} CA)")
                print(f"  bb-lDDT (coverage-weighted): {cov_lddt:.4f} (coverage: {coverage:.2%})")
            else:
                print(f"  bb-lDDT: {lddt_score:.4f} (model: {len(model_coords)} CA, ref: {len(ref_coords)} CA)")

            # Compute global RMSD (all residues after superposition)
            print("Computing RMSD (all residues, Kabsch)...")
            global_rmsd_result = compute_global_rmsd(model_coords, ref_coords, aligned_pairs)
            if global_rmsd_result["global_rmsd"] is not None:
                result["metrics"]["global_rmsd"] = global_rmsd_result["global_rmsd"]
                result["metrics"]["kabsch_aligned_rmsd"] = global_rmsd_result["aligned_rmsd"]
                print(f"  RMSD (all residues, Kabsch): {global_rmsd_result['global_rmsd']:.3f} Å")
                print(f"  RMSD (aligned residues): {global_rmsd_result['aligned_rmsd']:.3f} Å")
        else:
            result["metrics"]["lddt_error"] = "Could not extract CA coordinates"
    except Exception as e:
        print(f"lDDT error: {e}", file=sys.stderr)
        result["metrics"]["lddt_error"] = str(e)

    # For binder problems, compute additional metrics
    if args.problem_type == "binder":
        result["binder_metrics"] = {}
        result["interface_metrics"] = {}

        # 1. Complex TM-score using USalign multimer mode
        print("\nComputing complex TM-score (USalign multimer mode)...")
        complex_tm = run_tmalign(args.model, args.reference, multimer=True)
        if "error" not in complex_tm:
            result["metrics"]["complex_tm_score"] = complex_tm.get("tm_score")
            result["metrics"]["complex_tm_score_ref"] = complex_tm.get("tm_score_ref")
            result["metrics"]["complex_rmsd"] = complex_tm.get("rmsd")
            result["metrics"]["complex_aligned_length"] = complex_tm.get("aligned_length")
            print(f"  Complex TM-score: {complex_tm.get('tm_score')}")
            print(f"  Complex RMSD: {complex_tm.get('rmsd')}")
        else:
            print(f"  Complex TM-score error: {complex_tm.get('error')}")

        # 2. Binder-only metrics (chain A vs chain A) using TMalign
        print("\nComputing binder-only metrics (chain A vs chain A, TMalign)...")
        binder_aligned_pairs = None  # Initialize for use in interface lDDT
        try:
            # Extract chain A from model and reference
            model_chain_a = tempfile.NamedTemporaryFile(suffix=".pdb", delete=False)
            ref_chain_a = tempfile.NamedTemporaryFile(suffix=".pdb", delete=False)
            model_chain_a.close()
            ref_chain_a.close()

            model_extracted = extract_chain_to_pdb(args.model, model_chain_a.name, "A")
            ref_extracted = extract_chain_to_pdb(args.reference, ref_chain_a.name, "A")

            if model_extracted and ref_extracted:
                maybe_keep_temp(model_chain_a.name, "binder_model_chainA")
                maybe_keep_temp(ref_chain_a.name, "binder_ref_chainA")

                # TMalign on binder chain only (monomer mode) with alignment
                binder_tm = run_tmalign(model_chain_a.name, ref_chain_a.name,
                                        multimer=False, return_alignment=True)
                binder_aligned_pairs = None
                if "error" not in binder_tm:
                    result["binder_metrics"]["binder_tm_score"] = binder_tm.get("tm_score")
                    result["binder_metrics"]["binder_rmsd"] = binder_tm.get("rmsd")
                    result["binder_metrics"]["binder_aligned_length"] = binder_tm.get("aligned_length")
                    binder_aligned_pairs = binder_tm.get("aligned_pairs")
                    print(f"  Binder TM-score: {binder_tm.get('tm_score')}")
                    print(f"  Binder Aligned RMSD: {binder_tm.get('rmsd')}")
                else:
                    print(f"  Binder TMalign error: {binder_tm.get('error')}")

                # lDDT on binder chain only using alignment
                model_a_coords, _ = parse_structure_ca(args.model, chain="A")
                ref_a_coords, _ = parse_structure_ca(args.reference, chain="A")

                if len(model_a_coords) > 0 and len(ref_a_coords) > 0:
                    binder_lddt = compute_lddt(model_a_coords, ref_a_coords,
                                               aligned_pairs=binder_aligned_pairs)
                    result["binder_metrics"]["binder_lddt"] = round(binder_lddt, 4)
                    result["binder_metrics"]["binder_model_ca"] = len(model_a_coords)
                    result["binder_metrics"]["binder_ref_ca"] = len(ref_a_coords)
                    print(f"  Binder lDDT: {binder_lddt:.4f}")

                    # Compute coverage-weighted lDDT for binder
                    if binder_aligned_pairs:
                        binder_coverage = len(binder_aligned_pairs) / len(ref_a_coords)
                        binder_lddt_cov = binder_lddt * binder_coverage
                        result["binder_metrics"]["binder_lddt_cov"] = round(binder_lddt_cov, 4)
                        result["binder_metrics"]["binder_coverage"] = round(binder_coverage, 4)
                        result["binder_metrics"]["binder_aligned_count"] = len(binder_aligned_pairs)
                        print(f"  Binder lDDT (coverage-weighted): {binder_lddt_cov:.4f} (coverage: {binder_coverage:.2%})")
            else:
                result["binder_metrics"]["error"] = "Could not extract chain A"
                print("  Warning: Could not extract chain A for binder-only evaluation")

            # Cleanup temp files
            if not KEEP_TEMP_FILES:
                for f in [model_chain_a.name, ref_chain_a.name]:
                    if os.path.exists(f):
                        os.unlink(f)

        except Exception as e:
            print(f"Binder-only evaluation error: {e}", file=sys.stderr)
            result["binder_metrics"]["error"] = str(e)

        # 3. Interface LDDT calculation
        print("\nComputing interface lDDT...")
        try:
            model_a_coords, _ = parse_structure_ca(args.model, chain="A")
            model_b_coords, _ = parse_structure_ca(args.model, chain="B")
            ref_a_coords, _ = parse_structure_ca(args.reference, chain="A")
            ref_b_coords, _ = parse_structure_ca(args.reference, chain="B")

            print(f"  Model: chain A={len(model_a_coords)} CA, chain B={len(model_b_coords)} CA")
            print(f"  Reference: chain A={len(ref_a_coords)} CA, chain B={len(ref_b_coords)} CA")

            # Check for length mismatch
            length_mismatch = (len(model_a_coords) != len(ref_a_coords) or
                               len(model_b_coords) != len(ref_b_coords))

            aligned_pairs_a = binder_aligned_pairs  # From binder TMalign above
            aligned_pairs_b = None

            if length_mismatch:
                print("  Length mismatch detected - using TMalign alignment for chain B...")
                # Get alignment for chain B
                model_chain_b = tempfile.NamedTemporaryFile(suffix=".pdb", delete=False)
                ref_chain_b = tempfile.NamedTemporaryFile(suffix=".pdb", delete=False)
                model_chain_b.close()
                ref_chain_b.close()

                model_b_extracted = extract_chain_to_pdb(args.model, model_chain_b.name, "B")
                ref_b_extracted = extract_chain_to_pdb(args.reference, ref_chain_b.name, "B")

                if model_b_extracted and ref_b_extracted:
                    maybe_keep_temp(model_chain_b.name, "interface_model_chainB")
                    maybe_keep_temp(ref_chain_b.name, "interface_ref_chainB")

                    chain_b_tm = run_tmalign(model_chain_b.name, ref_chain_b.name,
                                             multimer=False, return_alignment=True)
                    if "error" not in chain_b_tm:
                        aligned_pairs_b = chain_b_tm.get("aligned_pairs")
                        print(f"  Chain B alignment: {len(aligned_pairs_b) if aligned_pairs_b else 0} pairs")
                    else:
                        print(f"  Chain B TMalign error: {chain_b_tm.get('error')}")

                # Cleanup temp files
                if not KEEP_TEMP_FILES:
                    for f in [model_chain_b.name, ref_chain_b.name]:
                        if os.path.exists(f):
                            os.unlink(f)

            ilddt_result = compute_interface_lddt(
                model_a_coords, model_b_coords,
                ref_a_coords, ref_b_coords,
                interface_cutoff=8.0,
                aligned_pairs_a=aligned_pairs_a,
                aligned_pairs_b=aligned_pairs_b
            )
            result["interface_metrics"] = ilddt_result
            if ilddt_result.get("interface_lddt") is not None:
                print(f"  Interface lDDT: {ilddt_result['interface_lddt']}")
                print(f"  Interface residues: A={ilddt_result['interface_count_a']}, B={ilddt_result['interface_count_b']}")
                print(f"  Total interface contacts: {ilddt_result['total_interface_contacts']}")
            else:
                print(f"  Interface lDDT error: {ilddt_result.get('error', 'Unknown')}")

        except Exception as e:
            print(f"Interface lDDT error: {e}", file=sys.stderr)
            result["interface_metrics"]["error"] = str(e)

    # Determine primary score based on problem type
    metrics = result.get("metrics", {})
    af3 = result.get("af3_metrics", {})

    if args.problem_type == "binder":
        # For binders, use TM-score (binder_tm or complex_tm) as primary metric
        binder_metrics = result.get("binder_metrics", {})
        if binder_metrics.get("binder_tm_score") is not None:
            result["primary_score"] = binder_metrics["binder_tm_score"]
            result["primary_metric"] = "tm_score"
        elif metrics.get("complex_tm_score") is not None:
            result["primary_score"] = metrics["complex_tm_score"]
            result["primary_metric"] = "tm_score"
        elif metrics.get("tm_score") is not None:
            result["primary_score"] = metrics["tm_score"]
            result["primary_metric"] = "tm_score"
        else:
            # Fall back to iptm if no TM-score available
            chain_pair_iptm = af3.get("chain_pair_iptm")
            max_off_diag = None
            if chain_pair_iptm and isinstance(chain_pair_iptm, list):
                for i, row in enumerate(chain_pair_iptm):
                    if not isinstance(row, list):
                        continue
                    for j, val in enumerate(row):
                        if i == j:
                            continue
                        if val is not None and (max_off_diag is None or val > max_off_diag):
                            max_off_diag = val
            if max_off_diag is not None:
                result["primary_score"] = max_off_diag
                result["primary_metric"] = "iptm"
            elif af3.get("iptm") is not None:
                result["primary_score"] = af3.get("iptm")
                result["primary_metric"] = "iptm"
            else:
                result["primary_score"] = af3.get("ranking_score")
                result["primary_metric"] = "ranking_score"
    else:
        # For monomers, use TM-score as primary (properly normalized by reference length)
        if metrics.get("tm_score") is not None:
            result["primary_score"] = metrics["tm_score"]
            result["primary_metric"] = "tm_score"
        elif metrics.get("bb_lddt") is not None:
            result["primary_score"] = metrics["bb_lddt"]
            result["primary_metric"] = "bb_lddt"
        else:
            result["primary_score"] = af3.get("ptm")
            result["primary_metric"] = "ptm"

    # Write output
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nEvaluation saved to {args.output}")
    print(f"Primary metric: {result.get('primary_metric')} = {result.get('primary_score')}")

    # Print summary
    print("\n=== Metrics Summary ===")
    for k, v in result["metrics"].items():
        if not k.endswith("_error") and not k.endswith("_count"):
            print(f"  {k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
