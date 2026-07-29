#include <cuda.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>

static void check(CUresult result, const char* operation) {
    if (result == CUDA_SUCCESS) {
        return;
    }
    const char* name = nullptr;
    const char* message = nullptr;
    cuGetErrorName(result, &name);
    cuGetErrorString(result, &message);
    std::fprintf(stderr, "%s failed: %s (%s)\n", operation,
                 name ? name : "unknown", message ? message : "unknown");
    std::exit(2);
}

int main(int argc, char** argv) {
    if (argc != 5) {
        std::fprintf(stderr, "usage: %s CUBIN FUNCTION INPUT EXPECTED\n", argv[0]);
        return 2;
    }

    const std::uint32_t input = static_cast<std::uint32_t>(std::strtoul(argv[3], nullptr, 0));
    const std::uint32_t expected = static_cast<std::uint32_t>(std::strtoul(argv[4], nullptr, 0));

    check(cuInit(0), "cuInit");
    CUdevice device;
    check(cuDeviceGet(&device, 0), "cuDeviceGet");
    CUcontext context;
    check(cuCtxCreate(&context, 0, device), "cuCtxCreate");

    CUmodule module;
    check(cuModuleLoad(&module, argv[1]), "cuModuleLoad");
    CUfunction function;
    check(cuModuleGetFunction(&function, module, argv[2]), "cuModuleGetFunction");

    CUdeviceptr output_device;
    check(cuMemAlloc(&output_device, sizeof(std::uint32_t)), "cuMemAlloc");
    void* arguments[] = {&output_device, const_cast<std::uint32_t*>(&input)};
    check(cuLaunchKernel(function, 1, 1, 1, 1, 1, 1, 0, nullptr, arguments, nullptr),
          "cuLaunchKernel");
    check(cuCtxSynchronize(), "cuCtxSynchronize");

    std::uint32_t output = 0;
    check(cuMemcpyDtoH(&output, output_device, sizeof(output)), "cuMemcpyDtoH");
    std::printf("%s(0x%08x) = 0x%08x; expected 0x%08x: %s\n", argv[2], input,
                output, expected, output == expected ? "PASS" : "FAIL");

    check(cuMemFree(output_device), "cuMemFree");
    check(cuModuleUnload(module), "cuModuleUnload");
    check(cuCtxDestroy(context), "cuCtxDestroy");
    return output == expected ? 0 : 1;
}
