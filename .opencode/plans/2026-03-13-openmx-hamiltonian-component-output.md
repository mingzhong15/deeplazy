# OpenMX Hamiltonian Component Output Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional output for Hamiltonian components (H0, HNL, HVNA) to OpenMX `.scfout` binary file, enabling machine learning of SCF-dependent terms.

**Architecture:** Modify `SCF2File.c` to output additional Hamiltonian components (H0, HNL, HVNA) after existing data. Add input parameter `Hamiltonian.Components.Output` to control output. Modify `read_scfout.c` to read the new components. No new dependencies required.

**Tech Stack:** C, MPI, OpenMX 3.9.9

**Remote Server:** cpu.tj.th-3k.dkvpn  
**OpenMX Source Path:** /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/

---

## File Structure

### Files to Modify (on remote server)
```
/thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/
├── openmx_common.h    # Add control variable
├── Input_std.c        # Add input parameter parsing
├── SCF2File.c         # Add H0, HNL, HVNA output
├── read_scfout.h      # Add new variable declarations
└── read_scfout.c      # Add reading of new components
```

### No New Files Required
沿用现有二进制格式，输出到 `.scfout` 文件末尾。

### Output Data Order (modified `.scfout`)
```
=== Existing Output ===
1. Header (atomnum, SpinP_switch, etc.)
2. Connectivity (atv, FNAN, natn, ncn, etc.)
3. H[spin]           - Total Hamiltonian
4. iHNL[spin]        - Imaginary nonlocal (non-collinear only)
5. OLP[0]            - Overlap matrix
6. OLPpo, OLPmo      - Position/momentum operators
7. DM, iDM           - Density matrix
8. Footer (ChemP, E_Temp, input file)

=== New Output (when Hamiltonian.Components.Output=on) ===
9. H0                - Kinetic energy (spin-independent)
10. HNL[spin]        - Nonlocal pseudopotential real part
11. HVNA             - VNA potential (spin-independent)
```

---

## Chunk 1: Control Variable and Input Parameter

### Task 1.1: Add control variable to openmx_common.h

**Files:**
- Modify: `/thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/openmx_common.h`

- [ ] **Step 1: Find appropriate location for new variable**

Run: `ssh cpu.tj.th-3k.dkvpn "grep -n 'level_fileout' /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/openmx_common.h | head -3"`

- [ ] **Step 2: Add the control variable**

After the `level_fileout` related declaration, add:
```c
/* Hamiltonian component output control */
extern int H_Component_Output;   /* 0: off (default), 1: on */
```

> **Note:** Use `extern` (not `static`) to avoid each .c file having its own copy.

- [ ] **Step 3: Verify modification**

Run: `ssh cpu.tj.th-3k.dkvpn "grep -n 'H_Component_Output' /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/openmx_common.h"`

- [ ] **Step 4: Commit**

```bash
ssh cpu.tj.th-3k.dkvpn "cd /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source && git add openmx_common.h && git commit -m 'feat: add H_Component_Output control variable'"
```

---

### Task 1.2: Add input parameter in Input_std.c

**Files:**
- Modify: `/thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/Input_std.c`

- [ ] **Step 1: Find location for similar input parsing**

Run: `ssh cpu.tj.th-3k.dkvpn "grep -n 'level.of.fileout' /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/Input_std.c | head -3"`

- [ ] **Step 2: Add the input parameter parsing**

After the `input_int("level.of.fileout",...)` line, add:
```c
  /* Hamiltonian component output for machine learning */
  input_int("Hamiltonian.Components.Output", &H_Component_Output, 0);
```

> **Note:** The variable definition (not extern) should be added in Input_std.c:
> ```c
> int H_Component_Output = 0;  /* definition */
> ```

- [ ] **Step 3: Verify modification**

Run: `ssh cpu.tj.th-3k.dkvpn "grep -n 'Hamiltonian.Components' /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/Input_std.c"`

- [ ] **Step 4: Commit**

```bash
ssh cpu.tj.th-3k.dkvpn "cd /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source && git add Input_std.c && git commit -m 'feat: add Hamiltonian.Components.Output input parameter'"
```

---

## Chunk 2: Modify SCF2File.c for Output

### Task 2.1: Add H0 output in SCF2File.c

**Files:**
- Modify: `/thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/SCF2File.c`

- [ ] **Step 1: Find where to add new output**

Run: `ssh cpu.tj.th-3k.dkvpn "grep -n 'density matrix\|DM and iDM' /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/SCF2File.c | head -5"`

- [ ] **Step 2: Read the DM output section for reference**

Run: `ssh cpu.tj.th-3k.dkvpn "sed -n '700,800p' /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/SCF2File.c"`

- [ ] **Step 3: Add H0 output after iDM output**

