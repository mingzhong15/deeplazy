# Draft: sigma-flow 项目分析

## 项目概述

**项目位置**: `/thfs4/home/xuyong/zeng/00.B-comp/01.sigma-flow`

**核心功能**: 计算 sigma 键对电子结构的贡献，包括能带和态密度 (DOS) 分析

**技术栈**: Python, Julia, Bash, Slurm HPC

---

## 文件结构

```
01.sigma-flow/
├── lib/                          # 数据库文件 (CSV)
│   ├── metastable_2element_100meV.csv
│   ├── metastable_3element_100meV.csv
│   ├── stable_2element.csv
│   └── stable_3element.csv
│
├── src/                          # 核心源代码
│   ├── DeepH-sigma.py           # ★ 核心：sigma键分析
│   ├── diag-sigma.jl            # ★ 核心：对角化计算
│   ├── get_fermi.jl             # ★ 核心：费米能计算
│   ├── gen_band_config.py       # 能带配置生成
│   ├── gen_openmx_input.py      # OpenMX输入生成
│   ├── merge_fermi_to_config.py # 合并费米能到配置
│   ├── plot_*.py                # 绘图脚本
│   ├── basis_dict.json          # 基组字典
│   └── openmx_*.sh              # OpenMX辅助脚本
│
├── 01.run_gen_quick.sh           # ★ 步骤1：快速生成配置
├── 02.run_calc_sigma.sh          # ★ 步骤2：并行计算
├── 02.sub_adv.sh                 # 高级作业提交
├── 03.gen_dft_dir.sh             # DFT目录生成 (串行)
├── 04.gen_dft_dir_quick.sh       # DFT目录生成 (并行)
├── 05.get_stats.py               # 统计分析
├── 06.collect_poscar.sh          # POSCAR收集
└── sigma_bond_group.slurm        # Slurm作业脚本
```

---

## 数据流分析

### 主工作流

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SIGMA-FLOW 数据流                                    │
└─────────────────────────────────────────────────────────────────────────────┘

输入数据:
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   CSV文件    │    │  POSCAR路径  │    │ folders.dat  │
│ (元素/结构)  │    │  (晶体结构)  │    │ (哈密顿量)   │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │
       └───────────────────┴───────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 阶段1: 准备阶段 (01.run_gen_quick.sh)                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  输入: CSV + folders.dat                                                     │
│  输出: 工作目录结构                                                          │
│        ├── POSCAR (软链接)                                                   │
│        ├── preprocessed (软链接到哈密顿量)                                    │
│        ├── band_config.json                                                  │
│        ├── dos_config.json                                                   │
│        └── get_fermi_config.json                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 阶段2: 计算阶段 (02.run_calc_sigma.sh / sigma_bond_group.slurm)              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐                                                        │
│  │ get_fermi.jl    │ 计算 Fermi 能级                                         │
│  │ 输入: H_k, S_k  │                                                        │
│  │ 输出: fermi_level│                                                        │
│  └────────┬────────┘                                                        │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────┐                                                        │
│  │ DeepH-sigma.py  │ 计算 sigma 键权重                                       │
│  │ 输入: 结构信息  │ - radial_weights.h5                                     │
│  │ 输出: 变换矩阵  │ - left/right_transform_matrixs.h5                       │
│  └────────┬────────┘                                                        │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────┐                                                        │
│  │ merge_fermi     │ 合并 Fermi 能级到配置                                   │
│  └────────┬────────┘                                                        │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────┐     ┌─────────────────┐                               │
│  │ diag-sigma.jl   │────▶│ DOS计算         │                                │
│  │ (dos模式)       │     │ plot_dos_sigma  │                                │
│  └────────┬────────┘     └─────────────────┘                               │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────┐     ┌─────────────────┐                               │
│  │ diag-sigma.jl   │────▶│ Band计算        │                                │
│  │ (band模式)      │     │ plot_band_sigma │                                │
│  └─────────────────┘     └─────────────────┘                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 阶段3: 后处理 (03/04.gen_dft_dir.sh + 05.get_stats.py)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  DFT目录转换:                                                                │
│  - preprocessed -> preprocessed_deeph (备份)                                │
│  - 创建 preprocessed_dft (使用 hamiltonians.h5 而非 hamiltonians_pred.h5)   │
│                                                                              │
│  统计分析:                                                                   │
│  - sigma_dos_at_fermi                                                       │
│  - total_dos_at_fermi                                                       │
│  - 相关性分析                                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 核心依赖关系

