#include <cuda.h>

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

static void failCu(CUresult r, const char *expr, const char *file, int line) {
    const char *name = nullptr;
    const char *msg = nullptr;
    cuGetErrorName(r, &name);
    cuGetErrorString(r, &msg);
    std::fprintf(stderr, "CUDA error at %s:%d: %s -> %s (%s)\n",
                 file, line, expr, name ? name : "unknown", msg ? msg : "no message");
    std::exit(2);
}

#define CHECK_CU(expr) do {                       \
    CUresult _r = (expr);                         \
    if (_r != CUDA_SUCCESS) failCu(_r, #expr, __FILE__, __LINE__); \
} while (0)

static void fillDevice(CUdeviceptr dst, size_t count, float base) {
    std::vector<float> h(count);
    for (size_t i = 0; i < count; ++i) {
        h[i] = base + static_cast<float>(i % 97) * 0.001f;
    }
    CHECK_CU(cuMemcpyHtoD(dst, h.data(), count * sizeof(float)));
}

static CUdeviceptr allocFloats(size_t count, float base) {
    CUdeviceptr p = 0;
    CHECK_CU(cuMemAlloc(&p, count * sizeof(float)));
    fillDevice(p, count, base);
    return p;
}

static void syncAndReport(const char *kernelName) {
    CHECK_CU(cuCtxSynchronize());
    std::printf("[RUN OK] %s\n", kernelName);
}

static void runFused(CUfunction fn) {
    CUdeviceptr x = allocFloats(512, 0.1f);
    CUdeviceptr bias = allocFloats(512, 0.01f);
    CUdeviceptr y = allocFloats(512, 0.0f);
    unsigned n = 256;
    float scale = 1.0f;
    void *args[] = {&x, &bias, &y, &n, &scale};
    CHECK_CU(cuLaunchKernel(fn, 1, 1, 1, 128, 1, 1, 0, nullptr, args, nullptr));
    syncAndReport("fused_ew");
    CHECK_CU(cuMemFree(x));
    CHECK_CU(cuMemFree(bias));
    CHECK_CU(cuMemFree(y));
}

static void runLayernorm(CUfunction fn) {
    CUdeviceptr x = allocFloats(1024, 0.2f);
    CUdeviceptr y = allocFloats(1024, 0.0f);
    CUdeviceptr gamma = allocFloats(1024, 1.0f);
    CUdeviceptr beta = allocFloats(1024, 0.0f);
    void *args[] = {&x, &y, &gamma, &beta};
    CHECK_CU(cuLaunchKernel(fn, 1, 1, 1, 128, 1, 1, 0, nullptr, args, nullptr));
    syncAndReport("layernorm");
    CHECK_CU(cuMemFree(x));
    CHECK_CU(cuMemFree(y));
    CHECK_CU(cuMemFree(gamma));
    CHECK_CU(cuMemFree(beta));
}

static void runSoftmax(CUfunction fn) {
    CUdeviceptr x = allocFloats(1024, 0.3f);
    CUdeviceptr y = allocFloats(1024, 0.0f);
    void *args[] = {&x, &y};
    CHECK_CU(cuLaunchKernel(fn, 1, 1, 1, 128, 1, 1, 0, nullptr, args, nullptr));
    syncAndReport("softmax_mt");
    CHECK_CU(cuMemFree(x));
    CHECK_CU(cuMemFree(y));
}

static void runTmaBulk(CUfunction fn) {
    CUdeviceptr in = allocFloats(128, 1.0f);
    CUdeviceptr out = allocFloats(128, 0.0f);
    void *args[] = {&in, &out};
    CHECK_CU(cuLaunchKernel(fn, 1, 1, 1, 128, 1, 1, 0, nullptr, args, nullptr));
    syncAndReport("tma_bulk");
    CHECK_CU(cuMemFree(in));
    CHECK_CU(cuMemFree(out));
}

