import json
import shutil
import tarfile
from pathlib import Path

from . import utils


def export_step_dataset(step_name, *, structures_file, work_dir):
    step_src = Path(work_dir) / "restart" / step_name
    olp_src = Path(work_dir) / "restart" / "olp"
    ds_dir = Path(work_dir) / "deeph_datasets" / step_name
    ds_dir.mkdir(parents=True, exist_ok=True)

    structures = utils.read_structures(structures_file)
    exported = 0
    skipped = []

    for sid, poscar_path in structures:
        out_dir = ds_dir / sid
        if (out_dir / "hamiltonian.h5").exists():
            exported += 1
            continue

        h = utils.find_final_hamiltonian(step_src / sid)
        if not h:
            skipped.append(sid)
            continue

        overlap = olp_src / sid / "overlap.h5"
        if not overlap.exists():
            skipped.append(sid)
            continue

        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(poscar_path, out_dir / "POSCAR")
        shutil.copy2(h, out_dir / "hamiltonian.h5")
        shutil.copy2(overlap, out_dir / "overlap.h5")

        info_src = olp_src / sid / "info.json"
        if info_src.exists():
            shutil.copy2(info_src, out_dir / "info.json")
        else:
            _write_minimal_info(out_dir / "info.json")

        exported += 1

    if skipped:
        print(f"  [export] {len(skipped)} skipped (no overlap.h5 or hamiltonian)")

    if exported:
        _write_features_json(ds_dir, structures)
        print(f"  [export] {step_name}: {exported} structures, {len(skipped)} skipped")

    return exported


def package_datasets(work_dir):
    ds_base = Path(work_dir) / "deeph_datasets"
    if not ds_base.is_dir():
        return
    for d in sorted(ds_base.iterdir()):
        if not d.is_dir():
            continue
        tgz = ds_base / f"{d.name}.tar.gz"
        if tgz.exists() and tgz.stat().st_mtime > d.stat().st_mtime:
            continue
        print(f"  [package] {d.name}.tar.gz")
        with tarfile.open(tgz, "w:gz") as tf:
            tf.add(d, arcname=d.name)


def _write_minimal_info(path):
    path.write_text(json.dumps({"atoms_quantity": 32, "orbits_quantity": 416,
                                 "orthogonal_basis": False, "spinful": False}) + "\n")


def _write_features_json(dataset_dir, structures):
    first = None
    for sid, _ in structures:
        info = dataset_dir / sid / "info.json"
        if info.exists():
            first = info
            break

    elem_map = {}
    orb_types = []
    spinful = False
    if first:
        data = json.loads(first.read_text())
        elem_map = data.get("elements_orbital_map", {})
        for v in elem_map.values():
            if isinstance(v, list):
                orb_types = v
                break
        spinful = data.get("spinful", False)

    sids = sorted(d.name for d in dataset_dir.iterdir() if d.is_dir())
    features = {
        "_ready_to_be_used": True,
        "all_dft_data_num": len(sids),
        "all_dft_dirname": sids,
        "elements_orbital_map": elem_map or {"Al": [0, 0, 1, 1, 2]},
        "common_orbital_types": orb_types or [0, 0, 1, 1, 2],
        "common_orbital_num": len(orb_types) or 5,
        "spinful": spinful,
        "common_fitting_num": 0,
    }
    (dataset_dir / "features.json").write_text(json.dumps(features, indent=2) + "\n")
