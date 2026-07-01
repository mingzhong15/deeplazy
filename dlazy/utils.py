import re
import sys
from pathlib import Path


def natural_key(path: Path):
    """Sort key that splits numeric chunks so step10 sorts after step2."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(path.name))]


def read_structures(path, base=None):
    result = []
    if base is None:
        base = Path(path).parent
    else:
        base = Path(base)
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = Path(line)
            if not p.is_absolute():
                p = base / p
            sid = p.stem
            result.append((sid, str(p.resolve())))
    return result


def find_final_hamiltonian(work_dir):
    """Return the highest step number hamiltonians_step*.h5, or None."""
    step_files = sorted(Path(work_dir).glob("hamiltonians_step*.h5"),
                        key=natural_key)
    return str(step_files[-1]) if step_files else None


def check_finished(std_path):
    """Check if an OpenMX calculation finished normally."""
    p = Path(std_path)
    if not p.exists():
        return False
    text = p.read_text()
    return "normally finished" in text


def extract_scf_criterion(val):
    """Normalize scf_criterion string/float to display format."""
    if isinstance(val, str):
        return float(val)
    return val


def print_progress_bar(done, total, label, width=30):
    frac = done / total if total else 0
    filled = int(width * frac)
    bar = "▓" * filled + "░" * (width - filled)
    print(f"  [{label}] {bar} {done}/{total}")


def update_progress(done, total, label, width=30):
    frac = done / total if total else 0
    filled = int(width * frac)
    bar = "▓" * filled + "░" * (width - filled)
    sys.stdout.write(f"\r  preparing {label}: {bar} {done}/{total}")
    sys.stdout.flush()


def make_mpi_cmd(template, exe, cpus):
    cmd = template.replace("{cpus}", str(cpus))
    return f"{cmd} {exe} openmx_in.dat > openmx.std"
