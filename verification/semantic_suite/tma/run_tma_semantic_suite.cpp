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
constexpr std::size_t kTileDepth = 2;
constexpr std::size_t kTile3dElements = kTileElements * kTileDepth;
constexpr std::size_t kTile3dBytes = kTile3dElements * sizeof(std::uint32_t);
constexpr std::size_t kPitchedRowElements = 32;

constexpr std::uint32_t kTmaLoadStatus = 0xA11CE001U;
constexpr std::uint32_t kTma3dLoadStatus = 0xA11CE003U;
constexpr std::uint32_t kCpAsyncStatus = 0xC0A57C01U;
constexpr std::uint32_t kBulkStoreStatus = 0xB01C5E01U;
constexpr std::uint32_t kReduceAddStatus = 0xADD2D001U;
constexpr std::uint32_t kPrefetchExecutedStatus = 0xFE7C4001U;
constexpr std::uint32_t kStridedLoadStatus = 0x57A1D001U;
constexpr std::uint32_t kSwizzleRoundtripStatus = 0x5A122001U;
constexpr std::uint32_t kMulticastStatus = 0xAC125001U;

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

CUtensorMap make_u32_tensor_map_2d(CUdeviceptr data,
                                   std::size_t width,
                                   std::size_t height,
                                   std::size_t row_pitch_elements,
                                   CUtensorMapSwizzle swizzle = CU_TENSOR_MAP_SWIZZLE_NONE) {
    const cuuint64_t global_dimensions[2] = {
        static_cast<cuuint64_t>(width), static_cast<cuuint64_t>(height)};
    const cuuint64_t global_strides[1] = {
        static_cast<cuuint64_t>(row_pitch_elements * sizeof(std::uint32_t))};
    const cuuint32_t box_dimensions[2] = {
        static_cast<cuuint32_t>(width), static_cast<cuuint32_t>(height)};
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
              swizzle,
              CU_TENSOR_MAP_L2_PROMOTION_NONE,
              CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE),
          "cuTensorMapEncodeTiled(rank-2)");
    return tensor_map;
}

CUtensorMap make_16x16_u32_tensor_map(CUdeviceptr data) {
    // Tensor-map rules require a 16-byte-aligned base/stride and an inner box
    // width in bytes that is a multiple of 16.  16 u32 = 64 bytes satisfies
    // both requirements without swizzling or padding.
    return make_u32_tensor_map_2d(data, kTileEdge, kTileEdge, kTileEdge);
}

