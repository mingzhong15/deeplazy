import json
import os
import numpy as np
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from pymatgen.core.structure import Structure

# === per-step output alias → canonical (Input_std.c:1126-1138) ===
_STEP_KEYWORD_MAP = {
    "hamiltonianstep":   "HamiltonianStep",
    "hamiltonian":       "HamiltonianStep",
    "h":                 "HamiltonianStep",
    "densitymatrixstep": "DensityMatrixStep",
    "densitymatrix":     "DensityMatrixStep",
    "dm":                "DensityMatrixStep",
    "chargedensitystep": "ChargeDensityStep",
    "chargedensity":     "ChargeDensityStep",
    "rho":               "ChargeDensityStep",
    "eigenvaluestep":    "EigenvalueStep",
    "eigenvalue":        "EigenvalueStep",
    "eigen":             "EigenvalueStep",
    "energystep":        "EnergyStep",
    "energy":            "EnergyStep",
    "e":                 "EnergyStep",
    "forcestep":         "ForceStep",
    "force":             "ForceStep",
    "f":                 "ForceStep",
}


def _resolve_step_output(step_output):
    validated = []
    invalid = []
    for raw in step_output:
        canon = _STEP_KEYWORD_MAP.get(str(raw).strip().lower())
        if canon is None:
            invalid.append(raw)
        elif canon not in validated:
            validated.append(canon)
    if invalid:
        canon = sorted(set(_STEP_KEYWORD_MAP.values()))
        aliases = sorted(set(k for k in _STEP_KEYWORD_MAP
                             if k not in set(v.lower() for v in _STEP_KEYWORD_MAP.values())))
        raise ValueError(
            f"无效的 step_output: {invalid}\n"
            f"  合法关键字: {canon}\n"
            f"  可用别名: {aliases}")
    return validated


class ParseVaspPoscar:
    def __init__(self, poscar_content):
        self._structure = Structure.from_str(poscar_content, fmt='poscar')

    def get_primitive_structure(self):
        return self._structure.get_primitive_structure()

    def get_poscar(self):
        return self._structure.to(fmt='poscar')

    def regularize_structure(self, niggli=False, prim=False):
        s = self._structure
        if prim:
            from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
            sga = SpacegroupAnalyzer(s, symprec=1e-5)
            s = sga.get_refined_structure()
            s = s.get_primitive_structure(tolerance=1e-5)
        if niggli:
            s = s.get_reduced_structure()
        self._structure = s

    def get_ibz(self):
        from pymatgen.symmetry.bandstructure import HighSymmKpath
        ibz = HighSymmKpath(self._structure)
        if ibz.kpath is None:
            ibz._kpath = {'kpoints': {'\\Gamma': np.array([0., 0., 0.])}, 'path': [['\\Gamma', '\\Gamma']]}
        return ibz

    def get_reciprocal_lattice(self):
        return self._structure.lattice.reciprocal_lattice

    def get_elements(self):
        return [atom for atom in self._structure.composition.as_dict().keys()]

    def get_elements_num(self):
        return [int(atom_num) for atom_num in self._structure.composition.as_dict().values()]

    def get_dimension(self):
        from pymatgen.analysis.local_env import CrystalNN
        from pymatgen.analysis.dimensionality import get_dimensionality_larsen
        crystal_nn = CrystalNN()
        bonded_structure = crystal_nn.get_bonded_structure(self._structure)
        return get_dimensionality_larsen(bonded_structure)

    def analyze_symmetry(self):
        from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
        analyzer = SpacegroupAnalyzer(self._structure)
        return {
            "crystal_system": analyzer.get_crystal_system(),
            "bravais_lattice": analyzer.get_lattice_type(),
            "space_group": analyzer.get_space_group_number()
        }

    def get_info(self, *args, **kwargs):
        niggli = kwargs.get("niggli", False)
        prim = kwargs.get("prim", False)
        self.regularize_structure(niggli=niggli, prim=prim)
        return {
            'is_bulk': True,
            'elements': self.get_elements(),
            'symmetry': self.analyze_symmetry(),
            'poscar_spec': self.get_poscar(),
            'elements_num': self.get_elements_num(),
        }


