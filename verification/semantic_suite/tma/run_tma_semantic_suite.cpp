#include <cuda.h>

#include <array>
#include <cerrno>
#include <climits>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

constexpr std::size_t kTileEdge = 16;
constexpr std::size_t kTileElements = kTileEdge * kTileEdge;
constexpr std::size_t kTileBytes = kTileElements * sizeof(std::uint32_t);

constexpr std::uint32_t kTmaLoadStatus = 0xA11CE001U;
constexpr std::uint32_t kCpAsyncStatus = 0xC0A57C01U;
constexpr std::uint32_t kBulkStoreStatus = 0xB01C5E01U;

[[noreturn]] void fail(const char* operation, CUresult result) {
    const char* name = nullptr;
    const char* message = nullptr;
    cuGetErrorName(result, &name);
    cuGetErrorString(result, &message);
    std::fprintf(stderr, "%s failed: %s (%s)\n", operation,
                 name ? name : "unknown", message ? message : "unknown");
    std::exit(2);
}

void check(CUresult result, const char* operation) {
    if (result != CUDA_SUCCESS) {
        fail(operation, result);
    }
}

void check_equal(const char* label, std::uint32_t actual, std::uint32_t expected) {
    if (actual == expected) {
        return;
    }
    std::fprintf(stderr, "%s: got 0x%08x, expected 0x%08x\n", label, actual, expected);
    std::exit(1);
}

struct DeviceBuffer {
    CUdeviceptr value = 0;

    explicit DeviceBuffer(std::size_t bytes) {
        check(cuMemAlloc(&value, bytes), "cuMemAlloc");
    }

    DeviceBuffer(const DeviceBuffer&) = delete;
    DeviceBuffer& operator=(const DeviceBuffer&) = delete;

    DeviceBuffer(DeviceBuffer&& other) noexcept : value(other.value) {
        other.value = 0;
    }

    DeviceBuffer& operator=(DeviceBuffer&& other) noexcept {
        if (this != &other) {
            if (value != 0) {
                cuMemFree(value);
            }
            value = other.value;
            other.value = 0;
        }
        return *this;
    }

    ~DeviceBuffer() {
        if (value != 0) {
            // The process is already terminating if this fails; do not hide a
            // semantic test result by reporting cleanup failure.
            cuMemFree(value);
        }
    }
};

struct LoadedModule {
    CUmodule value = nullptr;

    explicit LoadedModule(const std::string& path) {
        check(cuModuleLoad(&value, path.c_str()), "cuModuleLoad");
    }

    LoadedModule(const LoadedModule&) = delete;
    LoadedModule& operator=(const LoadedModule&) = delete;

    ~LoadedModule() {
        if (value != nullptr) {
            cuModuleUnload(value);
        }
    }
};

CUtensorMap make_16x16_u32_tensor_map(CUdeviceptr data) {
    // Tensor-map rules require a 16-byte-aligned base/stride and an inner box
    // width in bytes that is a multiple of 16.  16 u32 = 64 bytes satisfies
    // both requirements without swizzling or padding.
    const cuuint64_t global_dimensions[2] = {kTileEdge, kTileEdge};
    const cuuint64_t global_strides[1] = {kTileEdge * sizeof(std::uint32_t)};
    const cuuint32_t box_dimensions[2] = {kTileEdge, kTileEdge};
    const cuuint32_t element_strides[2] = {1, 1};

    CUtensorMap tensor_map{};
    check(cuTensorMapEncodeTiled(
              &tensor_map,
              CU_TENSOR_MAP_DATA_TYPE_UINT32,
              2,
              reinterpret_cast<void*>(static_cast<std::uintptr_t>(data)),
              global_dimensions,
              global_strides,
              box_dimensions,
              element_strides,
              CU_TENSOR_MAP_INTERLEAVE_NONE,
              CU_TENSOR_MAP_SWIZZLE_NONE,
              CU_TENSOR_MAP_L2_PROMOTION_NONE,
              CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE),
          "cuTensorMapEncodeTiled");
    return tensor_map;
}