After the iDM output block, before the "Solver" output, add:
```c
  /***************************************************************
      H0: kinetic energy matrix (component 0 only)
      Note: H0 is a 5D array H0[k][Mc_AN][h_AN][i][j]
            k=0: main kinetic+VNL matrix (used in Hamiltonian)
            k=1,2,3: spatial derivatives (used in force calculations)
            H0 is spin-independent, so only H0[0] is output
  ****************************************************************/

  if (H_Component_Output == 1) {

    for (Gc_AN=1; Gc_AN<=atomnum; Gc_AN++){
      ID = G2ID[Gc_AN];

      if (myid==ID){

        num = 0;
        Mc_AN = F_G2M[Gc_AN];
        wan1 = WhatSpecies[Gc_AN];
        TNO1 = Spe_Total_CNO[wan1];
        for (h_AN=0; h_AN<=FNAN[Gc_AN]; h_AN++){
          Gh_AN = natn[Gc_AN][h_AN];
          wan2 = WhatSpecies[Gh_AN];
          TNO2 = Spe_Total_CNO[wan2];

          for (i=0; i<TNO1; i++){
            for (j=0; j<TNO2; j++){
              Tmp_Vec[num] = H0[0][Mc_AN][h_AN][i][j];
              num++;
            }
          }
        }

        if (myid!=Host_ID){
          MPI_Isend(&num, 1, MPI_INT, Host_ID, tag, mpi_comm_level1, &request);
          MPI_Wait(&request,&stat);
          MPI_Isend(&Tmp_Vec[0], num, MPI_DOUBLE, Host_ID, tag, mpi_comm_level1, &request);
          MPI_Wait(&request,&stat);
        }
        else{
          fwrite(Tmp_Vec, sizeof(double), num, fp);
        }
      }

      else if (ID!=myid && myid==Host_ID){
        MPI_Recv(&num, 1, MPI_INT, ID, tag, mpi_comm_level1, &stat);
        MPI_Recv(&Tmp_Vec[0], num, MPI_DOUBLE, ID, tag, mpi_comm_level1, &stat);
        fwrite(Tmp_Vec, sizeof(double), num, fp);
      }
    }

    if (myid==Host_ID){
      printf("  H0 (kinetic energy) written to scfout\n");
    }
  }
```

- [ ] **Step 4: Commit**

```bash
ssh cpu.tj.th-3k.dkvpn "cd /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source && git add SCF2File.c && git commit -m 'feat: add H0 output to scfout'"
```

---

### Task 2.2: Add HNL output in SCF2File.c

**Files:**
- Modify: `/thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/SCF2File.c`

- [ ] **Step 1: Add HNL output after H0 output**

```c
  /***************************************************************
      HNL: nonlocal pseudopotential (spin-dependent)
      Note: HNL size is List_YOUSO[5], NOT SpinP_switch+1!
            SpinP_switch=0: List_YOUSO[5]=1 (HNL[0])
            SpinP_switch=1: List_YOUSO[5]=2 (HNL[0,1])
            SpinP_switch=3: List_YOUSO[5]=3 (HNL[0,1,2])
            HNL[0]=up-up, HNL[1]=dn-dn, HNL[2]=up-dn
  ****************************************************************/

  if (H_Component_Output == 1) {

    for (spin=0; spin<List_YOUSO[5]; spin++){  /* CRITICAL: Use List_YOUSO[5], not SpinP_switch+1 */

      for (Gc_AN=1; Gc_AN<=atomnum; Gc_AN++){
        ID = G2ID[Gc_AN];

        if (myid==ID){

          num = 0;
          Mc_AN = F_G2M[Gc_AN];
          wan1 = WhatSpecies[Gc_AN];
          TNO1 = Spe_Total_CNO[wan1];
          for (h_AN=0; h_AN<=FNAN[Gc_AN]; h_AN++){
            Gh_AN = natn[Gc_AN][h_AN];
            wan2 = WhatSpecies[Gh_AN];
            TNO2 = Spe_Total_CNO[wan2];

            for (i=0; i<TNO1; i++){
              for (j=0; j<TNO2; j++){
                Tmp_Vec[num] = HNL[spin][Mc_AN][h_AN][i][j];
                num++;
              }
            }
          }

          if (myid!=Host_ID){
            MPI_Isend(&num, 1, MPI_INT, Host_ID, tag, mpi_comm_level1, &request);
            MPI_Wait(&request,&stat);
            MPI_Isend(&Tmp_Vec[0], num, MPI_DOUBLE, Host_ID, tag, mpi_comm_level1, &request);
            MPI_Wait(&request,&stat);
          }
          else{
            fwrite(Tmp_Vec, sizeof(double), num, fp);
          }
        }

        else if (ID!=myid && myid==Host_ID){
          MPI_Recv(&num, 1, MPI_INT, ID, tag, mpi_comm_level1, &stat);
          MPI_Recv(&Tmp_Vec[0], num, MPI_DOUBLE, ID, tag, mpi_comm_level1, &stat);
          fwrite(Tmp_Vec, sizeof(double), num, fp);
        }
      }
    }

    if (myid==Host_ID){
      printf("  HNL (nonlocal pseudopotential) written to scfout\n");
    }
  }
```

