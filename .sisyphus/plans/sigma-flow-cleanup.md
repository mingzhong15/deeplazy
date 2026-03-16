# sigma-flow 项目最小修复计划

## TL;DR

> **目标**: 修复路径不一致问题和整合重复脚本，保持其他结构不变
> 
> **交付物**:
> - 修复后的脚本文件 (路径正确指向 `01.sigma-flow`)
> - 删除重复的 `sigma_bond_group.slurm`
> - 保留并优化 `04.gen_dft_dir_quick.sh`
> - 更新的 README 文档
> 
> **预计工作量**: Quick
> **并行执行**: NO - 顺序执行
> **关键路径**: 路径修复 → 脚本整合 → 文档更新

---

## Context

### 原始请求
用户希望整理 `/thfs4/home/xuyong/zeng/00.B-comp/01.sigma-flow` 项目，确认依赖关系，去掉不必要的依赖。

### 分析摘要
**发现的问题**:
1. **路径不一致**: 脚本中 `CODE_DIR` 指向 `sigma-bonding/src` 而非实际的 `01.sigma-flow/src`
2. **脚本重复**: `sigma_bond_group.slurm` 和 `02.run_calc_sigma.sh` 功能完全相同
3. **版本重复**: `03.gen_dft_dir.sh` 和 `04.gen_dft_dir_quick.sh` 分别是串行/并行版本

**用户决策**:
- 整理范围: 最小修复
- 硬编码路径: 保持现状
- 重复脚本: 整合为一个

### Metis Review
**已识别的问题**:
- 需要确认 `get_fermi_dos.py`、`collect_poscars.py`、`get_poscar.sh` 是否仍在使用
- 需要验证修复后的脚本是否能正常运行

---

## Work Objectives

### 核心目标
修复项目中阻碍正常使用的问题，保持其他结构不变

### 具体交付物
- 修复路径引用的脚本文件
- 清理重复的脚本文件
- 更新的项目文档

### 完成定义
- [ ] 所有 `sigma-bonding` 路径引用改为 `01.sigma-flow`
- [ ] `sigma_bond_group.slurm` 已删除
- [ ] `03.gen_dft_dir.sh` 已标记废弃或删除
- [ ] README 已更新说明正确的工作流

### 必须完成
- 路径修复

### 必须不做 (Guardrails)
- 不修改硬编码的绝对路径结构
- 不创建新的配置文件系统
- 不修改核心计算逻辑

---

## Verification Strategy

### 测试决策
- **Infrastructure exists**: NO
- **Automated tests**: None
- **Agent-Executed QA**: ALWAYS

### QA Policy
每个任务包含Agent执行的QA场景。

---

## Execution Strategy

### 顺序执行
```
Task 1 → Task 2 → Task 3 → Task 4
```

### 依赖矩阵
- **Task 1**: 无依赖
- **Task 2**: 依赖 Task 1 (路径正确后再整合)
- **Task 3**: 依赖 Task 1
- **Task 4**: 依赖 Task 1, 2, 3

---

## TODOs