DeviceBuffer upload_tensor_map(const CUtensorMap& tensor_map) {
    DeviceBuffer device_map(sizeof(tensor_map));
    check(cuMemcpyHtoD(device_map.value, &tensor_map, sizeof(tensor_map)), "cuMemcpyHtoD(tensor map)");
    return device_map;
}

void launch(CUmodule module,
            const char* function_name,
            unsigned int block_threads,
            void** arguments) {
    CUfunction function = nullptr;
    check(cuModuleGetFunction(&function, module, function_name), "cuModuleGetFunction");
    check(cuLaunchKernel(function,
                         1,
                         1,
                         1,
                         block_threads,
                         1,
                         1,
                         0,
                         nullptr,
                         arguments,
                         nullptr),
          "cuLaunchKernel");
    check(cuCtxSynchronize(), "cuCtxSynchronize");
}

std::uint32_t download_u32(CUdeviceptr source) {
    std::uint32_t value = 0;
    check(cuMemcpyDtoH(&value, source, sizeof(value)), "cuMemcpyDtoH(u32)");
    return value;
}

void run_tma_mbarrier_load(const std::string& cubin_directory) {
    std::array<std::uint32_t, kTileElements> input{};
    for (std::size_t i = 0; i < input.size(); ++i) {
        input[i] = static_cast<std::uint32_t>(i + 1);
    }
    std::array<std::uint32_t, kTileElements> output{};

    DeviceBuffer input_device(kTileBytes);
    DeviceBuffer output_device(kTileBytes);
    DeviceBuffer status_device(sizeof(std::uint32_t));
    check(cuMemcpyHtoD(input_device.value, input.data(), kTileBytes), "cuMemcpyHtoD(TMA input)");
    check(cuMemsetD8(output_device.value, 0, kTileBytes), "cuMemsetD8(TMA output)");
    const CUtensorMap map = make_16x16_u32_tensor_map(input_device.value);
    DeviceBuffer map_device = upload_tensor_map(map);

    LoadedModule module(cubin_directory + "/tma_mbarrier_load_2d.cubin");
    void* arguments[] = {&map_device.value, &output_device.value, &status_device.value};
    // The PTX initializes the mbarrier in thread 0 and uses a CTA sync to
    // publish it before the same thread issues the TMA transaction.
    launch(module.value, "semantic_tma_mbarrier_load_2d", 32, arguments);

    check_equal("TMA mbarrier status", download_u32(status_device.value), kTmaLoadStatus);
    check(cuMemcpyDtoH(output.data(), output_device.value, kTileBytes), "cuMemcpyDtoH(TMA output)");
    for (std::size_t i = 0; i < output.size(); ++i) {
        check_equal("TMA mbarrier output", output[i], input[i]);
    }
    std::printf("PASS tma_mbarrier_load_2d: 16x16 u32 tile copied after mbarrier wait\n");
}

void run_classic_cp_async_group(const std::string& cubin_directory) {
    const std::array<std::uint32_t, 8> input = {
        0x00112233U, 0x44556677U, 0x89ABCDEFU, 0x10203040U,
        0x55667788U, 0x99AABBCCU, 0xDDEEFF00U, 0x13579BDFU,
    };
    std::array<std::uint32_t, input.size()> output{};

    DeviceBuffer input_device(sizeof(input));
    DeviceBuffer output_device(sizeof(output));
    DeviceBuffer status_device(sizeof(std::uint32_t));
    check(cuMemcpyHtoD(input_device.value, input.data(), sizeof(input)), "cuMemcpyHtoD(cp.async input)");
    check(cuMemsetD8(output_device.value, 0, sizeof(output)), "cuMemsetD8(cp.async output)");

    LoadedModule module(cubin_directory + "/cp_async_group.cubin");
    void* arguments[] = {&input_device.value, &output_device.value, &status_device.value};
    launch(module.value, "semantic_cp_async_group", 1, arguments);

    check(cuMemcpyDtoH(output.data(), output_device.value, sizeof(output)), "cuMemcpyDtoH(cp.async output)");
    for (std::size_t i = 0; i < input.size(); ++i) {
        check_equal("classic cp.async output", output[i], input[i]);
    }
    check_equal("classic cp.async status", download_u32(status_device.value), kCpAsyncStatus);
    std::printf("PASS cp_async_group: 8 u32 values copied after commit/wait\n");
}

