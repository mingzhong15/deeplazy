import json
import shutil
import tarfile
from pathlib import Path

from . import utils


def export_step_dataset(step_name, *, structures_file, work_dir, discover_all=False):
    step_src = Path(work_dir) / "restart" / step_name
    olp_src = Path(work_dir) / "restart" / "olp"
    ds_dir = Path(work_dir) / "deeph_datasets" / step_name
    ds_dir.mkdir(parents=True, exist_ok=True)

    structures = utils.read_structures(structures_file)

    if discover_all:
        sid_to_poscar = {sid: p for sid, p in structures}

        poscar_base = poscar_ext = None
        if sid_to_poscar:
            example = Path(next(iter(sid_to_poscar.values())))
            poscar_base, poscar_ext = example.parent, example.suffix

        discovered = sorted(
            d.name for d in step_src.iterdir()
            if d.is_dir() and list(d.glob("hamiltonians_step*.h5"))
        )

        structures = []
        for sid in discovered:
            if sid in sid_to_poscar:
                structures.append((sid, sid_to_poscar[sid]))
            elif poscar_base:
                inferred = poscar_base / f"{sid}{poscar_ext}"
                if inferred.exists():
                    structures.append((sid, str(inferred)))
                else:
                    print(f"  [export] WARNING: POSCAR not found for {sid}, skipping")
            else:
                print(f"  [export] WARNING: cannot infer POSCAR for {sid}, skipping")

        print(f"  [export] discovered {len(structures)} structures")

    exported = 0
    skipped_h = 0
    missed_olp = 0

    for sid, poscar_path in structures:
        out_dir = ds_dir / sid
        ham_dst = out_dir / "hamiltonian.h5"
        olp_dst = out_dir / "overlap.h5"
        olp_src_file = olp_src / sid / "overlap.h5"

        if ham_dst.exists() and olp_dst.exists():
            exported += 1
            continue

        if not ham_dst.exists():
            h = utils.find_final_hamiltonian(step_src / sid)
            if not h:
                skipped_h += 1
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(poscar_path, out_dir / "POSCAR")
            shutil.copy2(h, ham_dst)
            info_src = olp_src / sid / "info.json"
            if info_src.exists():
                shutil.copy2(info_src, out_dir / "info.json")
            else:
                _write_minimal_info(out_dir / "info.json")

        if olp_src_file.exists():
            shutil.copy2(olp_src_file, olp_dst)
        else:
            missed_olp += 1

        exported += 1

    if skipped_h:
        print(f"  [export] {skipped_h} skipped (no hamiltonian)")
    if missed_olp:
        print(f"  [export] WARNING: {missed_olp} structures missing overlap.h5")
    if exported:
        _write_features_json(ds_dir, structures)
        print(f"  [export] {step_name}: {exported} structures")

    return exported


def _human_size(b):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


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
        print(f"             {_human_size(tgz.stat().st_size)}")


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