class ParsePoscar(ParseVaspPoscar):
    def __init__(self, poscar_content):
        super().__init__(poscar_content)

    def get_lattice(self):
        return self._structure.lattice

    def get_frac_pos(self):
        frac_pos_list = []
        for site_index in range(len(self._structure.sites)):
            site_dict = self._structure.sites[site_index].to_unit_cell().as_dict()
            frac_pos = site_dict['abc']
            frac_pos = [x if abs(x - 1.0) > 1e-10 else 0.0 for x in frac_pos]
            frac_pos_list.append(frac_pos)
        return frac_pos_list

    def get_full_elements(self):
        elem_list = []
        for site_index in range(len(self._structure.sites)):
            site_dict = self._structure.sites[site_index].as_dict()
            element = site_dict['species'][0]['element']
            elem_list.append(element)
        return elem_list

    def get_info(self, *args, **kwargs):
        niggli = kwargs.get("niggli", False)
        prim = kwargs.get("prim", False)
        self.regularize_structure(niggli=niggli, prim=prim)
        return {
            'is_bulk': True,
            'elements': self.get_full_elements(),
            'symmetry': self.analyze_symmetry(),
            'poscar_spec': self.get_poscar(),
            'elements_num': self.get_elements_num(),
            'frac_pos': self.get_frac_pos(),
            'lattice': self.get_lattice().matrix
        }


class GenOpenMXKpoints:
    def __init__(self, poscar_content="", output_kpoints="KPOINTS"):
        self._structure = ParsePoscar(poscar_content)
        self._kpoints = None
        self._output_kpoints = output_kpoints

    @staticmethod
    def _getmod(a):
        return np.sqrt(np.sum(np.square(a)))

    def auto_grid(self, kmesh_density: float):
        lattice = self._structure.get_lattice()
        kpoint = (round(kmesh_density / (2 * lattice.a)) * 2 + 1,
                  round(kmesh_density / (2 * lattice.b)) * 2 + 1,
                  round(kmesh_density / (2 * lattice.c)) * 2 + 1)
        return kpoint

    def auto_mp(self, kmesh_density: float):
        comment = "Monkhorst-Pack kpoint scheme with kmesh density = {}".format(kmesh_density)
        kpt = self.auto_grid(kmesh_density)
        self._kpoints = dict(
            comment=comment,
            num_kpts=0,
            style="Monkhorst-Pack",
            kpts=kpt,
            kpts_shift=(0, 0, 0),
        )
        return self._kpoints

    def auto_path_bulk(self, num="20"):
        ibz = self._structure.get_ibz()
        return self.gen_kpts_path(ibz, num)

    def gen_kpts_path(self, ibz, num="20"):
        comment = "K-Path kpoint scheme"
        kpoints = []
        labels = []
        for path in ibz.kpath["path"]:
            kpoints.append(ibz.kpath["kpoints"][path[0]])
            labels.append(path[0])
            for i in range(1, len(path) - 1):
                kpoints.append(ibz.kpath["kpoints"][path[i]])
                labels.append(path[i])
                kpoints.append(ibz.kpath["kpoints"][path[i]])
                labels.append(path[i])
            kpoints.append(ibz.kpath["kpoints"][path[-1]])
            labels.append(path[-1])
        for i in range(len(labels)):
            labels[i] = labels[i].replace("\\", "")
        self._kpoints = dict(
            comment=comment,
            style="Line-Mode",
            coord_type="Reciprocal",
            kpts=kpoints,
            labels=labels,
            num_kpts=int(num),
        )
        return self._kpoints

    def out(self):
        if self._kpoints is None:
            raise ValueError("Please generate kpoints first!")
        return self._kpoints


class GetElementsConf:
    def __init__(self, element_list, element_conf, pao_mode):
        if len(element_list) == 0:
            raise ValueError("element_list is empty")
        self.element_list = sorted(list(set(element_list)))
        if element_conf is None:
            raise ValueError("element_conf is None")
        self.element_conf = element_conf
        if pao_mode is None:
            raise ValueError("pao_mode is None")
        self.pao_mode = pao_mode
        self._read_from_json()

    def _read_from_json(self):
        with open(self.element_conf, "r") as file:
            pvs_json = json.load(file)
        self.pvs_map = pvs_json[self.pao_mode]
        self.pao_list = []
        self.vps_list = []
        self.electron_num_dict = {}
        for element in self.element_list:
            pao, vps, electron_num = self.pvs_map[element]
            self.pao_list.append(pao)
            self.vps_list.append(vps)
            self.electron_num_dict[element] = electron_num

    def out(self):
        return dict(
            pao=self.pao_list,
            vps=self.vps_list,
            electron_num=self.electron_num_dict,
        )


