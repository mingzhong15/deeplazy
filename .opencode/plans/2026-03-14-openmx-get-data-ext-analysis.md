# openmx_get_data_ext.jl 实现计划

## 1. 原始脚本分析：openmx_get_data.jl

### 1.1 输入

| 来源 | 参数 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| 命令行 | `--input_dir, -i` | String | "./" | 输入目录 |
| 命令行 | `--output_dir, -o` | String | "./output" | 输出目录 |
| 命令行 | `--if_DM, -d` | Bool | false | 是否读取密度矩阵 |
| 命令行 | `--save_overlap, -s` | Bool | false | 是否保存重叠矩阵 |
| 文件 | `openmx.scfout` | Binary | - | OpenMX 二进制输出文件 |

### 1.2 输出

| 文件名 | 条件 | 格式 | 内容 | Key 格式 |
|--------|------|------|------|----------|
| `hamiltonians.h5` | 必输出 | HDF5 | Hamiltonian 矩阵 | `[Rx, Ry, Rz, site_i, site_j]` |
| `overlaps.h5` | `-s` 参数 | HDF5 | 重叠矩阵 OLP | `[Rx, Ry, Rz, site_i, site_j]` |
| `density_matrixs.h5` | `-d` 参数 | HDF5 | 密度矩阵 DM | `[Rx, Ry, Rz, site_i, site_j]` |
| `info.json` | 必输出 | JSON | fermi_level, isspinful | - |
| `site_positions.dat` | 必输出 | 文本 | 原子位置 (Ang) | - |
| `R_list.dat` | 必输出 | 文本 | R 向量列表 | - |
| `lat.dat` | 必输出 | 文本 | 晶格矢量 (Ang) | - |
| `rlat.dat` | 必输出 | 文本 | 倒格矢 | - |
| `orbital_types.dat` | 必输出 | 文本 | 轨道类型 | - |
| `element.dat` | 必输出 | 文本 | 元素原子序数 | - |

### 1.3 核心函数

#### `parse_openmx(filepath; return_DM=false)`

读取 `.scfout` 二进制文件，返回：
```julia
element, atomnum, SpinP_switch, atv, atv_ijk, Total_NumOrbs, 
FNAN, natn, ncn, tv, Hk, iHk, OLP, OLP_r, orbital_types, 
fermi_level, atom_pos, DM
```

**二进制读取顺序：**
1. Header: `atomnum, SpinP_switch, Catomnum, Latomnum, Ratomnum, TCpyCell, order_max`
2. atv, atv_ijk (格点向量)
3. Total_NumOrbs, FNAN (轨道数、近邻数)
4. natn, ncn (近邻原子索引、格点索引)
5. tv, rtv, Gxyz (晶格矢量、原子坐标)
6. **Hk** (Hamiltonian, SpinP_switch+1 个 spin)
7. **iHk** (虚部, 仅非共线时)
8. **OLP** (重叠矩阵)
9. OLP_r, OLP_p (位置/动量算符)
10. **DM** (密度矩阵)
11. iDM
12. Footer: chem_p, E_temp, Valence_Electrons, 等

#### `get_data(filepath, Rcut; if_DM=false)`

处理数据并转换为字典格式：
- 单位转换: Hartree→eV (×27.211), Bohr→Ang (×0.529)
- 处理自旋: SpinP_switch=0 (无自旋), =1 (共线), =3 (非共线)
- 输出: `element, overlaps, density_matrixs, hamiltonians, fermi_level, orbital_types, lat, site_positions, spinful, R_list`

---

## 2. 新脚本分析：openmx_get_data_ext.jl

### 2.1 输入

| 来源 | 参数 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| 命令行 | `--input_dir, -i` | String | "./" | 输入目录（继承） |
| 命令行 | `--output_dir, -o` | String | "./output" | 输出目录（继承） |
| 命令行 | `--if_DM, -d` | Bool | false | 是否读取密度矩阵（继承） |
| 命令行 | `--save_overlap, -s` | Bool | false | 是否保存重叠矩阵（继承） |
| 命令行 | **`--H_components`** | Bool | false | **新增：是否读取 H0/HNL/HVNA** |
| 文件 | `openmx.scfout` | Binary | - | OpenMX 二进制输出文件 |

### 2.2 输出

#### 继承自原始脚本（所有输出保持不变）

| 文件名 | 条件 | 格式 | 内容 |
|--------|------|------|------|
| `hamiltonians.h5` | 必输出 | HDF5 | Hamiltonian 矩阵 |
| `overlaps.h5` | `-s` 参数 | HDF5 | 重叠矩阵 OLP |
| `density_matrixs.h5` | `-d` 参数 | HDF5 | 密度矩阵 DM |
| `info.json` | 必输出 | JSON | 元信息 |
| `site_positions.dat` | 必输出 | 文本 | 原子位置 |
| `R_list.dat` | 必输出 | 文本 | R 向量列表 |
| `lat.dat` | 必输出 | 文本 | 晶格矢量 |
| `rlat.dat` | 必输出 | 文本 | 倒格矢 |
| `orbital_types.dat` | 必输出 | 文本 | 轨道类型 |
| `element.dat` | 必输出 | 文本 | 元素信息 |

