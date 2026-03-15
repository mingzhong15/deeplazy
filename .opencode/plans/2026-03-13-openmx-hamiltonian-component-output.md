# OpenMX Hamiltonian Component Output Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional output for Hamiltonian components (H0, HNL, HVNA) to OpenMX `.scfout` binary file, enabling machine learning of SCF-dependent terms.

**Architecture:** Modify `SCF2File.c` to output additional Hamiltonian components after existing data. Add input parameter `Hamiltonian.Components.Output` to control output. Create `openmx_get_data_ext.jl` to read the new components. No modifications to `read_scfout.c` (OpenMX's built-in post-processing tools).

**Tech Stack:** C, MPI, OpenMX 3.9.9, Julia

**Remote Server:** cpu.tj.th-3k.dkvpn  
**OpenMX Source Path:** /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/
**Julia Script Path:** /thfs4/home/xuyong/script/

---

## Backward Compatibility Guarantee

| Scenario | Behavior |
|----------|----------|
| User does NOT set `Hamiltonian.Components.Output` | ✅ Identical to original OpenMX, no extra output |
| User sets `Hamiltonian.Components.Output on` | ✅ New format file with extra data appended at end |
| New `openmx_get_data_ext.jl` reads old `.scfout` | ✅ Detects missing data via fread return, skips |
| Old `openmx_get_data.jl` reads new `.scfout` | ✅ Only reads known data, ignores extra at end |
| Old OpenMX tools read new `.scfout` | ✅ Works normally, ignores extra data |

**Key:** Extra data is APPENDED after all existing data. No version change required.

---

## File Structure

### Files to Modify (on remote server)
```
/thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/
├── openmx_common.h    # Add control variable (follow existing pattern)
├── Input_std.c        # Add input parameter parsing + variable definition
└── SCF2File.c         # Add H0, HNL, HVNA output with Cnt_switch handling
```

### Files to Create
```
/thfs4/home/xuyong/script/
└── openmx_get_data_ext.jl  # Extended Julia script for H0/HNL/HVNA extraction
```

### Files NOT Modified
```
read_scfout.h  # Not needed - OpenMX's built-in tools don't need H0/HNL/HVNA
read_scfout.c  # Not needed - custom Julia script handles the reading
```

### Output Data Order (modified `.scfout`)
```
=== Existing Output (unchanged) ===
1. Header (atomnum, SpinP_switch, etc.)
2. Connectivity (atv, FNAN, natn, ncn, etc.)
3. H[spin]           - Total Hamiltonian
4. iHNL[spin]        - Imaginary nonlocal (non-collinear only)
5. OLP[0]            - Overlap matrix
6. OLPpo, OLPmo      - Position/momentum operators
7. DM, iDM           - Density matrix
8. Footer (ChemP, E_Temp, input file)

=== New Output (appended when Hamiltonian.Components.Output=on) ===
9. H0                - Kinetic energy (spin-independent, component 0)
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

- [ ] **Step 2: Add the control variable (follow existing pattern)**

Find the line like:
```c
int Num_Mixing_pDM,level_stdout,level_fileout,HS_fileout;
```

Add `H_Component_Output` to this line:
```c
int Num_Mixing_pDM,level_stdout,level_fileout,HS_fileout,H_Component_Output;
```

> **Note:** Follow the existing pattern - define directly in header (not extern). This is OpenMX's convention.

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

The default value is `0` (off), ensuring backward compatibility.

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

- [ ] **Step 1: Find insertion point (after iDM output)**

Run: `ssh cpu.tj.th-3k.dkvpn "grep -n 'iDM\|density matrix' /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/SCF2File.c | head -10"`

- [ ] **Step 2: Add H0 output after iDM output block**

```c
  /***************************************************************
      H0: kinetic energy matrix (component 0 only)
      Note: H0 is a 5D array H0[k][Mc_AN][h_AN][i][j]
            k=0: main kinetic+VNL matrix (used in Hamiltonian)
            k=1,2,3: spatial derivatives (used in force calculations)
            H0 is spin-independent, so only H0[0] is output
            
      Cnt_switch handling: Use CntH0 when Cnt_switch==1
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

          if (Cnt_switch==0){
            for (i=0; i<TNO1; i++){
              for (j=0; j<TNO2; j++){
                Tmp_Vec[num] = H0[0][Mc_AN][h_AN][i][j];
                num++;
              }
            }
          }
          else{
            for (i=0; i<TNO1; i++){
              for (j=0; j<TNO2; j++){
                Tmp_Vec[num] = CntH0[0][Mc_AN][h_AN][i][j];
                num++;
              }
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

- [ ] **Step 3: Commit**

```bash
ssh cpu.tj.th-3k.dkvpn "cd /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source && git add SCF2File.c && git commit -m 'feat: add H0 output to scfout with Cnt_switch support'"
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
            
      No Cnt_switch handling: HNL has no contracted version
      (only iHNL has iCntHNL)
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
      printf("  HNL (nonlocal pseudopotential) written to scfout (%d spin components)\n", List_YOUSO[5]);
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
      Note: HVNA is a 4D array HVNA[Mc_AN][h_AN][i][j]
            No spin dimension - VNA is spin-independent
            
      Cnt_switch handling: Use CntHVNA2 when Cnt_switch==1
      (CntHVNA without number does not exist, use CntHVNA2)
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

          if (Cnt_switch==0){
            for (i=0; i<TNO1; i++){
              for (j=0; j<TNO2; j++){
                Tmp_Vec[num] = HVNA[Mc_AN][h_AN][i][j];
                num++;
              }
            }
          }
          else{
            for (i=0; i<TNO1; i++){
              for (j=0; j<TNO2; j++){
                Tmp_Vec[num] = CntHVNA2[0][Mc_AN][h_AN][i][j];
                num++;
              }
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
ssh cpu.tj.th-3k.dkvpn "cd /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source && git add SCF2File.c && git commit -m 'feat: add HVNA output to scfout with Cnt_switch support'"
```

---

## Chunk 3: Create openmx_get_data_ext.jl

### Task 3.1: Create extended Julia script

**Files:**
- Create: `/thfs4/home/xuyong/script/openmx_get_data_ext.jl`

- [ ] **Step 1: Read original script for reference**

Run: `ssh cpu.tj.th-3k.dkvpn "cat /thfs4/home/xuyong/script/openmx_get_data.jl"`

- [ ] **Step 2: Create openmx_get_data_ext.jl**

Based on `openmx_get_data.jl`, extend it to:
1. Parse existing data (H, OLP, DM, etc.)
2. After parsing all existing data, try to read H0/HNL/HVNA
3. Use fread return value to detect if data exists (backward compatible)
4. Output additional HDF5 files: `H0.h5`, `HNL.h5`, `HVNA.h5`

See detailed implementation in Task 3.2.

- [ ] **Step 3: Test with old and new format files**

---

### Task 3.2: openmx_get_data_ext.jl Implementation

```julia
#!/usr/bin/env julia
#
# openmx_get_data_ext.jl
# Extended version of openmx_get_data.jl with H0/HNL/HVNA extraction
#
# Usage: julia openmx_get_data_ext.jl <scfout_file> [output_dir]
#
# Output files:
#   - hamiltonians.h5 (existing)
#   - overlaps.h5 (existing)
#   - H0.h5 (new)
#   - HNL.h5 (new)
#   - HVNA.h5 (new)
#   - ... other existing outputs
#

using HDF5
using JSON

# ============================================================
# Include all functions from original openmx_get_data.jl
# ============================================================

# [Copy all helper functions from openmx_get_data.jl]
# multiread, read_matrix_in_mixed_matrix, etc.

# ============================================================
# New functions for H0/HNL/HVNA extraction
# ============================================================

"""
Calculate total matrix size for H0/HNL/HVNA storage.
This is the sum of all (TNO1 * TNO2) for each atom-neighbor pair.
"""
function calculate_total_matrix_size(atomnum, FNAN, natn, Total_NumOrbs)
    total_size = 0
    for ct_AN in 1:atomnum
        TNO1 = Total_NumOrbs[ct_AN]
        for h_AN in 0:FNAN[ct_AN]
            Gh_AN = natn[ct_AN][h_AN+1]  # Julia is 1-indexed
            TNO2 = Total_NumOrbs[Gh_AN]
            total_size += TNO1 * TNO2
        end
    end
    return total_size
end

"""
Determine number of HNL spin components from SpinP_switch.
Matches OpenMX's List_YOUSO[5] logic.
"""
function get_num_HNL_spin(SpinP_switch)
    if SpinP_switch == 0
        return 1
    elseif SpinP_switch == 1
        return 2
    else  # SpinP_switch == 3
        return 3
    end
end

"""
Try to read H0, HNL, HVNA from scfout file.
Returns (H0, HNL, HVNA, has_components) where has_components is true if read succeeded.
"""
function try_read_H_components(f, atomnum, SpinP_switch, FNAN, natn, Total_NumOrbs)
    total_size = calculate_total_matrix_size(atomnum, FNAN, natn, Total_NumOrbs)
    num_HNL_spin = get_num_HNL_spin(SpinP_switch)
    
    # Try to read H0
    H0_raw = Vector{Float64}(undef, total_size)
    n_read = read!(f, H0_raw)
    
    if n_read < total_size
        # Old format file - no H0/HNL/HVNA data
        return nothing, nothing, nothing, false
    end
    
    # Successfully read H0, now read HNL
    HNL_raw = Vector{Float64}(undef, total_size * num_HNL_spin)
    read!(f, HNL_raw)
    
    # Read HVNA
    HVNA_raw = Vector{Float64}(undef, total_size)
    read!(f, HVNA_raw)
    
    return H0_raw, HNL_raw, HVNA_raw, true
end

"""
Convert raw H0/HNL/HVNA data to same format as hamiltonians dict.
Key: [Rx, Ry, Rz, site_i, site_j] -> Matrix
"""
function convert_H_components_to_dict(H0_raw, HNL_raw, HVNA_raw, 
                                       atomnum, FNAN, natn, ncn, 
                                       Total_NumOrbs, atv_ijk, num_HNL_spin)
    H0_dict = Dict{Vector{Int64}, Matrix{Float64}}()
    HNL_dict = Dict{Vector{Int64}, Vector{Matrix{Float64}}}()  # Multiple spin components
    HVNA_dict = Dict{Vector{Int64}, Matrix{Float64}}()
    
    offset = 0
    for ct_AN in 1:atomnum
        TNO1 = Total_NumOrbs[ct_AN]
        for h_AN in 0:FNAN[ct_AN]
            Gh_AN = natn[ct_AN][h_AN+1]
            TNO2 = Total_NumOrbs[Gh_AN]
            block_size = TNO1 * TNO2
            
            # Get lattice vector R
            nc_idx = ncn[ct_AN][h_AN+1]
            R = atv_ijk[:, nc_idx]
            
            # Key for this block
            key = vcat(R, [ct_AN, Gh_AN])
            
            # Extract H0 block
            H0_block = reshape(H0_raw[offset+1:offset+block_size], TNO2, TNO1)
            H0_dict[key] = H0_block
            
            # Extract HNL blocks for each spin
            HNL_blocks = Vector{Matrix{Float64}}(undef, num_HNL_spin)
            for spin in 1:num_HNL_spin
                spin_offset = (spin - 1) * length(H0_raw) + offset
                HNL_blocks[spin] = reshape(HNL_raw[spin_offset+1:spin_offset+block_size], TNO2, TNO1)
            end
            HNL_dict[key] = HNL_blocks
            
            # Extract HVNA block
            HVNA_block = reshape(HVNA_raw[offset+1:offset+block_size], TNO2, TNO1)
            HVNA_dict[key] = HVNA_block
            
            offset += block_size
        end
    end
    
    return H0_dict, HNL_dict, HVNA_dict
end

"""
Save H0/HNL/HVNA to HDF5 files.
"""
function save_H_components(H0_dict, HNL_dict, HVNA_dict, output_dir)
    # Save H0
    h5open(joinpath(output_dir, "H0.h5"), "w") do f
        for (key, mat) in H0_dict
            key_str = string(key)
            f[key_str] = mat
        end
    end
    
    # Save HNL (with spin index in key)
    h5open(joinpath(output_dir, "HNL.h5"), "w") do f
        for (key, blocks) in HNL_dict
            for (spin, mat) in enumerate(blocks)
                key_str = string(vcat(key, [spin]))
                f[key_str] = mat
            end
        end
    end
    
    # Save HVNA
    h5open(joinpath(output_dir, "HVNA.h5"), "w") do f
        for (key, mat) in HVNA_dict
            key_str = string(key)
            f[key_str] = mat
        end
    end
end

# ============================================================
# Main function (extended from original)
# ============================================================

function main()
    # Parse arguments
    if length(ARGS) < 1
        println("Usage: julia openmx_get_data_ext.jl <scfout_file> [output_dir]")
        exit(1)
    end
    
    scfout_file = ARGS[1]
    output_dir = length(ARGS) >= 2 ? ARGS[2] : dirname(scfout_file)
    
    # Open and parse scfout file
    open(scfout_file, "r") do f
        # [Use existing parsing logic from openmx_get_data.jl]
        # This extracts: atomnum, SpinP_switch, Hk, OLP, DM, etc.
        
        # ... existing parsing code ...
        
        # After all existing parsing, try to read H0/HNL/HVNA
        println("Attempting to read H0/HNL/HVNA components...")
        
        H0_raw, HNL_raw, HVNA_raw, has_components = try_read_H_components(
            f, atomnum, SpinP_switch, FNAN, natn, Total_NumOrbs
        )
        
        if has_components
            println("Successfully read H0/HNL/HVNA from scfout")
            
            # Convert to dict format
            H0_dict, HNL_dict, HVNA_dict = convert_H_components_to_dict(
                H0_raw, HNL_raw, HVNA_raw,
                atomnum, FNAN, natn, ncn, Total_NumOrbs, atv_ijk, 
                get_num_HNL_spin(SpinP_switch)
            )
            
            # Save to HDF5
            save_H_components(H0_dict, HNL_dict, HVNA_dict, output_dir)
            println("Saved H0.h5, HNL.h5, HVNA.h5 to $output_dir")
        else
            println("No H0/HNL/HVNA found in scfout (old format or not enabled)")
        end
    end
    
    # [Continue with existing processing from openmx_get_data.jl]
    # ... existing code ...
end

main()
```

---

## Chunk 4: Compilation and Testing

### Task 4.1: Compile OpenMX

- [ ] **Step 1: Compile**

```bash
ssh cpu.tj.th-3k.dkvpn "cd /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source && make clean && make openmx 2>&1 | tail -30"
```

- [ ] **Step 2: Verify compilation success**

Check for errors in output.

---

### Task 4.2: Test backward compatibility

- [ ] **Step 1: Run OpenMX WITHOUT new parameter**

Create test input without `Hamiltonian.Components.Output`:
```bash
ssh cpu.tj.th-3k.dkvpn "cd /path/to/test && /thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/openmx test.dat"
```

Verify `.scfout` is identical to original.

- [ ] **Step 2: Run OpenMX WITH new parameter**

Add to input file:
```
Hamiltonian.Components.Output    on
```

Run and verify output contains H0/HNL/HVNA.

- [ ] **Step 3: Test Julia script**

```bash
julia /thfs4/home/xuyong/script/openmx_get_data_ext.jl test.scfout
```

Verify H0.h5, HNL.h5, HVNA.h5 are created.

- [ ] **Step 4: Test old format compatibility**

Run `openmx_get_data_ext.jl` on an old `.scfout` file (without H0/HNL/HVNA).
Verify it detects missing data and continues normally.

---

## Summary

### Files Modified

| File | Lines Changed | Purpose |
|------|---------------|---------|
| `openmx_common.h` | +1 | Add control variable |
| `Input_std.c` | +2 | Add input parameter |
| `SCF2File.c` | +~150 | Add H0/HNL/HVNA output |

### Files Created

| File | Purpose |
|------|---------|
| `openmx_get_data_ext.jl` | Extended Julia script for reading new components |

### Files NOT Modified

| File | Reason |
|------|--------|
| `read_scfout.h` | Not needed - OpenMX tools don't use H0/HNL/HVNA |
| `read_scfout.c` | Not needed - custom Julia script handles reading |

---

## Data Flow Verification (2026-03-13)

### Key Findings from Subagent Analysis

| Variable | Type | Dimensions | Spin Index | Atom Index |
|----------|------|------------|------------|------------|
| **H** (total) | `double *****` | `[spin][Mc_AN][h_AN][i][j]` | `0..SpinP_switch` | Mc_AN |
| **H0** (kinetic) | `double *****` | `[k][Mc_AN][h_AN][i][j]` | ❌ No spin (k=component) | Mc_AN |
| **HNL** (nonlocal) | `double *****` | `[spin][Mc_AN][h_AN][i][j]` | `0..List_YOUSO[5]-1` | Mc_AN |
| **HVNA** (VNA) | `double ****` | `[Mc_AN][h_AN][i][j]` | ❌ No spin | Mc_AN |

### Critical Details

1. **HNL spin loop**: Use `spin < List_YOUSO[5]` (NOT `spin <= SpinP_switch`)
2. **Cnt_switch handling**: H0 → H0/CntH0, HNL → no contracted version, HVNA → HVNA/CntHVNA2
3. **Variable declaration**: Follow OpenMX pattern - define directly in `openmx_common.h`

### HNL Spin Count Reference

| SpinP_switch | List_YOUSO[5] | HNL indices | H indices |
|--------------|---------------|-------------|-----------|
| 0 (off) | 1 | HNL[0] | H[0] |
| 1 (collinear) | 2 | HNL[0,1] | H[0,1] |
| 3 (non-collinear) | 3 | HNL[0,1,2] | H[0,1,2,3] |

### Output Format

All three components (H0, HNL, HVNA) use the same format as H:
- Loop order: `Gc_AN → h_AN → i → j`
- Index conversion: `Mc_AN = F_G2M[Gc_AN]`
- MPI: gather-to-host pattern
- Binary: `fwrite` of packed `double` array

---

## Chunk 5: Create openmx_get_data_ext.jl (Detailed Implementation)

### Task 5.1: Copy and extend original script

**Files:**
- Source: `/thfs4/home/xuyong/script/openmx_get_data.jl`
- Target: `/thfs4/home/xuyong/script/openmx_get_data_ext.jl`

- [ ] **Step 1: Copy original script**
```bash
ssh cpu.tj.th-3k.dkvpn "cp /thfs4/home/xuyong/script/openmx_get_data.jl /thfs4/home/xuyong/script/openmx_get_data_ext.jl"
```

- [ ] **Step 2: Add new command line argument**

In `parse_commandline()`, add:
```julia
@add_arg_table! s begin
    # ... existing arguments ...
    "--H_components", "-H"
        help = "Extract H0/HNL/HVNA components"
        arg_type = Bool
        default = false
end
```

- [ ] **Step 3: Modify parse_openmx() to return H components**

Add new return values after DM parsing. The key is to read H0/HNL/HVNA at the END of `parse_openmx()` function, just before `close(f)`.

**Critical: Binary reading must match SCF2File.c output order**

```
SCF2File.c output order:
  for Gc_AN = 1 to atomnum:
    for h_AN = 0 to FNAN[Gc_AN]:
      for i = 0 to TNO1-1:
        for j = 0 to TNO2-1:
          write H0[0][Mc_AN][h_AN][i][j]  (single component)
  
  for spin = 0 to List_YOUSO[5]-1:
    for Gc_AN = 1 to atomnum:
      for h_AN = 0 to FNAN[Gc_AN]:
        for i = 0 to TNO1-1:
          for j = 0 to TNO2-1:
            write HNL[spin][Mc_AN][h_AN][i][j]
  
  for Gc_AN = 1 to atomnum:
    for h_AN = 0 to FNAN[Gc_AN]:
      for i = 0 to TNO1-1:
        for j = 0 to TNO2-1:
          write HVNA[Mc_AN][h_AN][i][j]  (no spin)
```

**Julia reading order (1-indexed):**
```julia
# After all existing reads in parse_openmx()

# Calculate total size
total_size = 0
for ct_AN in 1:atomnum
    TNO1 = Total_NumOrbs[ct_AN]
    for h_AN in 1:FNAN[ct_AN]  # Julia 1-indexed
        Gh_AN = natn[ct_AN][h_AN]
        TNO2 = Total_NumOrbs[Gh_AN]
        total_size += TNO1 * TNO2
    end
end

# Try to read H0 (component 0 only, spin-independent)
H0_raw = Vector{Float64}(undef, total_size)
n_read = readbytes!(f, reinterpret(UInt8, H0_raw), total_size * 8)
n_read = div(n_read, 8)  # Convert bytes to Float64 count

if n_read == total_size
    # Success - new format with H components
    H_components_available = true
    
    # Read HNL (multiple spin components)
    num_HNL_spin = SpinP_switch == 0 ? 1 : (SpinP_switch == 1 ? 2 : 3)
    HNL_raw = Vector{Float64}(undef, total_size * num_HNL_spin)
    read!(f, HNL_raw)
    
    # Read HVNA (spin-independent)
    HVNA_raw = Vector{Float64}(undef, total_size)
    read!(f, HVNA_raw)
    
    println("H0/HNL/HVNA read successfully")
else
    # Old format - no H components
    H_components_available = false
    H0_raw = nothing
    HNL_raw = nothing
    HVNA_raw = nothing
    println("No H0/HNL/HVNA found (old format or not enabled)")
end
```

- [ ] **Step 4: Convert raw data to dict format**

Add helper function to convert raw arrays to the same dict format as `hamiltonians`:

```julia
function raw_to_H_dict(raw_data, atomnum, FNAN, natn, ncn, Total_NumOrbs, atv_ijk)
    H_dict = Dict{Vector{Int64}, Matrix{Float64}}()
    offset = 0
    
    for ct_AN in 1:atomnum
        TNO1 = Total_NumOrbs[ct_AN]
        for h_AN in 1:FNAN[ct_AN]
            Gh_AN = natn[ct_AN][h_AN]
            TNO2 = Total_NumOrbs[Gh_AN]
            block_size = TNO1 * TNO2
            
            # Get lattice vector R
            nc_idx = ncn[ct_AN][h_AN]
            R = atv_ijk[:, nc_idx]
            
            # Key: [Rx, Ry, Rz, site_i, site_j]
            key = vcat(R, [ct_AN, Gh_AN])
            
            # Extract block and reshape (note: Julia is column-major)
            block = reshape(raw_data[offset+1:offset+block_size], TNO2, TNO1)
            H_dict[key] = block
            
            offset += block_size
        end
    end
    
    return H_dict
end
```

- [ ] **Step 5: Save to HDF5 files**

Add output functions:

```julia
function save_H0(H0_dict, output_dir)
    h5open(joinpath(output_dir, "H0.h5"), "w") do f
        for (key, mat) in H0_dict
            write(f, string(key), mat)
        end
    end
    println("Saved H0.h5")
end

function save_HNL(HNL_dict, output_dir, num_HNL_spin)
    h5open(joinpath(output_dir, "HNL.h5"), "w") do f
        for (key, blocks) in HNL_dict
            for spin in 1:num_HNL_spin
                # Key format: [Rx, Ry, Rz, site_i, site_j, spin]
                spin_key = vcat(key, [spin])
                write(f, string(spin_key), blocks[spin])
            end
        end
    end
    println("Saved HNL.h5 ($num_HNL_spin spin components)")
end

function save_HVNA(HVNA_dict, output_dir)
    h5open(joinpath(output_dir, "HVNA.h5"), "w") do f
        for (key, mat) in HVNA_dict
            write(f, string(key), mat)
        end
    end
    println("Saved HVNA.h5")
end
```

---

### Task 5.2: File Structure Summary

**Modified parse_openmx() return signature:**
```julia
# Original:
return element, atomnum, SpinP_switch, atv, atv_ijk, Total_NumOrbs, 
       FNAN, natn, ncn, tv, Hk, iHk, OLP, OLP_r, orbital_types, 
       fermi_level, atom_pos, DM

# Extended:
return element, atomnum, SpinP_switch, atv, atv_ijk, Total_NumOrbs, 
       FNAN, natn, ncn, tv, Hk, iHk, OLP, OLP_r, orbital_types, 
       fermi_level, atom_pos, DM,
       H0_raw, HNL_raw, HVNA_raw, H_components_available, num_HNL_spin
```

**Output files when H_components=true:**
| File | Content | Key Format |
|------|---------|------------|
| `H0.h5` | H0 matrices | `[Rx, Ry, Rz, site_i, site_j]` |
| `HNL.h5` | HNL matrices | `[Rx, Ry, Rz, site_i, site_j, spin]` |
| `HVNA.h5` | HVNA matrices | `[Rx, Ry, Rz, site_i, site_j]` |

---

### Task 5.3: Test the script

- [ ] **Step 1: Test with old format scfout**
```bash
julia /thfs4/home/xuyong/script/openmx_get_data_ext.jl old_format.scfout
# Should output: "No H0/HNL/HVNA found (old format or not enabled)"
```

- [ ] **Step 2: Test with new format scfout**
```bash
julia /thfs4/home/xuyong/script/openmx_get_data_ext.jl new_format.scfout
# Should output: "H0/HNL/HVNA read successfully"
# Should create: H0.h5, HNL.h5, HVNA.h5
```

- [ ] **Step 3: Verify data integrity**

Check that H = H0 + HNL + HVNA + SCF_terms:
```julia
# In Julia REPL
using HDF5
H = h5read("hamiltonians.h5", "[0, 0, 0, 1, 1]")
H0 = h5read("H0.h5", "[0, 0, 0, 1, 1]")
HNL = h5read("HNL.h5", "[0, 0, 0, 1, 1, 1]")  # spin=1
HVNA = h5read("HVNA.h5", "[0, 0, 0, 1, 1]")
# Verify: H ≈ H0 + HNL + HVNA + (SCF contribution)
```

---

## Implementation Status

### Completed (2026-03-14)

| Task | Status | Notes |
|------|--------|-------|
| openmx_common.h modification | ✅ Done | Line 2632 |
| Input_std.c modification | ✅ Done | Line 103 |
| SCF2File.c modification | ✅ Done | Lines 792-985 |
| OpenMX compilation | ✅ Done | ARM aarch64, 6.2MB |
| openmx_get_data_ext.jl | ⏳ Pending | Ready for implementation |

### Compilation Environment

```bash
source /etc/profile
module load GCC/9.4.0
module load fftw/3.3.10-gcc9.4.0-mpich4.1.2
module load scalapack/2.2.0-gcc9.4.0-mpich4.1.2
module load openblas/0.3.28-gcc9.4.0
module load sse2neon/1.8.0
```

### Binary Location

```
/thfs4/home/xuyong/software/openmx/openmx3.9_modify_output/source/openmx
```

---

Plan verified and ready to execute.
