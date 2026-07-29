#include <cuda.h>

#include <array>
#include <cerrno>
#include <climits>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

namespace {

constexpr unsigned int kThreadsPerBlock = 32;
constexpr std::uint32_t kArriveWaitExpected = 528;
constexpr std::uint32_t kExpectTxPendingExpected = 1;
constexpr std::uint32_t kCompleteTxExpected = 0xC0DEC0DEu;
constexpr std::uint32_t kArriveExpectTxCompleteExpected = 0xB03B03B0u;
constexpr std::uint32_t kArriveDropExpected = 0x0A441D04u;
constexpr std::array<std::uint32_t, 4> kMultiPhaseExpected = {
    528u, 3728u, 6928u, 10128u,
};

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

std::array<std::uint32_t, 4> run_kernel(CUmodule module, const char* function_name) {
    CUfunction function;
    check(cuModuleGetFunction(&function, module, function_name), "cuModuleGetFunction");

    CUdeviceptr output_device;
    check(cuMemAlloc(&output_device, 4 * sizeof(std::uint32_t)), "cuMemAlloc");
    check(cuMemsetD32(output_device, 0xDEADBEEFu, 4), "cuMemsetD32");

    void* arguments[] = {&output_device};
    check(cuLaunchKernel(function,
                         1, 1, 1,
                         kThreadsPerBlock, 1, 1,
                         0, nullptr, arguments, nullptr),
          "cuLaunchKernel");
    check(cuCtxSynchronize(), "cuCtxSynchronize");

    std::array<std::uint32_t, 4> output{};
    check(cuMemcpyDtoH(output.data(), output_device, output.size() * sizeof(output[0])),
          "cuMemcpyDtoH");
    check(cuMemFree(output_device), "cuMemFree");
    return output;
}

bool report_arrive_wait(const std::array<std::uint32_t, 4>& output) {
    const bool pass = output[0] == kArriveWaitExpected;
    std::printf("test_mbarrier_arrive_wait: sum=%u (expected %u): %s\n",
                output[0], kArriveWaitExpected, pass ? "PASS" : "FAIL");
    return pass;
}

bool report_expect_tx_complete_tx(const std::array<std::uint32_t, 4>& output) {
    const bool pending_pass = output[0] == kExpectTxPendingExpected;
    const bool completion_pass = output[1] == kCompleteTxExpected;
    const bool pass = pending_pass && completion_pass;
    std::printf("test_mbarrier_expect_tx_complete_tx: "
                "early_wait_pending=%u (expected %u), completion=0x%08x "
                "(expected 0x%08x): %s\n",
                output[0], kExpectTxPendingExpected, output[1], kCompleteTxExpected,
                pass ? "PASS" : "FAIL");
    return pass;
}

bool report_arrive_expect_tx_complete_tx(const std::array<std::uint32_t, 4>& output) {
    const bool pending_pass = output[0] == kExpectTxPendingExpected;
    const bool completion_pass = output[1] == kArriveExpectTxCompleteExpected;
    const bool pass = pending_pass && completion_pass;
    std::printf("test_mbarrier_arrive_expect_tx_complete_tx: "
                "early_wait_pending=%u (expected %u), completion=0x%08x "
                "(expected 0x%08x): %s\n",
                output[0], kExpectTxPendingExpected, output[1],
                kArriveExpectTxCompleteExpected, pass ? "PASS" : "FAIL");
    return pass;
}

bool report_arrive_drop_next_phase(const std::array<std::uint32_t, 4>& output) {
    const bool pass = output[0] == kArriveDropExpected;
    std::printf("test_mbarrier_arrive_drop_next_phase: phase-1 status=0x%08x "
                "(expected 0x%08x): %s\n",
                output[0], kArriveDropExpected, pass ? "PASS" : "FAIL");
    return pass;
}

bool report_multi_phase_reuse(const std::array<std::uint32_t, 4>& output) {
    const bool pass = output == kMultiPhaseExpected;
    std::printf("test_mbarrier_multi_phase_reuse: sums=[%u, %u, %u, %u] "
                "(expected [%u, %u, %u, %u]): %s\n",
                output[0], output[1], output[2], output[3],
                kMultiPhaseExpected[0], kMultiPhaseExpected[1],
                kMultiPhaseExpected[2], kMultiPhaseExpected[3],
                pass ? "PASS" : "FAIL");
    return pass;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2 && argc != 3) {
        std::fprintf(stderr, "usage: %s CUBIN [CUDA_DEVICE_ORDINAL]\n", argv[0]);
        return 2;
    }

    int device_ordinal = 0;
    if (argc == 3) {
        char* end = nullptr;
        errno = 0;
        const long parsed = std::strtol(argv[2], &end, 10);
        if (errno != 0 || end == argv[2] || *end != '\0' || parsed < 0 || parsed > INT_MAX) {
            std::fprintf(stderr, "ERROR: invalid CUDA device ordinal: %s\n", argv[2]);
            return 2;
        }
        device_ordinal = static_cast<int>(parsed);
    }

    check(cuInit(0), "cuInit");
    CUdevice device;
    check(cuDeviceGet(&device, device_ordinal), "cuDeviceGet");

    int major = 0;
    int minor = 0;
    check(cuDeviceGetAttribute(&major, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR, device),
          "cuDeviceGetAttribute(major)");
    check(cuDeviceGetAttribute(&minor, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR, device),
          "cuDeviceGetAttribute(minor)");
    if (major != 10 || minor != 0) {
        std::fprintf(stderr,
                     "ERROR: this suite is built for B200 sm_100a; found compute capability %d.%d\n",
                     major, minor);
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

    const bool arrive_wait_pass =
        report_arrive_wait(run_kernel(module, "test_mbarrier_arrive_wait"));
    const bool expect_tx_complete_tx_pass = report_expect_tx_complete_tx(
        run_kernel(module, "test_mbarrier_expect_tx_complete_tx"));
    const bool arrive_expect_tx_complete_tx_pass = report_arrive_expect_tx_complete_tx(
        run_kernel(module, "test_mbarrier_arrive_expect_tx_complete_tx"));
    const bool arrive_drop_next_phase_pass = report_arrive_drop_next_phase(
        run_kernel(module, "test_mbarrier_arrive_drop_next_phase"));
    const bool multi_phase_reuse_pass = report_multi_phase_reuse(
        run_kernel(module, "test_mbarrier_multi_phase_reuse"));

    check(cuModuleUnload(module), "cuModuleUnload");
    check(cuCtxDestroy(context), "cuCtxDestroy");
    return arrive_wait_pass && expect_tx_complete_tx_pass && arrive_expect_tx_complete_tx_pass &&
                   arrive_drop_next_phase_pass && multi_phase_reuse_pass
               ? 0
               : 1;
}