#### 新增输出（`--H_components` 参数启用）

| 文件名 | 格式 | 内容 | Key 格式 | 说明 |
|--------|------|------|----------|------|
| **`H0.h5`** | HDF5 | 动能矩阵 | `[Rx, Ry, Rz, site_i, site_j]` | 自旋无关 |
| **`HNL.h5`** | HDF5 | 非局域赝势 | `[Rx, Ry, Rz, site_i, site_j, spin]` | 自旋依赖 |
| **`HVNA.h5`** | HDF5 | VNA 势 | `[Rx, Ry, Rz, site_i, site_j]` | 自旋无关 |

---

## 3. 二进制数据读取顺序对比

### 3.1 原始 .scfout 结构（无 H_Component_Output）

```
[Header]
atomnum, SpinP_switch, Catomnum, Latomnum, Ratomnum, TCpyCell, order_max

[Connectivity]
atv, atv_ijk, Total_NumOrbs, FNAN, natn, ncn, tv, rtv, Gxyz

[Hamiltonian]
Hk[spin]          # spin = 0..SpinP_switch
iHk[spin]         # spin = 0..2 (非共线时)

[Overlap]
OLP[0], OLP_r, OLP_p

[Density Matrix]
DM[spin], iDM

[Footer]
chem_p, E_temp, dipole_moment, Valence_Electrons, Total_SpinS
dummy_blocks, input_file_content
```

### 3.2 扩展 .scfout 结构（H_Component_Output=on）

```
[Header]           # 同上
[Connectivity]     # 同上
[Hamiltonian]      # 同上
[Overlap]          # 同上
[Density Matrix]   # 同上
[Footer]           # 同上

[New: H Components]  ← 追加在文件末尾
H0                 # 自旋无关, 单分量
HNL[spin]          # spin = 0..List_YOUSO[5]-1
HVNA               # 自旋无关
```

### 3.3 HNL 自旋分量数量

| SpinP_switch | List_YOUSO[5] | HNL 索引 | 说明 |
|--------------|---------------|----------|------|
| 0 (off) | 1 | HNL[0] | 无自旋 |
| 1 (collinear) | 2 | HNL[0,1] | 自旋向上/向下 |
| 3 (non-collinear) | 3 | HNL[0,1,2] | up-up, dn-dn, up-dn |

---

## 4. 实现方案

### 4.1 修改策略

**方案：复制原始脚本，扩展功能**

1. 复制 `openmx_get_data.jl` → `openmx_get_data_ext.jl`
2. 添加新命令行参数 `--H_components`
3. 修改 `parse_openmx()` 函数：
   - 在读取完所有现有数据后，尝试读取 H0/HNL/HVNA
   - 使用 `readbytes!` 返回值检测数据是否存在
4. 添加辅助函数：
   - `try_read_H_components()` - 尝试读取 H 组件
   - `raw_to_H_dict()` - 将原始数组转换为字典格式
   - `save_H0/HNL/HVNA()` - 保存到 HDF5

### 4.2 parse_openmx() 修改

在原始 `parse_openmx()` 函数末尾（`close(f)` 之前）添加：

```julia
# === 新增：尝试读取 H0/HNL/HVNA ===
H0_raw = nothing
HNL_raw = nothing
HVNA_raw = nothing
H_components_available = false

# 计算总矩阵大小
total_size = 0
for ct_AN in 1:atomnum
    TNO1 = Total_NumOrbs[ct_AN]
    for h_AN in 1:FNAN[ct_AN]
        Gh_AN = natn[ct_AN][h_AN]
        TNO2 = Total_NumOrbs[Gh_AN]
        total_size += TNO1 * TNO2
    end
end

# 尝试读取 H0
H0_raw = Vector{Float64}(undef, total_size)
n_bytes = readbytes!(f, reinterpret(UInt8, H0_raw), total_size * 8)
n_read = div(n_bytes, 8)

if n_read == total_size
    H_components_available = true
    
    # 确定 HNL 自旋数
    num_HNL_spin = SpinP_switch == 0 ? 1 : (SpinP_switch == 1 ? 2 : 3)
    
    # 读取 HNL
    HNL_raw = Vector{Float64}(undef, total_size * num_HNL_spin)
    read!(f, HNL_raw)
    
    # 读取 HVNA
    HVNA_raw = Vector{Float64}(undef, total_size)
    read!(f, HVNA_raw)
    
    println("H0/HNL/HVNA components read successfully")
else
    println("No H0/HNL/HVNA found (old format or not enabled)")
    H0_raw = nothing
    HNL_raw = nothing
    HVNA_raw = nothing
end
```

