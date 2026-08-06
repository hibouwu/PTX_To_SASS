
; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare hidden noundef range(i32 0, 1024) i32 @llvm.nvvm.read.ptx.sreg.tid.x() #0

; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare hidden noundef range(i32 1, 1025) i32 @llvm.nvvm.read.ptx.sreg.ntid.x() #0

; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare hidden noundef range(i32 0, 2147483647) i32 @llvm.nvvm.read.ptx.sreg.ctaid.x() #0

define ptx_kernel void @vecadd(ptr addrspace(101) byref(i64) %"77", ptr addrspace(101) byref(i64) %"78", ptr addrspace(101) byref(i64) %"79") #1 {
  %"80" = alloca i32, align 4, addrspace(5)
  %"81" = alloca i32, align 4, addrspace(5)
  %"82" = alloca i32, align 4, addrspace(5)
  %"83" = alloca i32, align 4, addrspace(5)
  %"84" = alloca i32, align 4, addrspace(5)
  %"85" = alloca i32, align 4, addrspace(5)
  %"86" = alloca i64, align 8, addrspace(5)
  %"87" = alloca i64, align 8, addrspace(5)
  %"88" = alloca i64, align 8, addrspace(5)
  %"89" = alloca i64, align 8, addrspace(5)
  %"90" = alloca i64, align 8, addrspace(5)
  %"91" = alloca i64, align 8, addrspace(5)
  %"92" = alloca i64, align 8, addrspace(5)
  %"93" = alloca i64, align 8, addrspace(5)
  %"94" = alloca i64, align 8, addrspace(5)
  %"95" = alloca i64, align 8, addrspace(5)
  %"96" = alloca i64, align 8, addrspace(5)
  %"97" = alloca float, align 4, addrspace(5)
  %"98" = alloca float, align 4, addrspace(5)
  %"99" = alloca float, align 4, addrspace(5)
  %"100" = alloca float, align 4, addrspace(5)
  br label %1

1:                                                ; preds = %0
  br label %"73"

"73":                                             ; preds = %1
  %2 = load i64, ptr addrspace(101) %"77", align 8
  store i64 %2, ptr addrspace(5) %"87", align 8
  %3 = load i64, ptr addrspace(101) %"78", align 8
  store i64 %3, ptr addrspace(5) %"88", align 8
  %4 = load i64, ptr addrspace(101) %"79", align 8
  store i64 %4, ptr addrspace(5) %"89", align 8
  %5 = load i64, ptr addrspace(5) %"87", align 8
  %6 = inttoptr i64 %5 to ptr
  %7 = addrspacecast ptr %6 to ptr addrspace(1)
  %"104" = ptrtoint ptr addrspace(1) %7 to i64
  store i64 %"104", ptr addrspace(5) %"90", align 8
  %8 = load i64, ptr addrspace(5) %"88", align 8
  %9 = inttoptr i64 %8 to ptr
  %10 = addrspacecast ptr %9 to ptr addrspace(1)
  %"106" = ptrtoint ptr addrspace(1) %10 to i64
  store i64 %"106", ptr addrspace(5) %"91", align 8
  %11 = load i64, ptr addrspace(5) %"89", align 8
  %12 = inttoptr i64 %11 to ptr
  %13 = addrspacecast ptr %12 to ptr addrspace(1)
  %"108" = ptrtoint ptr addrspace(1) %13 to i64
  store i64 %"108", ptr addrspace(5) %"92", align 8
  %"69" = call i32 @llvm.nvvm.read.ptx.sreg.ctaid.x()
  store i32 %"69", ptr addrspace(5) %"81", align 4
  %"70" = call i32 @llvm.nvvm.read.ptx.sreg.ntid.x()
  store i32 %"70", ptr addrspace(5) %"82", align 4
  %"71" = call i32 @llvm.nvvm.read.ptx.sreg.tid.x()
  store i32 %"71", ptr addrspace(5) %"83", align 4
  %14 = load i32, ptr addrspace(5) %"81", align 4
  %15 = load i32, ptr addrspace(5) %"82", align 4
  %16 = load i32, ptr addrspace(5) %"83", align 4
  %17 = mul i32 %14, %15
  %"143" = add i32 %17, %16
  store i32 %"143", ptr addrspace(5) %"84", align 4
  %18 = load i32, ptr addrspace(5) %"84", align 4
  %19 = sext i32 %18 to i64
  %"147" = mul i64 %19, 4
  store i64 %"147", ptr addrspace(5) %"93", align 8
  %20 = load i64, ptr addrspace(5) %"90", align 8
  %21 = load i64, ptr addrspace(5) %"93", align 8
  %"149" = add i64 %20, %21
  store i64 %"149", ptr addrspace(5) %"94", align 8
  %22 = load i64, ptr addrspace(5) %"91", align 8
  %23 = load i64, ptr addrspace(5) %"93", align 8
  %"152" = add i64 %22, %23
  store i64 %"152", ptr addrspace(5) %"95", align 8
  %24 = load i64, ptr addrspace(5) %"92", align 8
  %25 = load i64, ptr addrspace(5) %"93", align 8
  %"155" = add i64 %24, %25
  store i64 %"155", ptr addrspace(5) %"96", align 8
  %26 = load i64, ptr addrspace(5) %"94", align 8
  %"158" = inttoptr i64 %26 to ptr addrspace(1)
  %27 = load float, ptr addrspace(1) %"158", align 4
  store float %27, ptr addrspace(5) %"98", align 4
  %28 = load i64, ptr addrspace(5) %"95", align 8
  %"159" = inttoptr i64 %28 to ptr addrspace(1)
  %29 = load float, ptr addrspace(1) %"159", align 4
  store float %29, ptr addrspace(5) %"99", align 4
  %30 = load float, ptr addrspace(5) %"98", align 4
  %31 = load float, ptr addrspace(5) %"99", align 4
  %"132" = fadd float %30, %31
  store float %"132", ptr addrspace(5) %"100", align 4
  %32 = load i64, ptr addrspace(5) %"96", align 8
  %33 = load float, ptr addrspace(5) %"100", align 4
  %"160" = inttoptr i64 %32 to ptr addrspace(1)
  store float %33, ptr addrspace(1) %"160", align 4
  ret void
}

attributes #0 = { nocallback nofree nosync nounwind speculatable willreturn memory(none) "denormal-fp-math"="dynamic" "denormal-fp-math-f32"="dynamic" "no-trapping-math"="true" "target-cpu"="sm_80" }
attributes #1 = { "denormal-fp-math"="preserve-sign" "denormal-fp-math-f32"="ieee" "no-trapping-math"="true" "target-cpu"="sm_80" }