static void runTranspose(CUfunction fn) {
    CUdeviceptr in = allocFloats(128 * 128, 2.0f);
    CUdeviceptr out = allocFloats(128 * 128, 0.0f);

    alignas(128) CUtensorMap inMap;
    alignas(128) CUtensorMap outMap;
    std::memset(&inMap, 0, sizeof(inMap));
    std::memset(&outMap, 0, sizeof(outMap));

    const cuuint64_t dims[2] = {128, 128};
    const cuuint64_t strides[1] = {128 * sizeof(float)};
    const cuuint32_t box[2] = {32, 32};
    const cuuint32_t elemStrides[2] = {1, 1};

    CHECK_CU(cuTensorMapEncodeTiled(&inMap, CU_TENSOR_MAP_DATA_TYPE_FLOAT32, 2,
                                    reinterpret_cast<void *>(in), dims, strides, box, elemStrides,
                                    CU_TENSOR_MAP_INTERLEAVE_NONE, CU_TENSOR_MAP_SWIZZLE_NONE,
                                    CU_TENSOR_MAP_L2_PROMOTION_NONE, CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE));
    CHECK_CU(cuTensorMapEncodeTiled(&outMap, CU_TENSOR_MAP_DATA_TYPE_FLOAT32, 2,
                                    reinterpret_cast<void *>(out), dims, strides, box, elemStrides,
                                    CU_TENSOR_MAP_INTERLEAVE_NONE, CU_TENSOR_MAP_SWIZZLE_NONE,
                                    CU_TENSOR_MAP_L2_PROMOTION_NONE, CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE));

    CUdeviceptr inMapDev = 0;
    CUdeviceptr outMapDev = 0;
    CHECK_CU(cuMemAlloc(&inMapDev, sizeof(CUtensorMap)));
    CHECK_CU(cuMemAlloc(&outMapDev, sizeof(CUtensorMap)));
    CHECK_CU(cuMemcpyHtoD(inMapDev, &inMap, sizeof(CUtensorMap)));
    CHECK_CU(cuMemcpyHtoD(outMapDev, &outMap, sizeof(CUtensorMap)));
    void *args[] = {&inMapDev, &outMapDev};
    CHECK_CU(cuLaunchKernel(fn, 1, 1, 1, 128, 1, 1, 0, nullptr, args, nullptr));
    syncAndReport("transpose");
    CHECK_CU(cuMemFree(inMapDev));
    CHECK_CU(cuMemFree(outMapDev));
    CHECK_CU(cuMemFree(in));
    CHECK_CU(cuMemFree(out));
}

static void runMinTma(CUfunction fn) {
    CUdeviceptr in = allocFloats(128 * 128, 3.0f);
    CUdeviceptr out = allocFloats(16, 0.0f);

    alignas(128) CUtensorMap inMap;
    std::memset(&inMap, 0, sizeof(inMap));

    const cuuint64_t dims[2] = {128, 128};
    const cuuint64_t strides[1] = {128 * sizeof(float)};
    const cuuint32_t box[2] = {32, 32};
    const cuuint32_t elemStrides[2] = {1, 1};

    CHECK_CU(cuTensorMapEncodeTiled(&inMap, CU_TENSOR_MAP_DATA_TYPE_FLOAT32, 2,
                                    reinterpret_cast<void *>(in), dims, strides, box, elemStrides,
                                    CU_TENSOR_MAP_INTERLEAVE_NONE, CU_TENSOR_MAP_SWIZZLE_NONE,
                                    CU_TENSOR_MAP_L2_PROMOTION_NONE, CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE));

    CUdeviceptr inMapDev = 0;
    CHECK_CU(cuMemAlloc(&inMapDev, sizeof(CUtensorMap)));
    CHECK_CU(cuMemcpyHtoD(inMapDev, &inMap, sizeof(CUtensorMap)));

    void *args[] = {&inMapDev, &out};
    CHECK_CU(cuLaunchKernel(fn, 1, 1, 1, 128, 1, 1, 0, nullptr, args, nullptr));
    syncAndReport("min_tma");

    CHECK_CU(cuMemFree(inMapDev));
    CHECK_CU(cuMemFree(in));
    CHECK_CU(cuMemFree(out));
}

static std::string baseName(const char *path) {
    const char *slash = std::strrchr(path, '/');
    return slash ? slash + 1 : path;
}

int main(int argc, char **argv) {
    if (argc != 3) {
        std::fprintf(stderr, "usage: %s <cubin> <kernel-name>\n", argv[0]);
        return 2;
    }

    const char *cubinPath = argv[1];
    const char *kernelName = argv[2];

    CHECK_CU(cuInit(0));
    CUdevice dev;
    CHECK_CU(cuDeviceGet(&dev, 0));
    CUcontext ctx;
    CHECK_CU(cuCtxCreate(&ctx, nullptr, 0, dev));

    CUmodule mod;
    CHECK_CU(cuModuleLoad(&mod, cubinPath));
    CUfunction fn;
    CHECK_CU(cuModuleGetFunction(&fn, mod, kernelName));

    std::printf("[LOAD OK] %s:%s\n", baseName(cubinPath).c_str(), kernelName);

    if (std::strcmp(kernelName, "fused_ew") == 0) {
        runFused(fn);
    } else if (std::strcmp(kernelName, "layernorm") == 0) {
        runLayernorm(fn);
    } else if (std::strcmp(kernelName, "softmax_mt") == 0) {
        runSoftmax(fn);
    } else if (std::strcmp(kernelName, "tma_bulk") == 0) {
        runTmaBulk(fn);
    } else if (std::strcmp(kernelName, "transpose") == 0) {
        runTranspose(fn);
    } else if (std::strcmp(kernelName, "min_tma") == 0) {
        runMinTma(fn);
    } else {
        std::fprintf(stderr, "unknown kernel name: %s\n", kernelName);
        return 2;
    }

    CHECK_CU(cuModuleUnload(mod));
    CHECK_CU(cuCtxDestroy(ctx));
    return 0;
}