### 4.3 返回值修改

```julia
# 原始返回
return element, atomnum, SpinP_switch, atv, atv_ijk, Total_NumOrbs, 
       FNAN, natn, ncn, tv, Hk, iHk, OLP, OLP_r, orbital_types, 
       fermi_level, atom_pos, nothing

# 扩展返回
return element, atomnum, SpinP_switch, atv, atv_ijk, Total_NumOrbs, 
       FNAN, natn, ncn, tv, Hk, iHk, OLP, OLP_r, orbital_types, 
       fermi_level, atom_pos, nothing,
       H0_raw, HNL_raw, HVNA_raw, H_components_available
```

### 4.4 主程序修改

```julia
# 新增：处理并保存 H 组件
if parsed_args["H_components"] && H_components_available
    # 转换为字典格式
    H0_dict = raw_to_H_dict(H0_raw, atomnum, FNAN, natn, ncn, Total_NumOrbs, atv_ijk)
    HNL_dict = raw_to_HNL_dict(HNL_raw, atomnum, FNAN, natn, ncn, Total_NumOrbs, atv_ijk, num_HNL_spin)
    HVNA_dict = raw_to_H_dict(HVNA_raw, atomnum, FNAN, natn, ncn, Total_NumOrbs, atv_ijk)
    
    # 保存到 HDF5
    save_H0(H0_dict, ".")
    save_HNL(HNL_dict, ".", num_HNL_spin)
    save_HVNA(HVNA_dict, ".")
end
```

---

## 5. 数据验证

### 5.1 单位一致性

| 矩阵 | OpenMX 单位 | 输出单位 | 转换因子 |
|------|-------------|----------|----------|
| H | Hartree | eV | ×27.2113845 |
| H0 | Hartree | eV | ×27.2113845 |
| HNL | Hartree | eV | ×27.2113845 |
| HVNA | Hartree | eV | ×27.2113845 |

**所有 Hamiltonian 相关矩阵都使用相同的单位转换。**

### 5.2 物理关系验证

```
H_total = H0 + HNL + HVNA + H_SCF

其中:
- H0: 动能 + VNL (自旋无关)
- HNL: 非局域赝势实部
- HVNA: VNA 势 (自旋无关)
- H_SCF: SCF 收敛后的贡献 (Hartree 势 + XC 势)
```

### 5.3 验证脚本

```julia
using HDF5

# 读取数据
H = h5read("hamiltonians.h5", "[0, 0, 0, 1, 1]")
H0 = h5read("H0.h5", "[0, 0, 0, 1, 1]")
HNL = h5read("HNL.h5", "[0, 0, 0, 1, 1, 1]")  # spin=1
HVNA = h5read("HVNA.h5", "[0, 0, 0, 1, 1]")

# H0 应该等于动能部分
# H = H0 + HNL + HVNA + (SCF contribution)

println("H0 + HNL + HVNA = ", H0 + HNL + HVNA)
println("H_total = ", H)
```

---

## 6. 向后兼容性

| 场景 | 行为 |
|------|------|
| 旧 `.scfout` + 新脚本，无 `--H_components` | ✅ 正常工作 |
| 旧 `.scfout` + 新脚本，有 `--H_components` | ✅ 检测到无数据，输出提示 |
| 新 `.scfout` + 新脚本，无 `--H_components` | ✅ 正常工作，忽略 H 组件 |
| 新 `.scfout` + 新脚本，有 `--H_components` | ✅ 读取并输出 H 组件 |
| 新 `.scfout` + 旧脚本 | ✅ 正常工作，忽略末尾额外数据 |

---

## 7. 任务清单

### Chunk 1: 创建基础脚本
- [ ] 复制 `openmx_get_data.jl` → `openmx_get_data_ext.jl`
- [ ] 添加 `--H_components` 命令行参数

### Chunk 2: 修改 parse_openmx()
- [ ] 添加 H 组件读取逻辑
- [ ] 修改返回值
- [ ] 处理 `return_DM` 参数兼容性

### Chunk 3: 添加辅助函数
- [ ] 实现 `raw_to_H_dict()`
- [ ] 实现 `raw_to_HNL_dict()`
- [ ] 实现 `save_H0/HNL/HVNA()`

### Chunk 4: 主程序修改
- [ ] 修改 `get_data()` 函数签名
- [ ] 添加 H 组件处理和输出

### Chunk 5: 测试验证
- [ ] 测试旧格式文件兼容性
- [ ] 测试新格式文件读取
- [ ] 验证数据完整性

---

## 8. 文件位置

| 文件 | 路径 |
|------|------|
| 原始脚本 | `/thfs4/home/xuyong/script/openmx_get_data.jl` |
| 新脚本 | `/thfs4/home/xuyong/script/openmx_get_data_ext.jl` |
| 周期表数据 | `/thfs4/home/xuyong/script/periodic_table.json` |

---

计划完成。请确认是否开始实现？
