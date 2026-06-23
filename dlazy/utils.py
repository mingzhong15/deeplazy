import re
from pathlib import Path


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
                p = (base / p).resolve()
            result.append((p.stem, str(p)))
    return result


def find_final_hamiltonian(work_dir):
    """Return the highest step number hamiltonians_step*.h5, or None."""
    step_files = sorted(Path(work_dir).glob("hamiltonians_step*.h5"))
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


def make_mpi_cmd(template, exe, cpus):
    cmd = template.replace("{cpus}", str(cpus))
    return f"{cmd} {exe} openmx_in.dat > openmx.std"
