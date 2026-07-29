#include <cuda.h>

#include <array>
#include <cerrno>
#include <climits>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

namespace {

constexpr unsigned int kClusterBlocks = 2;
constexpr unsigned int kThreadsPerBlock = 32;
constexpr std::uint32_t kRemotePayloadExpected = 0xC1A57E01u;
constexpr std::uint32_t kRemoteProtocolExpected = 0xC1A57E02u;

void check(CUresult result, const char* operation) {
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

std::array<std::uint32_t, 2> run_cluster_kernel(CUmodule module) {
    CUfunction function;
    check(cuModuleGetFunction(&function, module, "test_mbarrier_cluster_remote"),
          "cuModuleGetFunction(test_mbarrier_cluster_remote)");

    CUdeviceptr output_device;
    check(cuMemAlloc(&output_device, 2 * sizeof(std::uint32_t)), "cuMemAlloc");
    check(cuMemsetD32(output_device, 0xDEADBEEFu, 2), "cuMemsetD32");

    void* arguments[] = {&output_device};
    CUlaunchAttribute cluster_attribute{};
    cluster_attribute.id = CU_LAUNCH_ATTRIBUTE_CLUSTER_DIMENSION;
    cluster_attribute.value.clusterDim.x = kClusterBlocks;
    cluster_attribute.value.clusterDim.y = 1;
    cluster_attribute.value.clusterDim.z = 1;

    CUlaunchConfig config{};
    config.gridDimX = kClusterBlocks;
    config.gridDimY = 1;
    config.gridDimZ = 1;
    config.blockDimX = kThreadsPerBlock;
    config.blockDimY = 1;
    config.blockDimZ = 1;
    config.sharedMemBytes = 0;
    config.hStream = nullptr;
    config.attrs = &cluster_attribute;
    config.numAttrs = 1;

    check(cuLaunchKernelEx(&config, function, arguments, nullptr), "cuLaunchKernelEx(cluster=2)");
    check(cuCtxSynchronize(), "cuCtxSynchronize");

    std::array<std::uint32_t, 2> output{};
    check(cuMemcpyDtoH(output.data(), output_device, output.size() * sizeof(output[0])),
          "cuMemcpyDtoH");
    check(cuMemFree(output_device), "cuMemFree");
    return output;
}

int parse_device_ordinal(int argc, char** argv) {
    if (argc == 2) {
        return 0;
    }

    char* end = nullptr;
    errno = 0;
    const long parsed = std::strtol(argv[2], &end, 10);
    if (errno != 0 || end == argv[2] || *end != '\0' || parsed < 0 || parsed > INT_MAX) {
        std::fprintf(stderr, "ERROR: invalid CUDA device ordinal: %s\n", argv[2]);
        std::exit(2);
    }
    return static_cast<int>(parsed);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2 && argc != 3) {
        std::fprintf(stderr, "usage: %s CLUSTER_CUBIN [CUDA_DEVICE_ORDINAL]\n", argv[0]);
        return 2;
    }

    const int device_ordinal = parse_device_ordinal(argc, argv);
    check(cuInit(0), "cuInit");

    CUdevice device;
    check(cuDeviceGet(&device, device_ordinal), "cuDeviceGet");
    int major = 0;
    int minor = 0;
    int cluster_launch = 0;
    check(cuDeviceGetAttribute(&major, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR, device),
          "cuDeviceGetAttribute(major)");
    check(cuDeviceGetAttribute(&minor, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR, device),
          "cuDeviceGetAttribute(minor)");
    check(cuDeviceGetAttribute(&cluster_launch, CU_DEVICE_ATTRIBUTE_CLUSTER_LAUNCH, device),
          "cuDeviceGetAttribute(cluster_launch)");
    if (major != 10 || minor != 0 || cluster_launch == 0) {
        std::fprintf(stderr,
                     "ERROR: this test requires a B200 sm_100a with cluster launch; found "
                     "compute capability %d.%d, cluster_launch=%d\n",
                     major, minor, cluster_launch);
        return 2;
    }

    CUcontext context;
#if CUDA_VERSION >= 13000
    check(cuCtxCreate(&context, nullptr, 0, device), "cuCtxCreate");
#else
    check(cuCtxCreate(&context, 0, device), "cuCtxCreate");
#endif

    CUmodule module;
    check(cuModuleLoad(&module, argv[1]), "cuModuleLoad");
    const std::array<std::uint32_t, 2> output = run_cluster_kernel(module);
    const bool pass = output[0] == kRemotePayloadExpected &&
                      output[1] == kRemoteProtocolExpected;
    std::printf("test_mbarrier_cluster_remote: payload=0x%08x (expected 0x%08x), "
                "protocol=0x%08x (expected 0x%08x): %s\n",
                output[0], kRemotePayloadExpected, output[1], kRemoteProtocolExpected,
                pass ? "PASS" : "FAIL");

    check(cuModuleUnload(module), "cuModuleUnload");
    check(cuCtxDestroy(context), "cuCtxDestroy");
    return pass ? 0 : 1;
}