CUtensorMap make_16x16x2_u32_tensor_map(CUdeviceptr data) {
    const cuuint64_t global_dimensions[3] = {kTileEdge, kTileEdge, kTileDepth};
    const cuuint64_t global_strides[2] = {
        kTileEdge * sizeof(std::uint32_t), kTileElements * sizeof(std::uint32_t)};
    const cuuint32_t box_dimensions[3] = {kTileEdge, kTileEdge, kTileDepth};
    const cuuint32_t element_strides[3] = {1, 1, 1};

    CUtensorMap tensor_map{};
    check(cuTensorMapEncodeTiled(
              &tensor_map,
              CU_TENSOR_MAP_DATA_TYPE_UINT32,
              3,
              reinterpret_cast<void*>(static_cast<std::uintptr_t>(data)),
              global_dimensions,
              global_strides,
              box_dimensions,
              element_strides,
              CU_TENSOR_MAP_INTERLEAVE_NONE,
              CU_TENSOR_MAP_SWIZZLE_NONE,
              CU_TENSOR_MAP_L2_PROMOTION_NONE,
              CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE),
          "cuTensorMapEncodeTiled(rank-3)");
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

void launch_cluster_2x1x1(CUmodule module,
                          const char* function_name,
                          unsigned int block_threads,
                          void** arguments) {
    CUfunction function = nullptr;
    check(cuModuleGetFunction(&function, module, function_name), "cuModuleGetFunction(cluster)");

    CUlaunchAttribute attribute{};
    attribute.id = CU_LAUNCH_ATTRIBUTE_CLUSTER_DIMENSION;
    attribute.value.clusterDim.x = 2;
    attribute.value.clusterDim.y = 1;
    attribute.value.clusterDim.z = 1;

    CUlaunchConfig config{};
    config.gridDimX = 2;
    config.gridDimY = 1;
    config.gridDimZ = 1;
    config.blockDimX = block_threads;
    config.blockDimY = 1;
    config.blockDimZ = 1;
    config.sharedMemBytes = 0;
    config.hStream = nullptr;
    config.attrs = &attribute;
    config.numAttrs = 1;
    check(cuLaunchKernelEx(&config, function, arguments, nullptr), "cuLaunchKernelEx(cluster 2x1x1)");
    check(cuCtxSynchronize(), "cuCtxSynchronize(cluster 2x1x1)");
}

std::uint32_t download_u32(CUdeviceptr source) {
    std::uint32_t value = 0;
    check(cuMemcpyDtoH(&value, source, sizeof(value)), "cuMemcpyDtoH(u32)");
    return value;
}

void initialize_status(const DeviceBuffer& status_device, const char* operation) {
    check(cuMemsetD32(status_device.value, 0xDEADBEEFU, 1), operation);
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
    initialize_status(status_device, "cuMemsetD32(TMA mbarrier status)");
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
    initialize_status(status_device, "cuMemsetD32(cp.async status)");
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
    initialize_status(status_device, "cuMemsetD32(TMA bulk status)");
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

void run_tma_mbarrier_load_3d(const std::string& cubin_directory) {
    std::array<std::uint32_t, kTile3dElements> input{};
    std::array<std::uint32_t, kTile3dElements> output{};
    for (std::size_t i = 0; i < input.size(); ++i) {
        input[i] = 0x33000000U | static_cast<std::uint32_t>(i);
    }

    DeviceBuffer input_device(kTile3dBytes);
    DeviceBuffer output_device(kTile3dBytes);
    DeviceBuffer status_device(sizeof(std::uint32_t));
    initialize_status(status_device, "cuMemsetD32(TMA 3D status)");
    check(cuMemcpyHtoD(input_device.value, input.data(), kTile3dBytes), "cuMemcpyHtoD(TMA 3D input)");
    check(cuMemsetD8(output_device.value, 0, kTile3dBytes), "cuMemsetD8(TMA 3D output)");
    const CUtensorMap map = make_16x16x2_u32_tensor_map(input_device.value);
    DeviceBuffer map_device = upload_tensor_map(map);

    LoadedModule module(cubin_directory + "/tma_mbarrier_load_3d.cubin");
    void* arguments[] = {&map_device.value, &output_device.value, &status_device.value};
    launch(module.value, "semantic_tma_mbarrier_load_3d", 32, arguments);

    check_equal("TMA 3D mbarrier status", download_u32(status_device.value), kTma3dLoadStatus);
    check(cuMemcpyDtoH(output.data(), output_device.value, kTile3dBytes), "cuMemcpyDtoH(TMA 3D output)");
    for (std::size_t i = 0; i < output.size(); ++i) {
        check_equal("TMA 3D mbarrier output", output[i], input[i]);
    }
    std::printf("PASS tma_mbarrier_load_3d: 16x16x2 u32 tile copied after mbarrier wait\n");
}

void run_tma_reduce_add(const std::string& cubin_directory) {
    std::array<std::uint32_t, kTileElements> destination{};
    std::array<std::uint32_t, kTileElements> baseline{};
    for (std::size_t i = 0; i < destination.size(); ++i) {
        baseline[i] = 0x10000000U + static_cast<std::uint32_t>(i * 3U);
        destination[i] = baseline[i];
    }

    DeviceBuffer destination_device(kTileBytes);
    DeviceBuffer status_device(sizeof(std::uint32_t));
    initialize_status(status_device, "cuMemsetD32(TMA reduce status)");
    check(cuMemcpyHtoD(destination_device.value, destination.data(), kTileBytes),
          "cuMemcpyHtoD(TMA reduce destination)");
    const CUtensorMap map = make_16x16_u32_tensor_map(destination_device.value);
    DeviceBuffer map_device = upload_tensor_map(map);

    LoadedModule module(cubin_directory + "/tma_reduce_add_2d.cubin");
    void* arguments[] = {&map_device.value, &status_device.value};
    launch(module.value, "semantic_tma_reduce_add_2d", 1, arguments);

    check_equal("TMA reduce-add status", download_u32(status_device.value), kReduceAddStatus);
    check(cuMemcpyDtoH(destination.data(), destination_device.value, kTileBytes),
          "cuMemcpyDtoH(TMA reduce destination)");
    for (std::size_t i = 0; i < destination.size(); ++i) {
        check_equal("TMA reduce-add output", destination[i], baseline[i] + static_cast<std::uint32_t>(i + 1));
    }
    std::printf("PASS tma_reduce_add_2d: global baseline plus shared 1..256 after bulk wait\n");
}

void run_tma_prefetch_execute(const std::string& cubin_directory) {
    std::array<std::uint32_t, kTileElements> input{};
    for (std::size_t i = 0; i < input.size(); ++i) {
        input[i] = static_cast<std::uint32_t>(i * 17U + 3U);
    }

    DeviceBuffer input_device(kTileBytes);
    DeviceBuffer status_device(sizeof(std::uint32_t));
    initialize_status(status_device, "cuMemsetD32(TMA prefetch status)");
    check(cuMemcpyHtoD(input_device.value, input.data(), kTileBytes), "cuMemcpyHtoD(TMA prefetch input)");
    const CUtensorMap map = make_16x16_u32_tensor_map(input_device.value);
    DeviceBuffer map_device = upload_tensor_map(map);

    LoadedModule module(cubin_directory + "/tma_prefetch_2d_execute.cubin");
    void* arguments[] = {&map_device.value, &status_device.value};
    launch(module.value, "semantic_tma_prefetch_2d_execute", 1, arguments);

    check_equal("TMA prefetch executed status", download_u32(status_device.value), kPrefetchExecutedStatus);
    std::printf("EXECUTED tma_prefetch_2d: valid descriptor reached the L2 prefetch instruction\n");
}

void run_tma_strided_load(const std::string& cubin_directory) {
    std::vector<std::uint32_t> input(kPitchedRowElements * kTileEdge, 0xDEADBEEFU);
    std::array<std::uint32_t, kTileElements> expected{};
    std::array<std::uint32_t, kTileElements> output{};
    for (std::size_t row = 0; row < kTileEdge; ++row) {
        for (std::size_t column = 0; column < kTileEdge; ++column) {
            const std::uint32_t value =
                0x71000000U | static_cast<std::uint32_t>(row * kTileEdge + column);
            input[row * kPitchedRowElements + column] = value;
            expected[row * kTileEdge + column] = value;
        }
    }

    DeviceBuffer input_device(input.size() * sizeof(std::uint32_t));
    DeviceBuffer output_device(kTileBytes);
    DeviceBuffer status_device(sizeof(std::uint32_t));
    initialize_status(status_device, "cuMemsetD32(TMA strided status)");
    check(cuMemcpyHtoD(input_device.value, input.data(), input.size() * sizeof(std::uint32_t)),
          "cuMemcpyHtoD(TMA strided input)");
    check(cuMemsetD8(output_device.value, 0, kTileBytes), "cuMemsetD8(TMA strided output)");
    const CUtensorMap map = make_u32_tensor_map_2d(
        input_device.value, kTileEdge, kTileEdge, kPitchedRowElements);
    DeviceBuffer map_device = upload_tensor_map(map);

    LoadedModule module(cubin_directory + "/tma_strided_load_2d.cubin");
    void* arguments[] = {&map_device.value, &output_device.value, &status_device.value};
    launch(module.value, "semantic_tma_strided_load_2d", 32, arguments);

    check_equal("TMA strided-load status", download_u32(status_device.value), kStridedLoadStatus);
    check(cuMemcpyDtoH(output.data(), output_device.value, kTileBytes),
          "cuMemcpyDtoH(TMA strided output)");
    for (std::size_t i = 0; i < output.size(); ++i) {
        check_equal("TMA strided-load output", output[i], expected[i]);
    }
    std::printf("PASS tma_strided_load_2d: 16x16 logical tile read from 32-u32 physical row pitch\n");
}

void run_tma_swizzle_roundtrips(const std::string& cubin_directory) {
    struct SwizzleCase {
        const char* name;
        std::size_t width;
        std::size_t height;
        CUtensorMapSwizzle swizzle;
    };
    const std::array<SwizzleCase, 3> cases = {{
        {"32B", 8, 16, CU_TENSOR_MAP_SWIZZLE_32B},
        {"64B", 16, 16, CU_TENSOR_MAP_SWIZZLE_64B},
        {"128B", 32, 8, CU_TENSOR_MAP_SWIZZLE_128B},
    }};

    LoadedModule module(cubin_directory + "/tma_swizzle_roundtrip_2d.cubin");
    for (const SwizzleCase& test : cases) {
        const std::size_t elements = test.width * test.height;
        const std::size_t bytes = elements * sizeof(std::uint32_t);
        std::vector<std::uint32_t> input(elements);
        std::vector<std::uint32_t> output(elements);
        for (std::size_t i = 0; i < input.size(); ++i) {
            input[i] = 0x68000000U | static_cast<std::uint32_t>(i);
        }

        DeviceBuffer input_device(bytes);
        DeviceBuffer output_device(bytes);
        DeviceBuffer status_device(sizeof(std::uint32_t));
        initialize_status(status_device, "cuMemsetD32(TMA swizzle status)");
        check(cuMemcpyHtoD(input_device.value, input.data(), bytes), "cuMemcpyHtoD(TMA swizzle input)");
        check(cuMemsetD8(output_device.value, 0, bytes), "cuMemsetD8(TMA swizzle output)");
        const CUtensorMap input_map = make_u32_tensor_map_2d(
            input_device.value, test.width, test.height, test.width, test.swizzle);
        const CUtensorMap output_map = make_u32_tensor_map_2d(
            output_device.value, test.width, test.height, test.width, test.swizzle);
        DeviceBuffer input_map_device = upload_tensor_map(input_map);
        DeviceBuffer output_map_device = upload_tensor_map(output_map);
        std::uint32_t transaction_bytes = static_cast<std::uint32_t>(bytes);
        void* arguments[] = {&input_map_device.value, &output_map_device.value,
                             &transaction_bytes, &status_device.value};
        launch(module.value, "semantic_tma_swizzle_roundtrip_2d", 32, arguments);

        check_equal("TMA swizzle status", download_u32(status_device.value), kSwizzleRoundtripStatus);
        check(cuMemcpyDtoH(output.data(), output_device.value, bytes), "cuMemcpyDtoH(TMA swizzle output)");
        for (std::size_t i = 0; i < output.size(); ++i) {
            check_equal("TMA swizzle roundtrip output", output[i], input[i]);
        }
        std::printf("PASS tma_swizzle_roundtrip_2d_%s: logical TMA load/store roundtrip\n", test.name);
    }
}

void run_tma_multicast_cluster(const std::string& cubin_directory) {
    std::array<std::uint32_t, kTileElements> input{};
    std::array<std::uint32_t, kTileElements * 2> output{};
    for (std::size_t i = 0; i < input.size(); ++i) {
        input[i] = 0x4D000000U | static_cast<std::uint32_t>(i);
    }

    DeviceBuffer input_device(kTileBytes);
    DeviceBuffer output_device(output.size() * sizeof(std::uint32_t));
    DeviceBuffer status_device(sizeof(std::uint32_t));
    initialize_status(status_device, "cuMemsetD32(TMA multicast status)");
    check(cuMemcpyHtoD(input_device.value, input.data(), kTileBytes), "cuMemcpyHtoD(TMA multicast input)");
    check(cuMemsetD8(output_device.value, 0, output.size() * sizeof(std::uint32_t)),
          "cuMemsetD8(TMA multicast output)");
    const CUtensorMap map = make_16x16_u32_tensor_map(input_device.value);
    DeviceBuffer map_device = upload_tensor_map(map);

    LoadedModule module(cubin_directory + "/tma_multicast_cluster_2d.cubin");
    void* arguments[] = {&map_device.value, &output_device.value, &status_device.value};
    launch_cluster_2x1x1(module.value, "semantic_tma_multicast_cluster_2d", 32, arguments);

    check_equal("TMA multicast status", download_u32(status_device.value), kMulticastStatus);
    check(cuMemcpyDtoH(output.data(), output_device.value, output.size() * sizeof(std::uint32_t)),
          "cuMemcpyDtoH(TMA multicast output)");
    for (std::size_t rank = 0; rank < 2; ++rank) {
        for (std::size_t i = 0; i < input.size(); ++i) {
            check_equal("TMA multicast output", output[rank * kTileElements + i], input[i]);
        }
    }
    std::printf("PASS tma_multicast_cluster_2d: one TMA issue reached both CTAs in a 2-CTA cluster\n");
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
    int tensor_map_access = 0;
    int cluster_launch = 0;
    check(cuDeviceGetAttribute(&major, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR, device),
          "cuDeviceGetAttribute(major)");
    check(cuDeviceGetAttribute(&minor, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR, device),
          "cuDeviceGetAttribute(minor)");
    check(cuDeviceGetAttribute(&tensor_map_access,
                               CU_DEVICE_ATTRIBUTE_TENSOR_MAP_ACCESS_SUPPORTED,
                               device),
          "cuDeviceGetAttribute(tensor_map_access)");
    check(cuDeviceGetAttribute(&cluster_launch, CU_DEVICE_ATTRIBUTE_CLUSTER_LAUNCH, device),
          "cuDeviceGetAttribute(cluster_launch)");
    char device_name[256]{};
    check(cuDeviceGetName(device_name, sizeof(device_name), device), "cuDeviceGetName");
    if (major != 10 || minor != 0 || tensor_map_access == 0 || cluster_launch == 0) {
        std::fprintf(stderr,
                     "This suite requires B200 sm_100a tensor-map and cluster-launch support; "
                     "found %s (compute %d.%d, tensor_map_access=%d, cluster_launch=%d).\n",
                     device_name, major, minor, tensor_map_access, cluster_launch);
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
    run_tma_mbarrier_load_3d(argv[1]);
    run_classic_cp_async_group(argv[1]);
    run_tma_bulk_store(argv[1]);
    run_tma_reduce_add(argv[1]);
    run_tma_strided_load(argv[1]);
    run_tma_swizzle_roundtrips(argv[1]);
    run_tma_multicast_cluster(argv[1]);
    run_tma_prefetch_execute(argv[1]);

    check(cuCtxDestroy(context), "cuCtxDestroy");
    std::puts("ALL TMA / cp.async semantic lifecycle tests: PASS");
    return 0;
}