- [ ] 1. 修复路径不一致问题

  **What to do**:
  - 搜索所有脚本中包含 `sigma-bonding` 的路径引用
  - 将 `sigma-bonding` 替换为 `01.sigma-flow`
  - 受影响文件:
    - `01.run_gen_quick.sh`: `CODE_DIR`
    - `02.run_calc_sigma.sh`: `CODE_DIR`, `OUTPUT_BASE`
    - `02.sub_adv.sh`: `OUTPUT_BASE`
    - `sigma_bond_group.slurm`: `CODE_DIR`, `OUTPUT_BASE`
    - `src/gen_openmx_input.py`: `basis_dict.json` 路径
    - `05.get_stats.py`: `base_dir` 默认值

  **Must NOT do**:
  - 不修改绝对路径结构 (如 `/thfs4/home/xuyong/...`)
  - 不添加新的配置变量

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的文本替换任务
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential
  - **Blocks**: Task 2, 3
  - **Blocked By**: None

  **References**:
  - `01.run_gen_quick.sh:15-20` - CODE_DIR 定义
  - `02.run_calc_sigma.sh:15-20` - CODE_DIR 定义
  - `05.get_stats.py:300-310` - base_dir 定义

  **Acceptance Criteria**:
  - [ ] `grep -r "sigma-bonding" *.sh` 返回空
  - [ ] `grep -r "sigma-bonding" src/*.py` 返回空

  **QA Scenarios**:

  ```
  Scenario: 路径修复验证
    Tool: Bash
    Preconditions: SSH 连接到远程服务器
    Steps:
      1. ssh cpu.tj.th-3k.dkvpn "grep -r 'sigma-bonding' /thfs4/home/xuyong/zeng/00.B-comp/01.sigma-flow/*.sh"
      2. 验证输出为空
    Expected Result: 无匹配结果
    Failure Indicators: 发现任何 "sigma-bonding" 字符串
    Evidence: .sisyphus/evidence/task-1-path-fix.txt
  ```

  **Commit**: YES
  - Message: `fix: correct path references from sigma-bonding to 01.sigma-flow`
  - Files: `*.sh`, `src/*.py`
  - Pre-commit: grep 验证

---

- [ ] 2. 整合重复的Slurm脚本

  **What to do**:
  - 比较 `sigma_bond_group.slurm` 和 `02.run_calc_sigma.sh` 的差异
  - 确认 `02.run_calc_sigma.sh` 功能更完整
  - 删除 `sigma_bond_group.slurm`
  - 更新 `02.sub_adv.sh` 中的引用 (如有)

  **Must NOT do**:
  - 不修改 `02.run_calc_sigma.sh` 的核心逻辑
  - 不添加新功能

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的文件删除任务
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential
  - **Blocks**: Task 4
  - **Blocked By**: Task 1

  **References**:
  - `sigma_bond_group.slurm` - 待删除文件
  - `02.run_calc_sigma.sh` - 保留文件
  - `02.sub_adv.sh` - 可能引用待删除文件

  **Acceptance Criteria**:
  - [ ] `sigma_bond_group.slurm` 文件已删除
  - [ ] 其他脚本无对 `sigma_bond_group.slurm` 的引用

  **QA Scenarios**:

  ```
  Scenario: 文件删除验证
    Tool: Bash
    Preconditions: SSH 连接
    Steps:
      1. ssh cpu.tj.th-3k.dkvpn "ls /thfs4/home/xuyong/zeng/00.B-comp/01.sigma-flow/sigma_bond_group.slurm"
    Expected Result: 文件不存在错误
    Failure Indicators: 文件仍然存在
    Evidence: .sisyphus/evidence/task-2-slurm-delete.txt
  ```

  **Commit**: YES
  - Message: `chore: remove duplicate sigma_bond_group.slurm`
  - Files: `sigma_bond_group.slurm` (删除)
  - Pre-commit: 无

---

- [ ] 3. 整合DFT目录生成脚本

  **What to do**:
  - 确认 `04.gen_dft_dir_quick.sh` 是并行版本，功能更优
  - 在 `03.gen_dft_dir.sh` 头部添加废弃警告
  - 或直接删除 `03.gen_dft_dir.sh`

  **Must NOT do**:
  - 不修改 `04.gen_dft_dir_quick.sh`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 简单的文件修改/删除任务
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential
  - **Blocks**: Task 4
  - **Blocked By**: Task 1

  **References**:
  - `03.gen_dft_dir.sh` - 串行版本
  - `04.gen_dft_dir_quick.sh` - 并行版本 (保留)

  **Acceptance Criteria**:
  - [ ] `03.gen_dft_dir.sh` 已标记废弃或删除
  - [ ] 文档中说明使用 `04.gen_dft_dir_quick.sh`

  **QA Scenarios**:

  ```
  Scenario: 废弃标记验证
    Tool: Bash
    Preconditions: SSH 连接
    Steps:
      1. ssh cpu.tj.th-3k.dkvpn "head -20 /thfs4/home/xuyong/zeng/00.B-comp/01.sigma-flow/03.gen_dft_dir.sh"
      2. 检查是否包含 DEPRECATED 或废弃说明
    Expected Result: 文件已标记废弃或已删除
    Failure Indicators: 文件存在且无废弃标记
    Evidence: .sisyphus/evidence/task-3-dft-script.txt
  ```

  **Commit**: YES
  - Message: `chore: deprecate 03.gen_dft_dir.sh in favor of 04.gen_dft_dir_quick.sh`
  - Files: `03.gen_dft_dir.sh`
  - Pre-commit: 无