void run_tma_bulk_store(const std::string& cubin_directory) {
    std::array<std::uint32_t, kTileElements> output{};
    DeviceBuffer output_device(kTileBytes);
    DeviceBuffer status_device(sizeof(std::uint32_t));
    check(cuMemsetD8(output_device.value, 0, kTileBytes), "cuMemsetD8(TMA bulk output)");
    const CUtensorMap map = make_16x16_u32_tensor_map(output_device.value);
    DeviceBuffer map_device = upload_tensor_map(map);

    LoadedModule module(cubin_directory + "/tma_bulk_store_2d.cubin");
    void* arguments[] = {&map_device.value, &status_device.value};
    launch(module.value, "semantic_tma_bulk_store_2d", 1, arguments);

    check(cuMemcpyDtoH(output.data(), output_device.value, kTileBytes), "cuMemcpyDtoH(TMA bulk output)");
    for (std::size_t i = 0; i < output.size(); ++i) {
        const std::uint32_t expected = 0xA5000000U | static_cast<std::uint32_t>(i);
        check_equal("TMA bulk-store output", output[i], expected);
    }
    check_equal("TMA bulk-store status", download_u32(status_device.value), kBulkStoreStatus);
    std::printf("PASS tma_bulk_store_2d: 16x16 u32 tile copied after bulk commit/wait\n");
}

int parse_device_ordinal(int argc, char** argv) {
    if (argc == 2) {
        return 0;
    }
    if (argc == 4 && std::strcmp(argv[2], "--device") == 0) {
        char* end = nullptr;
        errno = 0;
        const long parsed = std::strtol(argv[3], &end, 10);
        if (errno == 0 && end != argv[3] && *end == '\0' && parsed >= 0 && parsed <= INT_MAX) {
            return static_cast<int>(parsed);
        }
    }
    std::fprintf(stderr, "usage: %s CUBIN_DIRECTORY [--device ORDINAL]\n", argv[0]);
    std::exit(2);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2 && argc != 4) {
        std::fprintf(stderr, "usage: %s CUBIN_DIRECTORY [--device ORDINAL]\n", argv[0]);
        return 2;
    }

    const int device_ordinal = parse_device_ordinal(argc, argv);
    check(cuInit(0), "cuInit");

    CUdevice device{};
    check(cuDeviceGet(&device, device_ordinal), "cuDeviceGet");
    int major = 0;
    int minor = 0;
    check(cuDeviceGetAttribute(&major, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR, device),
          "cuDeviceGetAttribute(major)");
    check(cuDeviceGetAttribute(&minor, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR, device),
          "cuDeviceGetAttribute(minor)");
    char device_name[256]{};
    check(cuDeviceGetName(device_name, sizeof(device_name), device), "cuDeviceGetName");
    if (major != 10 || minor != 0) {
        std::fprintf(stderr,
                     "This suite contains sm_100a cubins and requires compute capability 10.0; found %s (compute %d.%d).\n",
                     device_name,
                     major,
                     minor);
        return 2;
    }
    std::printf("Device %d: %s (compute %d.%d)\n", device_ordinal, device_name, major, minor);

    CUcontext context = nullptr;
#if CUDA_VERSION >= 13000
    check(cuCtxCreate(&context, nullptr, 0, device), "cuCtxCreate");
#else
    check(cuCtxCreate(&context, 0, device), "cuCtxCreate");
#endif

    run_tma_mbarrier_load(argv[1]);
    run_classic_cp_async_group(argv[1]);
    run_tma_bulk_store(argv[1]);

    check(cuCtxDestroy(context), "cuCtxDestroy");
    std::puts("ALL TMA / cp.async semantic lifecycle tests: PASS");
    return 0;
}
