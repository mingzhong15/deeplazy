# Draft: sigma-flow-v2 规划

## 背景分析

### v1 数据结构 (旧格式)
```
folders.dat 格式:
POSCAR路径 ham_path1 ham_path2

ham_path 目录内容:
├── hamiltonians.h5
├── overlaps.h5
├── site_positions.dat
├── element.dat
├── lat.dat
├── rlat.dat
├── orbital_types.dat
└── info.json
```

### v2 数据结构 (新格式 - dlazy 批处理输出)
```
Al_calc/
├── batch.00000/
│   ├── output_calc/              # DFT 计算结果
│   │   └── task.000000/
│   │       ├── geth/             # DFT 真实哈密顿量
│   │       │   ├── hamiltonians.h5
│   │       │   ├── overlaps.h5
│   │       │   └── ...
│   │       └── scf/              # SCF 计算文件
│   │
│   ├── output_infer/             # 推理结果
│   │   └── g.001/                # 分组 (共 20 组)
│   │       ├── inputs/
│   │       │   ├── dft/          # 原始 POSCAR 等
│   │       │   │   └── task.000000/
│   │       │   ├── geth/         # DFT 哈密顿量输入
│   │       │   └── graph/        # 图文件
│   │       ├── geth/             # 预测的哈密顿量
│   │       │   └── task.000000/
│   │       │       ├── hamiltonians.h5  (预测)
│   │       │       └── ...
│   │       └── geth.new/         # 变换后的哈密顿量
│   │
│   └── output_olp/               # Overlap 计算结果
│
├── global_config.yaml            # 批处理配置
├── todo_list.json                # 任务列表 (JSON Lines)
└── batch_state.json              # 批处理状态
```

### 关键差异

| 方面 | v1 | v2 |
|------|----|----|
| 数据组织 | 平铺式 | 分层式 (batch/group/task) |
| 任务列表 | folders.dat (文本) | todo_list.json (JSON Lines) |
| 哈密顿量位置 | 直接路径 | output_infer/g.XXX/geth/task.YYYYY/ |
| 配置文件 | CSV | global_config.yaml |
| 元数据 | 无 | features.json, batch_state.json |

---

## v2 适配需求

### 1. 数据发现和收集
需要新的脚本：
- 扫描 batch.XXXXX 目录
- 找到 output_infer/g.XXX/geth/task.YYYYY 目录
- 收集所有可用的哈密顿量路径

### 2. 工作目录准备
- 创建新的目录结构
- 建立软链接到正确的 geth 目录
- 链接 POSCAR (从 inputs/dft 或 todo_list.json 路径)

### 3. 配置文件生成
- 需要读取 element.dat 获取元素信息
- 需要读取 site_positions.dat 获取原子数
- 生成 band_config.json, dos_config.json, get_fermi_config.json

### 4. 计算执行
- 复用 v1 的核心计算脚本
- 可能需要调整路径处理

---

## 规划 TODOs

### 阶段 1: 数据发现脚本
- [ ] 创建 `00.scan_batches.py` - 扫描所有 batch 目录
- [ ] 生成 `folders_v2.dat` 或 `tasks.json`

### 阶段 2: 准备脚本适配
- [ ] 修改 `01.run_gen_quick.sh` 适配新数据结构
- [ ] 或创建新脚本 `01.run_gen_v2.sh`

### 阶段 3: 计算脚本适配
- [ ] 修改 `02.run_calc_sigma.sh` 支持新路径格式
- [ ] 确保 Julia/Python 脚本兼容

### 阶段 4: 测试验证
- [ ] 使用 Al_calc 的前 5-10 个结构测试
- [ ] 验证所有计算步骤正常

---

## 关键技术决策 (需要确认)

1. **输出目录结构**:
   - 选项 A: 在 Al_calc 内创建 sigma-flow 子目录
   - 选项 B: 在外部创建独立的 sigma-flow-v2 输出目录

2. **输入数据来源**:
   - 使用 `output_infer` (预测哈密顿量)
   - 还是 `output_calc` (DFT 真实哈密顿量)

3. **批量处理策略**:
   - 单个 batch 目录独立处理
   - 还是跨 batch 统一处理

4. **Slurm 作业策略**:
   - 复用现有 Slurm 脚本
   - 还是根据 v2 数据量重新设计作业分割

---

## 待用户确认的问题

1. v2 主要用于分析预测结果 (output_infer) 还是 DFT 结果 (output_calc)?
2. 输出目录放在哪里?
3. 是否需要同时支持 v1 和 v2 数据格式?
