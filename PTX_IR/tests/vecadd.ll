
declare hidden i32 @__zluda_ptx_impl_sreg_tid(i8) #0

declare hidden i32 @__zluda_ptx_impl_sreg_ntid(i8) #0

declare hidden i32 @__zluda_ptx_impl_sreg_ctaid(i8) #0

define amdgpu_kernel void @vecadd(ptr addrspace(4) byref(i64) %"68", ptr addrspace(4) byref(i64) %"69", ptr addrspace(4) byref(i64) %"70") #1 {
  %"71" = alloca i32, align 4, addrspace(5)
  %"72" = alloca i32, align 4, addrspace(5)
  %"73" = alloca i32, align 4, addrspace(5)
  %"74" = alloca i32, align 4, addrspace(5)
  %"75" = alloca i32, align 4, addrspace(5)
  %"76" = alloca i32, align 4, addrspace(5)
  %"77" = alloca i64, align 8, addrspace(5)
  %"78" = alloca i64, align 8, addrspace(5)
  %"79" = alloca i64, align 8, addrspace(5)
  %"80" = alloca i64, align 8, addrspace(5)
  %"81" = alloca i64, align 8, addrspace(5)
  %"82" = alloca i64, align 8, addrspace(5)
  %"83" = alloca i64, align 8, addrspace(5)
  %"84" = alloca i64, align 8, addrspace(5)
  %"85" = alloca i64, align 8, addrspace(5)
  %"86" = alloca i64, align 8, addrspace(5)
  %"87" = alloca i64, align 8, addrspace(5)
  %"88" = alloca float, align 4, addrspace(5)
  %"89" = alloca float, align 4, addrspace(5)
  %"90" = alloca float, align 4, addrspace(5)
  %"91" = alloca float, align 4, addrspace(5)
  br label %1

1:                                                ; preds = %0
  br label %"64"

"64":                                             ; preds = %1
  %2 = load i64, ptr addrspace(4) %"68", align 8
  store i64 %2, ptr addrspace(5) %"78", align 8
  %3 = load i64, ptr addrspace(4) %"69", align 8
  store i64 %3, ptr addrspace(5) %"79", align 8
  %4 = load i64, ptr addrspace(4) %"70", align 8
  store i64 %4, ptr addrspace(5) %"80", align 8
  %5 = load i64, ptr addrspace(5) %"78", align 8
  %6 = inttoptr i64 %5 to ptr
  %7 = addrspacecast ptr %6 to ptr addrspace(1)
  %"95" = ptrtoint ptr addrspace(1) %7 to i64
  store i64 %"95", ptr addrspace(5) %"81", align 8
  %8 = load i64, ptr addrspace(5) %"79", align 8
  %9 = inttoptr i64 %8 to ptr
  %10 = addrspacecast ptr %9 to ptr addrspace(1)
  %"97" = ptrtoint ptr addrspace(1) %10 to i64
  store i64 %"97", ptr addrspace(5) %"82", align 8
  %11 = load i64, ptr addrspace(5) %"80", align 8
  %12 = inttoptr i64 %11 to ptr
  %13 = addrspacecast ptr %12 to ptr addrspace(1)
  %"99" = ptrtoint ptr addrspace(1) %13 to i64
  store i64 %"99", ptr addrspace(5) %"83", align 8
  %"58" = call i32 @__zluda_ptx_impl_sreg_ctaid(i8 0)
  store i32 %"58", ptr addrspace(5) %"72", align 4
  %"60" = call i32 @__zluda_ptx_impl_sreg_ntid(i8 0)
  store i32 %"60", ptr addrspace(5) %"73", align 4
  %"62" = call i32 @__zluda_ptx_impl_sreg_tid(i8 0)
  store i32 %"62", ptr addrspace(5) %"74", align 4
  %14 = load i32, ptr addrspace(5) %"72", align 4
  %15 = load i32, ptr addrspace(5) %"73", align 4
  %16 = load i32, ptr addrspace(5) %"74", align 4
  %17 = mul i32 %14, %15
  %"134" = add i32 %17, %16
  store i32 %"134", ptr addrspace(5) %"75", align 4
  %18 = load i32, ptr addrspace(5) %"75", align 4
  %19 = sext i32 %18 to i64
  %"138" = mul i64 %19, 4
  store i64 %"138", ptr addrspace(5) %"84", align 8
  %20 = load i64, ptr addrspace(5) %"81", align 8
  %21 = load i64, ptr addrspace(5) %"84", align 8
  %"140" = add i64 %20, %21
  store i64 %"140", ptr addrspace(5) %"85", align 8
  %22 = load i64, ptr addrspace(5) %"82", align 8
  %23 = load i64, ptr addrspace(5) %"84", align 8
  %"143" = add i64 %22, %23
  store i64 %"143", ptr addrspace(5) %"86", align 8
  %24 = load i64, ptr addrspace(5) %"83", align 8
  %25 = load i64, ptr addrspace(5) %"84", align 8
  %"146" = add i64 %24, %25
  store i64 %"146", ptr addrspace(5) %"87", align 8
  %26 = load i64, ptr addrspace(5) %"85", align 8
  %"149" = inttoptr i64 %26 to ptr addrspace(1)
  %27 = load float, ptr addrspace(1) %"149", align 4
  store float %27, ptr addrspace(5) %"89", align 4
  %28 = load i64, ptr addrspace(5) %"86", align 8
  %"150" = inttoptr i64 %28 to ptr addrspace(1)
  %29 = load float, ptr addrspace(1) %"150", align 4
  store float %29, ptr addrspace(5) %"90", align 4
  %30 = load float, ptr addrspace(5) %"89", align 4
  %31 = load float, ptr addrspace(5) %"90", align 4
  %"123" = fadd float %30, %31
  store float %"123", ptr addrspace(5) %"91", align 4
  %32 = load i64, ptr addrspace(5) %"87", align 8
  %33 = load float, ptr addrspace(5) %"91", align 4
  %"151" = inttoptr i64 %32 to ptr addrspace(1)
  store float %33, ptr addrspace(1) %"151", align 4
  ret void
}

attributes #0 = { "amdgpu-ieee"="false" "amdgpu-unsafe-fp-atomics"="true" "denormal-fp-math"="dynamic" "denormal-fp-math-f32"="dynamic" "no-trapping-math"="true" "target-features"="+wavefrontsize32,-wavefrontsize64,+cumode,+precise-memory" "uniform-work-group-size"="true" }
attributes #1 = { "amdgpu-ieee"="false" "amdgpu-unsafe-fp-atomics"="true" "denormal-fp-math"="preserve-sign" "denormal-fp-math-f32"="ieee" "no-trapping-math"="true" "target-features"="+wavefrontsize32,-wavefrontsize64,+cumode,+precise-memory" "uniform-work-group-size"="true" }
