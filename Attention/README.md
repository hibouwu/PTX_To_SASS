# Attention PTX: sm_110f build and run

`run_sm110f.sh` executes the complete flow:

1. Compile every PTX kernel with `ptxas -arch=sm_110f` at O0 and O3.
2. Save `nvdisasm -g` and `nvdisasm -gp` output.
3. Build the CUDA Driver API host runner.
4. Load and execute every cubin on a compute capability 11.0 GPU.

From the repository root:

```bash
./Attention/run_sm110f.sh
```

Generated cubins and SASS are verification evidence and should be committed:

```text
Attention/cubins/<kernel>_O0.cubin
Attention/cubins/<kernel>_O3.cubin
Attention/sass/<kernel>_O0.sass
Attention/sass/<kernel>_O0_ptxline.sass
Attention/sass/<kernel>_O3.sass
Attention/sass/<kernel>_O3_ptxline.sass
```

Run one kernel or one optimization level:

```bash
./Attention/run_sm110f.sh --kernel transpose
./Attention/run_sm110f.sh --kernel transpose --opt 0
./Attention/run_sm110f.sh --device 1
```

On a machine without an sm_110f GPU, compile and disassemble only:

```bash
./Attention/run_sm110f.sh --compile-only
```

Use another CUDA Toolkit installation with either
`--cuda-home /path/to/cuda` or the `CUDA_HOME` environment variable.

The current host runner verifies that each cubin loads and launches without a
CUDA error. It is not a numerical correctness oracle for the PTX skeletons.