---

- [ ] 4. 更新README文档

  **What to do**:
  - 更新 `src/README` 说明正确的工作流
  - 添加文件用途说明
  - 说明正确的工作流步骤:
    1. `01.run_gen_quick.sh` - 准备阶段
    2. `02.run_calc_sigma.sh` + `02.sub_adv.sh` - 计算阶段
    3. `04.gen_dft_dir_quick.sh` - DFT转换
    4. `05.get_stats.py` - 统计分析

  **Must NOT do**:
  - 不删除原有的工作流说明 (仅更新补充)

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: 文档更新任务
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential
  - **Blocks**: None
  - **Blocked By**: Task 1, 2, 3

  **References**:
  - `src/README` - 现有文档

  **Acceptance Criteria**:
  - [ ] README 包含正确的文件路径引用
  - [ ] README 说明正确的工作流顺序

  **QA Scenarios**:

  ```
  Scenario: README 验证
    Tool: Bash
    Preconditions: SSH 连接
    Steps:
      1. ssh cpu.tj.th-3k.dkvpn "cat /thfs4/home/xuyong/zeng/00.B-comp/01.sigma-flow/src/README"
      2. 验证包含正确的工作流说明
    Expected Result: README 内容正确
    Failure Indicators: README 仍包含过时的路径或步骤
    Evidence: .sisyphus/evidence/task-4-readme.txt
  ```

  **Commit**: YES
  - Message: `docs: update README with correct workflow and file descriptions`
  - Files: `src/README`
  - Pre-commit: 无

---

## Final Verification Wave

- [ ] F1. **路径修复验证** — `quick`
  在所有修复完成后，运行 `grep -r "sigma-bonding"` 确认无残留引用

- [ ] F2. **脚本完整性验证** — `quick`
  确认所有保留的脚本可被读取且语法正确

- [ ] F3. **文档一致性验证** — `quick`
  确认 README 中的说明与实际文件结构一致

---

## Commit Strategy

- **Commit 1**: `fix: correct path references from sigma-bonding to 01.sigma-flow`
- **Commit 2**: `chore: remove duplicate sigma_bond_group.slurm`
- **Commit 3**: `chore: deprecate 03.gen_dft_dir.sh in favor of 04.gen_dft_dir_quick.sh`
- **Commit 4**: `docs: update README with correct workflow and file descriptions`

---

## Success Criteria

### 验证命令
```bash
# 验证无残留路径
ssh cpu.tj.th-3k.dkvpn "grep -r 'sigma-bonding' /thfs4/home/xuyong/zeng/00.B-comp/01.sigma-flow/"

# 验证文件结构
ssh cpu.tj.th-3k.dkvpn "ls -la /thfs4/home/xuyong/zeng/00.B-comp/01.sigma-flow/"
```

### 最终检查
- [ ] 所有 `sigma-bonding` 路径已修正为 `01.sigma-flow`
- [ ] `sigma_bond_group.slurm` 已删除
- [ ] `03.gen_dft_dir.sh` 已废弃或删除
- [ ] README 已更新