- [ ] **Step 2: Commit**

```bash
ssh cpu.tj.th-3k.dkvpn "cd /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source && git add SCF2File.c && git commit -m 'feat: add HNL output to scfout'"
```

---

### Task 2.3: Add HVNA output in SCF2File.c

**Files:**
- Modify: `/thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/SCF2File.c`

- [ ] **Step 1: Add HVNA output after HNL output**

```c
  /***************************************************************
      HVNA: VNA potential (spin-independent)
  ****************************************************************/

  if (H_Component_Output == 1) {

    for (Gc_AN=1; Gc_AN<=atomnum; Gc_AN++){
      ID = G2ID[Gc_AN];

      if (myid==ID){

        num = 0;
        Mc_AN = F_G2M[Gc_AN];
        wan1 = WhatSpecies[Gc_AN];
        TNO1 = Spe_Total_CNO[wan1];
        for (h_AN=0; h_AN<=FNAN[Gc_AN]; h_AN++){
          Gh_AN = natn[Gc_AN][h_AN];
          wan2 = WhatSpecies[Gh_AN];
          TNO2 = Spe_Total_CNO[wan2];

          for (i=0; i<TNO1; i++){
            for (j=0; j<TNO2; j++){
              Tmp_Vec[num] = HVNA[Mc_AN][h_AN][i][j];
              num++;
            }
          }
        }

        if (myid!=Host_ID){
          MPI_Isend(&num, 1, MPI_INT, Host_ID, tag, mpi_comm_level1, &request);
          MPI_Wait(&request,&stat);
          MPI_Isend(&Tmp_Vec[0], num, MPI_DOUBLE, Host_ID, tag, mpi_comm_level1, &request);
          MPI_Wait(&request,&stat);
        }
        else{
          fwrite(Tmp_Vec, sizeof(double), num, fp);
        }
      }

      else if (ID!=myid && myid==Host_ID){
        MPI_Recv(&num, 1, MPI_INT, ID, tag, mpi_comm_level1, &stat);
        MPI_Recv(&Tmp_Vec[0], num, MPI_DOUBLE, ID, tag, mpi_comm_level1, &stat);
        fwrite(Tmp_Vec, sizeof(double), num, fp);
      }
    }

    if (myid==Host_ID){
      printf("  HVNA (VNA potential) written to scfout\n");
    }
  }
```

- [ ] **Step 2: Commit**

```bash
ssh cpu.tj.th-3k.dkvpn "cd /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source && git add SCF2File.c && git commit -m 'feat: add HVNA output to scfout'"
```

---

## Chunk 3: Modify read_scfout for Reading

### Task 3.1: Add variable declarations in read_scfout.h

**Files:**
- Modify: `/thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/read_scfout.h`

- [ ] **Step 1: Add new variable declarations**

```c
/* Hamiltonian components for machine learning */
extern double *H0_scfout;
extern double *HNL_scfout;
extern double *HVNA_scfout;
extern int H_Component_Output_flag;
```

- [ ] **Step 2: Commit**

```bash
ssh cpu.tj.th-3k.dkvpn "cd /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source && git add read_scfout.h && git commit -m 'feat: add Hamiltonian component variables to read_scfout.h'"
```

---

### Task 3.2: Add reading logic in read_scfout.c

**Files:**
- Modify: `/thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/read_scfout.c`

- [ ] **Step 1: Add variable definitions**

```c
/* Hamiltonian components */
double *H0_scfout;
double *HNL_scfout;
double *HVNA_scfout;
int H_Component_Output_flag = 0;
```

- [ ] **Step 2: Add reading logic before fclose(fp)**