### 脚本依赖图

```
01.run_gen_quick.sh
    │
    ├── 依赖: CSV文件, folders.dat
    ├── 调用: gen_band_config.py
    ├── 调用: gen_openmx_input.py
    └── 输出: 工作目录 + 配置文件

02.run_calc_sigma.sh (或 sigma_bond_group.slurm)
    │
    ├── 依赖: 01的输出目录
    ├── 调用: get_fermi.jl ──────────────────────┐
    ├── 调用: DeepH-sigma.py                     │
    ├── 调用: merge_fermi_to_config.py ◀─────────┘
    ├── 调用: diag-sigma.jl (dos) ───▶ plot_dos_sigma.py
    └── 调用: diag-sigma.jl (band) ──▶ plot_openmx_band_sigma*.py

03/04.gen_dft_dir.sh
    │
    └── 依赖: 02的输出目录
    └── 转换: hamiltonians_pred.h5 -> hamiltonians.h5

05.get_stats.py
    │
    └── 依赖: 02的输出目录 (dos.dat, sigma_dos.dat)
    └── 输出: 统计报告 + 图表
```

### 核心Python/Julia脚本依赖

```
DeepH-sigma.py (核心: sigma键分析)
├── 输入文件:
│   ├── lat.dat              (晶格矢量)
│   ├── rlat.dat             (倒格矢)
│   ├── site_positions.dat   (原子位置)
│   ├── element.dat          (元素)
│   └── orbital_types.dat    (轨道类型)
├── 输出文件:
│   ├── sigma_kernels.dat    (sigma轨道核)
│   ├── radial_weights.h5    (径向权重)
│   ├── left_transform_matrixs.h5
│   └── right_transform_matrixs.h5
└── 外部依赖:
    ├── numpy, h5py, json, tqdm
    └── torch, e3nn (角动量变换)

get_fermi.jl (核心: Fermi能级)
├── 输入文件:
│   ├── hamiltonians_pred.h5 (或 hamiltonians.h5)
│   ├── overlaps.h5
│   ├── orbital_types.dat
│   ├── site_positions.dat
│   ├── rlat.dat
│   └── get_fermi_config.json
├── 输出文件:
│   └── info.json (含 fermi_level)
└── 外部依赖:
    ├── HDF5, JSON, LinearAlgebra
    └── Arpack (稀疏矩阵)

diag-sigma.jl (核心: 能带/DOS计算)
├── 输入文件:
│   ├── hamiltonians_pred.h5
│   ├── overlaps.h5
│   ├── radial_weights.h5      (from DeepH-sigma.py)
│   ├── left/right_transform_matrixs.h5
│   ├── sigma_kernels.dat
│   ├── band_config.json / dos_config.json
│   └── info.json (含 fermi_level)
├── 输出文件:
│   ├── dos.dat / egvals.dat
│   ├── sigma_dos.dat / sigma_band.dat
│   └── openmx.Band (能带格式)
└── 外部依赖:
    ├── HDF5, JSON, LinearAlgebra
    └── SparseArrays, Arpack
```

---

## 发现的问题

### 1. 硬编码路径问题
**问题**: 多处硬编码了绝对路径，降低了可移植性
```
/thfs4/home/xuyong/zeng/software/vaspkit.1.5.1/bin
/thfs4/home/xuyong/zeng/env/mz/bin/python
/thfs4/home/xuyong/software/julia-1.10.6/bin/julia
/thfs4/home/xuyong/zeng/00.B-comp/sigma-bonding/src
/thfs4/home/xuyong/data/openmx/DFT_DATA19
```