class OpenMXGenerator:
    def __init__(self, data_path, niggli=True, prim=True):
        self.data_path = data_path
        self.poscar_conf = {"niggli": niggli, "prim": prim}
        self._script_dir = Path(__file__).parent / "static"
        self._elem_conf = str(self._script_dir / "element_conf.json")
        self._template_dir = str(self._script_dir)
        self._template_file = "openmx_templ.j2"

    def generate(self, poscar_path, output_dir=".",
                 max_iter=200, scf_criterion=1e-8,
                 spin_polarization="Off",
                 mixing_type="RMM-DIISH",
                 mixing_history=30, startpulay=3,
                 init_mixing_weight=0.3, max_mixing_weight=0.8,
                 detailed_output=False, step1_mix_h=False,
                 step_output=None):
        with open(poscar_path) as f:
            poscar_content = f.read()

        parser = ParsePoscar(poscar_content)
        info = parser.get_info(**self.poscar_conf)

        elem_config = GetElementsConf(
            info['elements'], self._elem_conf, pao_mode="standard_nof_s")
        elem_out = elem_config.out()

        kpts = GenOpenMXKpoints(info['poscar_spec'])
        kpts.auto_mp(80)
        kgrid = kpts.out()

        kpts = GenOpenMXKpoints(info['poscar_spec'])
        kpts.auto_path_bulk(20)
        kpath = kpts.out()

        species_num = len(info['elements_num'])
        atom_num = sum(info['elements_num'])
        criterion = scf_criterion * atom_num

        sorted_elements = sorted(list(set(info['elements'])))
        str_epv = "\n".join(
            f" {e:<4} {pao:<20} {vps}"
            for e, pao, vps in zip(sorted_elements, elem_out['pao'], elem_out['vps']))

        electron_num_list = [elem_out['electron_num'][e] for e in info['elements']]
        pos_lines = []
        for i, (e, frac, en) in enumerate(zip(info['elements'], info['frac_pos'], electron_num_list)):
            pos_lines.append(
                f" {i + 1:<2} {e:<3} {frac[0]:20.16f} {frac[1]:20.16f} {frac[2]:20.16f}   {en / 2:.1f} {en / 2:.1f}")
        str_atom_pos = "\n".join(pos_lines)

        str_unit_vec = "\n".join(
            f" {v[0]:20.16f} {v[1]:20.16f} {v[2]:20.16f}" for v in info['lattice'])

        str_kgrid = f"{kgrid['kpts'][0]:4d} {kgrid['kpts'][1]:4d} {kgrid['kpts'][2]:4d}"

        num_kpts = kpath['num_kpts']
        kpts_list = kpath['kpts']
        labels = kpath['labels']
        kpt1s = kpts_list[::2]
        kpt2s = kpts_list[1::2]
        label1s = labels[::2]
        label2s = labels[1::2]
        kpath_lines = []
        for k1, k2, l1, l2 in zip(kpt1s, kpt2s, label1s, label2s):
            kpath_lines.append(
                f"{num_kpts} {k1[0]:f} {k1[1]:f} {k1[2]:f} {k2[0]:f} {k2[1]:f} {k2[2]:f} {l1} {l2}")

        params = {
            'DATA_PATH': self.data_path,
            'Species_Number': str(species_num),
            'Atoms_Number': str(atom_num),
            'scf_criterion': str(criterion),
            'scf_SpinPolarization': spin_polarization,
            'scf_SpinOrbit_Coupling': 'Off',
            'scf_maxIter': str(max_iter),
            'scf_Mixing_Type': mixing_type,
            'scf_Mixing_History': str(mixing_history),
            'scf_Mixing_StartPulay': str(startpulay),
            'scf_Init_Mixing_Weight': str(init_mixing_weight),
            'scf_Max_Mixing_Weight': str(max_mixing_weight),
            'Block_Definition_of_Atomic_Species': str_epv,
            'Block_Atoms_SpeciesAndCoordinates': str_atom_pos,
            'Block_Atoms_UnitVectors': str_unit_vec,
            'scf_Kgrid': str_kgrid,
            'BAND': True,
            'Band_Nkpath': str(len(kpath_lines)),
            'Block_Band_kpath': "\n".join(kpath_lines),
        }

        os.makedirs(output_dir, exist_ok=True)
        env = Environment(
            loader=FileSystemLoader(self._template_dir),
            trim_blocks=True, lstrip_blocks=True)
        template = env.get_template(self._template_file)
        content = template.render(**params)

        extra = []
        if detailed_output:
            extra.append("scf.DetailedOutput     On")
            if step_output:
                for key in _resolve_step_output(step_output):
                    extra.append(f"scf.{key}     On")
        else:
            extra.append("scf.DetailedOutput     Off")
        if step1_mix_h:
            extra.append("scf.Step1MixH     On")
        if extra:
            extra_block = "\n".join(extra) + "\n"
            marker = "MD.Type"
            if marker in content:
                content = content.replace(marker, extra_block + marker, 1)
            else:
                content += "\n" + extra_block

        with open(os.path.join(output_dir, "openmx_in.dat"), 'w') as f:
            f.write(content)