```c
  /* Try to read H0, HNL, HVNA */
  {
    int total_size = 0;
    size_t read_size;
    int num_HNL_spin;  /* HNL spin count = List_YOUSO[5] */
    
    /* Determine HNL spin count from SpinP_switch (same logic as Input_std.c) */
    if      (SpinP_switch_scfout==0) num_HNL_spin = 1;
    else if (SpinP_switch_scfout==1) num_HNL_spin = 2;
    else                             num_HNL_spin = 3;  /* SpinP_switch==3 */
    
    /* Calculate total matrix size */
    for (ct_AN=1; ct_AN<=atomnum; ct_AN++){
      wan1 = WhatSpecies_scfout[ct_AN];
      TNO1 = Spe_Total_CNO_scfout[wan1];
      for (h_AN=0; h_AN<=FNAN_scfout[ct_AN]; h_AN++){
        Gh_AN = natn_scfout[ct_AN][h_AN];
        wan2 = WhatSpecies_scfout[Gh_AN];
        TNO2 = Spe_Total_CNO_scfout[wan2];
        total_size += TNO1 * TNO2;
      }
    }
    
    /* Try to read H0 */
    H0_scfout = (double*)malloc(sizeof(double) * total_size);
    read_size = fread(H0_scfout, sizeof(double), total_size, fp);
    
    if (read_size == total_size) {
      H_Component_Output_flag = 1;
      printf("  H0 read from scfout\n");
      
      /* Read HNL (CRITICAL: use num_HNL_spin, not SpinP_switch_scfout+1) */
      HNL_scfout = (double*)malloc(sizeof(double) * total_size * num_HNL_spin);
      for (spin=0; spin<num_HNL_spin; spin++){
        fread(HNL_scfout + spin*total_size, sizeof(double), total_size, fp);
      }
      printf("  HNL read from scfout (%d spin components)\n", num_HNL_spin);
      
      /* Read HVNA */
      HVNA_scfout = (double*)malloc(sizeof(double) * total_size);
      fread(HVNA_scfout, sizeof(double), total_size, fp);
      printf("  HVNA read from scfout\n");
    } else {
      H_Component_Output_flag = 0;
      free(H0_scfout);
      H0_scfout = NULL;
    }
  }
```

- [ ] **Step 3: Commit**

```bash
ssh cpu.tj.th-3k.dkvpn "cd /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source && git add read_scfout.c && git commit -m 'feat: add Hamiltonian component reading'"
```

---

## Chunk 4: Compilation and Testing

### Task 4.1: Compile and test

- [ ] **Step 1: Compile**

```bash
ssh cpu.tj.th-3k.dkvpn "cd /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source && make clean && make openmx 2>&1 | tail -20"
```

- [ ] **Step 2: Create test input with `Hamiltonian.Components.Output on`**

- [ ] **Step 3: Run test and verify H0/HNL/HVNA output**

- [ ] **Step 4: Test read_scfout reads components correctly**

---

## Summary

| File | Lines Added |
|------|-------------|
| openmx_common.h | +1 |
| Input_std.c | +1 |
| SCF2File.c | +~120 |
| read_scfout.h | +4 |
| read_scfout.c | +~40 |

**No new files, no new dependencies.**

---

## Data Flow Verification (2026-03-13)

### Key Findings from Subagent Analysis

| Variable | Type | Dimensions | Spin Index | Atom Index |
|----------|------|------------|------------|------------|
| **H** (total) | `double *****` | `[spin][Mc_AN][h_AN][i][j]` | `0..SpinP_switch` | Mc_AN |
| **H0** (kinetic) | `double *****` | `[k][Mc_AN][h_AN][i][j]` | ❌ No spin (k=component) | Mc_AN |
| **HNL** (nonlocal) | `double *****` | `[spin][Mc_AN][h_AN][i][j]` | `0..List_YOUSO[5]-1` | Mc_AN |
| **HVNA** (VNA) | `double ****` | `[Mc_AN][h_AN][i][j]` | ❌ No spin | Mc_AN |

### Critical Bugs Fixed

1. **HNL spin loop bug**: Changed `spin<=SpinP_switch` to `spin<List_YOUSO[5]`
   - SpinP_switch=3 means `spin<=3` (4 iterations), but HNL has only 3 elements!
   - H[3] exists but HNL[3] does not → array out-of-bounds

2. **Variable declaration bug**: Changed `static` to `extern`
   - `static` in header creates separate copies per .c file
   - `extern` + definition in Input_std.c ensures single global variable

3. **H0 clarification**: First dimension is component type, not spin
   - H0[0] = main kinetic matrix (used in Hamiltonian)
   - H0[1,2,3] = spatial derivatives (used in force calculations)
   - Only H0[0] should be output

### HNL Spin Count Reference

| SpinP_switch | List_YOUSO[5] | HNL indices | H indices |
|--------------|---------------|-------------|-----------|
| 0 (off) | 1 | HNL[0] | H[0] |
| 1 (collinear) | 2 | HNL[0,1] | H[0,1] |
| 3 (non-collinear) | 3 | HNL[0,1,2] | H[0,1,2,3] |

### Output Format Matches H (verified)

All three components (H0, HNL, HVNA) use the same MPI gather-to-host pattern as H:
- Loop: `for(Gc_AN=1; Gc_AN<=atomnum; Gc_AN++)`
- Convert: `Mc_AN = F_G2M[Gc_AN]`
- Pack: `for(h_AN) for(i) for(j) Tmp_Vec[num++] = Array[...][Mc_AN][h_AN][i][j]`
- MPI: Owner sends to Host_ID, Host_ID writes to file

---

Plan verified and ready to execute.
