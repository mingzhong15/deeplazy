# Plan: Analyze H0/HNL/HVNA/hamiltonians Matrix Components

## TL;DR

> **Quick Summary**: Create analysis script for Hamiltonian component matrices and run on remote server
> 
> **Deliverables**:
> - Modified `analyze_hcomponent.py` script
> - Upload to remote server
> - Run analysis and generate plots/statistics
> 
> **Estimated Effort**: Quick
> **Parallel Execution**: NO - sequential steps
> **Critical Path**: Write script → Upload → Run

---

## Context

### Original Request
用户希望基于 `/public/home/mind/zeng/github/deeplazy/scripts/analyze_hamiltonian.py` 创建新脚本，分析 H0/HNL/HVNA/hamiltonians 四个 HDF5 文件的矩阵元素，区分对角元和非对角元。

### Available Data
- **Location**: `/thfs4/home/xuyong/zeng/06.xc/00.output-test/test-hcomponent-single-final/output/`
- **Files**: H0.h5, HNL.h5, HVNA.h5, hamiltonians.h5, lat.dat, site_positions.dat, info.json
- **System**: Mo2B8, 18 atoms

---

## Work Objectives

### Core Objective
Create analysis script to compare H components (H0=kinetic, HNL=nonlocal, HVNA=VNA, H=total)

### Concrete Deliverables
1. `analyze_hcomponent.py` script in `/public/home/mind/zeng/github/deeplazy/scripts/`
2. Upload to remote server `/thfs4/home/xuyong/script/`
3. Run analysis on remote server
4. Generate statistics JSON and PNG plots

### Definition of Done
- [ ] Script created and uploaded
- [ ] Analysis executed successfully
- [ ] Statistics saved to JSON
- [ ] Histograms generated

---

## Execution Strategy

### Sequential Steps

```
Step 1: Write script locally (analyze_hcomponent.py)
Step 2: Upload to remote server
Step 3: Run analysis on remote
Step 4: Download results
```

---

## TODOs

- [ ] 1. Create analyze_hcomponent.py script

  **What to do**:
  - Based on analyze_hamiltonian.py
  - Support reading H0.h5, HNL.h5, HVNA.h5, hamiltonians.h5
  - Separate onsite (Hii) diagonal/offdiagonal analysis
  - Separate hopping (Hij) by distance bins
  - Generate comparison plots
  - Output statistics JSON

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple script modification task
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential
  - **Blocks**: Task 2
  - **Blocked By**: None

  **Acceptance Criteria**:
  - [ ] Script reads all 4 H5 files
  - [ ] Computes onsite diagonal/offdiagonal statistics
  - [ ] Computes hopping by distance bins
  - [ ] Generates comparison plots
  - [ ] Saves statistics.json

  **QA Scenarios**:
  ```
  Scenario: Script runs without error
    Tool: Bash
    Steps:
      1. python analyze_hcomponent.py --help
    Expected Result: Shows help message
  ```

  **Commit**: NO

- [ ] 2. Upload script to remote server

  **What to do**:
  - Use scp to upload to `/thfs4/home/xuyong/script/analyze_hcomponent.py`
  - Verify upload success

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential
  - **Blocks**: Task 3
  - **Blocked By**: Task 1

  **QA Scenarios**:
  ```
  Scenario: File uploaded successfully
    Tool: Bash (ssh)
    Steps:
      1. ssh cpu.tj.th-3k.dkvpn "ls -la /thfs4/home/xuyong/script/analyze_hcomponent.py"
    Expected Result: File exists with correct size
  ```

- [ ] 3. Run analysis on remote server

  **What to do**:
  - SSH to remote
  - Run: `python /thfs4/home/xuyong/script/analyze_hcomponent.py -i /thfs4/home/xuyong/zeng/06.xc/00.output-test/test-hcomponent-single-final/output -o ./hcomponent_analysis`
  - Verify output files created

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential
  - **Blocks**: Task 4
  - **Blocked By**: Task 2

  **QA Scenarios**:
  ```
  Scenario: Analysis completes
    Tool: Bash (ssh)
    Steps:
      1. Run python script
      2. Check for statistics.json output
    Expected Result: statistics.json exists with valid content
  ```

- [ ] 4. Download and present results

  **What to do**:
  - Download statistics.json and key plots
  - Present summary to user

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential
  - **Blocks**: None
  - **Blocked By**: Task 3

  **Commit**: NO

---

## Success Criteria

### Verification Commands
```bash
# Check script exists
ls -la /public/home/mind/zeng/github/deeplazy/scripts/analyze_hcomponent.py

# Check remote results
ssh cpu.tj.th-3k.dkvpn "ls -la /thfs4/home/xuyong/zeng/06.xc/00.output-test/test-hcomponent-single-final/output/hcomponent_analysis/"
```

### Final Checklist
- [ ] Script created
- [ ] Script uploaded to remote
- [ ] Analysis executed
- [ ] Results presented