**影响**: 代码无法在其他环境直接使用

### 2. 路径不一致
**问题**: 脚本中的路径指向 `sigma-bonding` 而非 `01.sigma-flow`
```
CODE_DIR="/thfs4/home/xuyong/zeng/00.B-comp/sigma-bonding/src"
OUTPUT_BASE="/thfs4/home/xuyong/zeng/00.B-comp/sigma-bonding/multi_run/..."
```

**实际位置**: `/thfs4/home/xuyong/zeng/00.B-comp/01.sigma-flow`

### 3. 重复的脚本
**问题**: 存在功能重复的脚本
- `02.run_calc_sigma.sh` 和 `sigma_bond_group.slurm` 功能高度重叠
- `03.gen_dft_dir.sh` 和 `04.gen_dft_dir_quick.sh` 功能相同 (串行 vs 并行)

### 4. 缺少模块化
**问题**: 
- 没有统一的配置文件管理
- 环境变量分散在各脚本中
- 没有统一的日志管理

### 5. 外部依赖未明确声明
**问题**: 缺少 requirements.txt 或 Project.toml

---

## 清理建议

### 可以移除/整合的文件

| 文件 | 建议 | 原因 |
|------|------|------|
| `sigma_bond_group.slurm` | 整合到 02.run_calc_sigma.sh | 功能重复 |
| `get_fermi_dos.py` | 检查是否仍在使用 | 与 get_fermi.jl 功能重叠? |
| `collect_poscars.py` | 检查是否仍在使用 | 需确认用途 |
| `get_poscar.sh` / `06.collect_poscar.sh` | 整合为一个 | 功能相似 |

### 建议的目录重组

```
01.sigma-flow/
├── config/
│   └── config.sh              # 统一配置 (路径、环境变量)
├── src/
│   ├── python/
│   │   ├── DeepH-sigma.py
│   │   ├── gen_band_config.py
│   │   └── ...
│   ├── julia/
│   │   ├── get_fermi.jl
│   │   ├── diag-sigma.jl
│   │   └── ...
│   └── utils/
│       └── plotting/
├── scripts/
│   ├── 01_prepare.sh
│   ├── 02_calculate.sh
│   ├── 03_dft_convert.sh
│   └── 04_analyze.sh
├── lib/                        # 数据库
├── requirements.txt            # Python依赖
├── Project.toml                # Julia依赖
└── README.md
```

---

## 用户决策

| 问题 | 决定 |
|------|------|
| 整理范围 | **最小修复** - 仅修复关键问题 |
| 硬编码路径 | **保持现状** - 不修改路径结构 |
| 重复脚本 | **整合为一个** - 合并功能重复的脚本 |

---

## 待执行工作

### 任务1: 修复路径不一致问题
**问题**: 脚本中 `CODE_DIR` 指向 `sigma-bonding/src` 而非实际的 `01.sigma-flow/src`
**修复**: 将所有 `sigma-bonding` 引用改为 `01.sigma-flow`

### 任务2: 整合重复的Slurm脚本
**问题**: `sigma_bond_group.slurm` 和 `02.run_calc_sigma.sh` 功能完全相同
**修复**: 保留 `02.run_calc_sigma.sh`，删除 `sigma_bond_group.slurm`

### 任务3: 整合DFT目录生成脚本
**问题**: `03.gen_dft_dir.sh` (串行) 和 `04.gen_dft_dir_quick.sh` (并行) 功能相同
**修复**: 保留并行版本 `04.gen_dft_dir_quick.sh`，将 `03.gen_dft_dir.sh` 标记为废弃或删除

### 任务4: 更新README文档
**修复**: 更新README说明实际的工作流和正确的路径
