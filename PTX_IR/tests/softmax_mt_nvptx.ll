
@partials_max = external addrspace(3) global [16 x i8], align 4
@partials_sum = external addrspace(3) global [16 x i8], align 4

declare hidden void @__zluda_ptx_impl_bar_sync(i32) #0

; Function Attrs: nocallback nofree nosync nounwind willreturn memory(none)
declare hidden float @llvm.nvvm.ex2.approx.f(float) #1

; Unknown intrinsic
declare hidden float @llvm.nvvm.rcp.approx.f(float) #0

declare hidden i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32, i32, i32, i32) #0

; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare hidden noundef range(i32 0, 1024) i32 @llvm.nvvm.read.ptx.sreg.tid.x() #2

; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare hidden noundef range(i32 1, 1025) i32 @llvm.nvvm.read.ptx.sreg.ntid.x() #2

define ptx_kernel void @softmax_mt(ptr addrspace(101) byref(i64) %"381", ptr addrspace(101) byref(i64) %"382") #3 {
  %"383" = alloca i32, align 4, addrspace(5)
  %"384" = alloca i32, align 4, addrspace(5)
  %"385" = alloca i32, align 4, addrspace(5)
  %"386" = alloca i32, align 4, addrspace(5)
  %"387" = alloca i32, align 4, addrspace(5)
  %"388" = alloca i32, align 4, addrspace(5)
  %"389" = alloca i32, align 4, addrspace(5)
  %"390" = alloca i32, align 4, addrspace(5)
  %"391" = alloca i32, align 4, addrspace(5)
  %"392" = alloca i32, align 4, addrspace(5)
  %"393" = alloca i32, align 4, addrspace(5)
  %"394" = alloca i32, align 4, addrspace(5)
  %"395" = alloca i32, align 4, addrspace(5)
  %"396" = alloca i32, align 4, addrspace(5)
  %"397" = alloca i32, align 4, addrspace(5)
  %"398" = alloca i32, align 4, addrspace(5)
  %"399" = alloca i32, align 4, addrspace(5)
  %"400" = alloca i32, align 4, addrspace(5)
  %"401" = alloca i32, align 4, addrspace(5)
  %"402" = alloca i32, align 4, addrspace(5)
  %"403" = alloca i32, align 4, addrspace(5)
  %"404" = alloca i32, align 4, addrspace(5)
  %"405" = alloca i32, align 4, addrspace(5)
  %"406" = alloca i32, align 4, addrspace(5)
  %"407" = alloca i32, align 4, addrspace(5)
  %"408" = alloca i32, align 4, addrspace(5)
  %"409" = alloca i32, align 4, addrspace(5)
  %"410" = alloca i32, align 4, addrspace(5)
  %"411" = alloca i32, align 4, addrspace(5)
  %"412" = alloca i32, align 4, addrspace(5)
  %"413" = alloca i32, align 4, addrspace(5)
  %"414" = alloca i32, align 4, addrspace(5)
  %"415" = alloca i32, align 4, addrspace(5)
  %"416" = alloca i32, align 4, addrspace(5)
  %"417" = alloca i32, align 4, addrspace(5)
  %"418" = alloca i32, align 4, addrspace(5)
  %"419" = alloca i32, align 4, addrspace(5)
  %"420" = alloca i32, align 4, addrspace(5)
  %"421" = alloca i32, align 4, addrspace(5)
  %"422" = alloca i32, align 4, addrspace(5)
  %"423" = alloca i32, align 4, addrspace(5)
  %"424" = alloca i32, align 4, addrspace(5)
  %"425" = alloca i32, align 4, addrspace(5)
  %"426" = alloca i32, align 4, addrspace(5)
  %"427" = alloca i32, align 4, addrspace(5)
  %"428" = alloca i32, align 4, addrspace(5)
  %"429" = alloca i32, align 4, addrspace(5)
  %"430" = alloca i32, align 4, addrspace(5)
  %"431" = alloca i32, align 4, addrspace(5)
  %"432" = alloca i32, align 4, addrspace(5)
  %"433" = alloca i32, align 4, addrspace(5)
  %"434" = alloca i32, align 4, addrspace(5)
  %"435" = alloca i32, align 4, addrspace(5)
  %"436" = alloca i32, align 4, addrspace(5)
  %"437" = alloca i32, align 4, addrspace(5)
  %"438" = alloca i32, align 4, addrspace(5)
  %"439" = alloca i32, align 4, addrspace(5)
  %"440" = alloca i32, align 4, addrspace(5)
  %"441" = alloca i32, align 4, addrspace(5)
  %"442" = alloca i32, align 4, addrspace(5)
  %"443" = alloca i32, align 4, addrspace(5)
  %"444" = alloca i32, align 4, addrspace(5)
  %"445" = alloca i32, align 4, addrspace(5)
  %"446" = alloca i32, align 4, addrspace(5)
  %"447" = alloca i32, align 4, addrspace(5)
  %"448" = alloca i32, align 4, addrspace(5)
  %"449" = alloca i32, align 4, addrspace(5)
  %"450" = alloca i32, align 4, addrspace(5)
  %"451" = alloca i32, align 4, addrspace(5)
  %"452" = alloca i32, align 4, addrspace(5)
  %"453" = alloca i32, align 4, addrspace(5)
  %"454" = alloca i32, align 4, addrspace(5)
  %"455" = alloca i32, align 4, addrspace(5)
  %"456" = alloca i32, align 4, addrspace(5)
  %"457" = alloca i32, align 4, addrspace(5)
  %"458" = alloca i32, align 4, addrspace(5)
  %"459" = alloca i32, align 4, addrspace(5)
  %"460" = alloca i32, align 4, addrspace(5)
  %"461" = alloca i32, align 4, addrspace(5)
  %"462" = alloca i32, align 4, addrspace(5)
  %"463" = alloca i32, align 4, addrspace(5)
  %"464" = alloca i32, align 4, addrspace(5)
  %"465" = alloca i32, align 4, addrspace(5)
  %"466" = alloca i32, align 4, addrspace(5)
  %"467" = alloca i32, align 4, addrspace(5)
  %"468" = alloca i32, align 4, addrspace(5)
  %"469" = alloca i32, align 4, addrspace(5)
  %"470" = alloca i32, align 4, addrspace(5)
  %"471" = alloca i32, align 4, addrspace(5)
  %"472" = alloca i32, align 4, addrspace(5)
  %"473" = alloca i32, align 4, addrspace(5)
  %"474" = alloca i32, align 4, addrspace(5)
  %"475" = alloca i32, align 4, addrspace(5)
  %"476" = alloca i32, align 4, addrspace(5)
  %"477" = alloca i32, align 4, addrspace(5)
  %"478" = alloca i32, align 4, addrspace(5)
  %"479" = alloca i32, align 4, addrspace(5)
  %"480" = alloca i32, align 4, addrspace(5)
  %"481" = alloca i32, align 4, addrspace(5)
  %"482" = alloca i32, align 4, addrspace(5)
  %"483" = alloca i64, align 8, addrspace(5)
  %"484" = alloca i64, align 8, addrspace(5)
  %"485" = alloca i64, align 8, addrspace(5)
  %"486" = alloca i64, align 8, addrspace(5)
  %"487" = alloca i64, align 8, addrspace(5)
  %"488" = alloca i64, align 8, addrspace(5)
  %"489" = alloca i64, align 8, addrspace(5)
  %"490" = alloca i64, align 8, addrspace(5)
  %"491" = alloca i64, align 8, addrspace(5)
  %"492" = alloca i64, align 8, addrspace(5)
  %"493" = alloca i64, align 8, addrspace(5)
  %"494" = alloca i64, align 8, addrspace(5)
  %"495" = alloca i64, align 8, addrspace(5)
  %"496" = alloca i64, align 8, addrspace(5)
  %"497" = alloca i64, align 8, addrspace(5)
  %"498" = alloca i64, align 8, addrspace(5)
  %"499" = alloca i64, align 8, addrspace(5)
  %"500" = alloca i64, align 8, addrspace(5)
  %"501" = alloca i64, align 8, addrspace(5)
  %"502" = alloca i64, align 8, addrspace(5)
  %"503" = alloca float, align 4, addrspace(5)
  %"504" = alloca float, align 4, addrspace(5)
  %"505" = alloca float, align 4, addrspace(5)
  %"506" = alloca float, align 4, addrspace(5)
  %"507" = alloca float, align 4, addrspace(5)
  %"508" = alloca float, align 4, addrspace(5)
  %"509" = alloca float, align 4, addrspace(5)
  %"510" = alloca float, align 4, addrspace(5)
  %"511" = alloca float, align 4, addrspace(5)
  %"512" = alloca float, align 4, addrspace(5)
  %"513" = alloca float, align 4, addrspace(5)
  %"514" = alloca float, align 4, addrspace(5)
  %"515" = alloca float, align 4, addrspace(5)
  %"516" = alloca float, align 4, addrspace(5)
  %"517" = alloca float, align 4, addrspace(5)
  %"518" = alloca float, align 4, addrspace(5)
  %"519" = alloca float, align 4, addrspace(5)
  %"520" = alloca float, align 4, addrspace(5)
  %"521" = alloca float, align 4, addrspace(5)
  %"522" = alloca float, align 4, addrspace(5)
  %"523" = alloca float, align 4, addrspace(5)
  %"524" = alloca float, align 4, addrspace(5)
  %"525" = alloca float, align 4, addrspace(5)
  %"526" = alloca float, align 4, addrspace(5)
  %"527" = alloca float, align 4, addrspace(5)
  %"528" = alloca float, align 4, addrspace(5)
  %"529" = alloca float, align 4, addrspace(5)
  %"530" = alloca float, align 4, addrspace(5)
  %"531" = alloca float, align 4, addrspace(5)
  %"532" = alloca float, align 4, addrspace(5)
  %"533" = alloca float, align 4, addrspace(5)
  %"534" = alloca float, align 4, addrspace(5)
  %"535" = alloca float, align 4, addrspace(5)
  %"536" = alloca float, align 4, addrspace(5)
  %"537" = alloca float, align 4, addrspace(5)
  %"538" = alloca float, align 4, addrspace(5)
  %"539" = alloca float, align 4, addrspace(5)
  %"540" = alloca float, align 4, addrspace(5)
  %"541" = alloca float, align 4, addrspace(5)
  %"542" = alloca float, align 4, addrspace(5)
  %"543" = alloca float, align 4, addrspace(5)
  %"544" = alloca float, align 4, addrspace(5)
  %"545" = alloca float, align 4, addrspace(5)
  %"546" = alloca float, align 4, addrspace(5)
  %"547" = alloca float, align 4, addrspace(5)
  %"548" = alloca float, align 4, addrspace(5)
  %"549" = alloca float, align 4, addrspace(5)
  %"550" = alloca float, align 4, addrspace(5)
  %"551" = alloca float, align 4, addrspace(5)
  %"552" = alloca float, align 4, addrspace(5)
  %"553" = alloca float, align 4, addrspace(5)
  %"554" = alloca float, align 4, addrspace(5)
  %"555" = alloca float, align 4, addrspace(5)
  %"556" = alloca float, align 4, addrspace(5)
  %"557" = alloca float, align 4, addrspace(5)
  %"558" = alloca float, align 4, addrspace(5)
  %"559" = alloca float, align 4, addrspace(5)
  %"560" = alloca float, align 4, addrspace(5)
  %"561" = alloca float, align 4, addrspace(5)
  %"562" = alloca float, align 4, addrspace(5)
  %"563" = alloca float, align 4, addrspace(5)
  %"564" = alloca float, align 4, addrspace(5)
  %"565" = alloca float, align 4, addrspace(5)
  %"566" = alloca float, align 4, addrspace(5)
  %"567" = alloca float, align 4, addrspace(5)
  %"568" = alloca float, align 4, addrspace(5)
  %"569" = alloca float, align 4, addrspace(5)
  %"570" = alloca float, align 4, addrspace(5)
  %"571" = alloca float, align 4, addrspace(5)
  %"572" = alloca float, align 4, addrspace(5)
  %"573" = alloca float, align 4, addrspace(5)
  %"574" = alloca float, align 4, addrspace(5)
  %"575" = alloca float, align 4, addrspace(5)
  %"576" = alloca float, align 4, addrspace(5)
  %"577" = alloca float, align 4, addrspace(5)
  %"578" = alloca float, align 4, addrspace(5)
  %"579" = alloca float, align 4, addrspace(5)
  %"580" = alloca float, align 4, addrspace(5)
  %"581" = alloca float, align 4, addrspace(5)
  %"582" = alloca float, align 4, addrspace(5)
  %"583" = alloca float, align 4, addrspace(5)
  %"584" = alloca float, align 4, addrspace(5)
  %"585" = alloca float, align 4, addrspace(5)
  %"586" = alloca float, align 4, addrspace(5)
  %"587" = alloca float, align 4, addrspace(5)
  %"588" = alloca float, align 4, addrspace(5)
  %"589" = alloca float, align 4, addrspace(5)
  %"590" = alloca float, align 4, addrspace(5)
  %"591" = alloca float, align 4, addrspace(5)
  %"592" = alloca float, align 4, addrspace(5)
  %"593" = alloca float, align 4, addrspace(5)
  %"594" = alloca float, align 4, addrspace(5)
  %"595" = alloca float, align 4, addrspace(5)
  %"596" = alloca float, align 4, addrspace(5)
  %"597" = alloca float, align 4, addrspace(5)
  %"598" = alloca float, align 4, addrspace(5)
  %"599" = alloca float, align 4, addrspace(5)
  %"600" = alloca float, align 4, addrspace(5)
  %"601" = alloca float, align 4, addrspace(5)
  %"602" = alloca float, align 4, addrspace(5)
  %"603" = alloca i1, align 1, addrspace(5)
  %"604" = alloca i1, align 1, addrspace(5)
  %"605" = alloca i1, align 1, addrspace(5)
  %"606" = alloca i1, align 1, addrspace(5)
  %"607" = alloca i1, align 1, addrspace(5)
  %"608" = alloca i1, align 1, addrspace(5)
  %"609" = alloca i1, align 1, addrspace(5)
  %"610" = alloca i1, align 1, addrspace(5)
  %"611" = alloca i1, align 1, addrspace(5)
  %"612" = alloca i1, align 1, addrspace(5)
  br label %1

1:                                                ; preds = %0
  br label %"378"

"378":                                            ; preds = %1
  %"283" = call i32 @llvm.nvvm.read.ptx.sreg.tid.x()
  store i32 %"283", ptr addrspace(5) %"383", align 4
  %"284" = call i32 @llvm.nvvm.read.ptx.sreg.ntid.x()
  store i32 %"284", ptr addrspace(5) %"384", align 4
  %2 = load i32, ptr addrspace(5) %"383", align 4
  %3 = lshr i32 %2, 5
  %"878" = select i1 false, i32 0, i32 %3
  store i32 %"878", ptr addrspace(5) %"385", align 4
  %4 = load i32, ptr addrspace(5) %"383", align 4
  %"617" = and i32 %4, 31
  store i32 %"617", ptr addrspace(5) %"386", align 4
  %5 = load i32, ptr addrspace(5) %"385", align 4
  %6 = shl i32 %5, 2
  %"619" = select i1 false, i32 0, i32 %6
  store i32 %"619", ptr addrspace(5) %"387", align 4
  store i32 ptrtoint (ptr addrspace(3) @partials_max to i32), ptr addrspace(5) %"473", align 4
  %7 = load i32, ptr addrspace(5) %"473", align 4
  %8 = load i32, ptr addrspace(5) %"387", align 4
  %"882" = add i32 %7, %8
  store i32 %"882", ptr addrspace(5) %"474", align 4
  store i32 ptrtoint (ptr addrspace(3) @partials_sum to i32), ptr addrspace(5) %"475", align 4
  %9 = load i32, ptr addrspace(5) %"475", align 4
  %10 = load i32, ptr addrspace(5) %"387", align 4
  %"887" = add i32 %9, %10
  store i32 %"887", ptr addrspace(5) %"476", align 4
  %11 = load i64, ptr addrspace(101) %"381", align 8
  store i64 %11, ptr addrspace(5) %"483", align 8
  %12 = load i64, ptr addrspace(101) %"382", align 8
  store i64 %12, ptr addrspace(5) %"484", align 8
  %13 = load i32, ptr addrspace(5) %"383", align 4
  %"892" = zext i32 %13 to i64
  store i64 %"892", ptr addrspace(5) %"485", align 8
  %14 = load i32, ptr addrspace(5) %"383", align 4
  %15 = load i64, ptr addrspace(5) %"483", align 8
  %16 = zext i32 %14 to i64
  %17 = mul i64 %16, 4
  %"894" = add i64 %17, %15
  store i64 %"894", ptr addrspace(5) %"486", align 8
  %18 = load i64, ptr addrspace(5) %"486", align 8
  %"897" = inttoptr i64 %18 to ptr addrspace(1)
  %"290" = getelementptr inbounds i8, ptr addrspace(1) %"897", i64 0
  %19 = load float, ptr addrspace(1) %"290", align 4
  store float %19, ptr addrspace(5) %"503", align 4
  %20 = load i64, ptr addrspace(5) %"486", align 8
  %"898" = inttoptr i64 %20 to ptr addrspace(1)
  %"292" = getelementptr inbounds i8, ptr addrspace(1) %"898", i64 512
  %21 = load float, ptr addrspace(1) %"292", align 4
  store float %21, ptr addrspace(5) %"504", align 4
  %22 = load i64, ptr addrspace(5) %"486", align 8
  %"899" = inttoptr i64 %22 to ptr addrspace(1)
  %"294" = getelementptr inbounds i8, ptr addrspace(1) %"899", i64 1024
  %23 = load float, ptr addrspace(1) %"294", align 4
  store float %23, ptr addrspace(5) %"505", align 4
  %24 = load i64, ptr addrspace(5) %"486", align 8
  %"900" = inttoptr i64 %24 to ptr addrspace(1)
  %"296" = getelementptr inbounds i8, ptr addrspace(1) %"900", i64 1536
  %25 = load float, ptr addrspace(1) %"296", align 4
  store float %25, ptr addrspace(5) %"506", align 4
  %26 = load i64, ptr addrspace(5) %"486", align 8
  %"901" = inttoptr i64 %26 to ptr addrspace(1)
  %"298" = getelementptr inbounds i8, ptr addrspace(1) %"901", i64 2048
  %27 = load float, ptr addrspace(1) %"298", align 4
  store float %27, ptr addrspace(5) %"507", align 4
  %28 = load i64, ptr addrspace(5) %"486", align 8
  %"902" = inttoptr i64 %28 to ptr addrspace(1)
  %"300" = getelementptr inbounds i8, ptr addrspace(1) %"902", i64 2560
  %29 = load float, ptr addrspace(1) %"300", align 4
  store float %29, ptr addrspace(5) %"508", align 4
  %30 = load i64, ptr addrspace(5) %"486", align 8
  %"903" = inttoptr i64 %30 to ptr addrspace(1)
  %"302" = getelementptr inbounds i8, ptr addrspace(1) %"903", i64 3072
  %31 = load float, ptr addrspace(1) %"302", align 4
  store float %31, ptr addrspace(5) %"509", align 4
  %32 = load i64, ptr addrspace(5) %"486", align 8
  %"904" = inttoptr i64 %32 to ptr addrspace(1)
  %"304" = getelementptr inbounds i8, ptr addrspace(1) %"904", i64 3584
  %33 = load float, ptr addrspace(1) %"304", align 4
  store float %33, ptr addrspace(5) %"510", align 4
  %34 = load float, ptr addrspace(5) %"503", align 4
  %35 = load float, ptr addrspace(5) %"504", align 4
  %36 = call float @llvm.maximumnum.f32(float %34, float %35)
  store float %36, ptr addrspace(5) %"513", align 4
  %37 = load float, ptr addrspace(5) %"505", align 4
  %38 = load float, ptr addrspace(5) %"506", align 4
  %39 = call float @llvm.maximumnum.f32(float %37, float %38)
  store float %39, ptr addrspace(5) %"514", align 4
  %40 = load float, ptr addrspace(5) %"507", align 4
  %41 = load float, ptr addrspace(5) %"508", align 4
  %42 = call float @llvm.maximumnum.f32(float %40, float %41)
  store float %42, ptr addrspace(5) %"515", align 4
  %43 = load float, ptr addrspace(5) %"509", align 4
  %44 = load float, ptr addrspace(5) %"510", align 4
  %45 = call float @llvm.maximumnum.f32(float %43, float %44)
  store float %45, ptr addrspace(5) %"516", align 4
  %46 = load float, ptr addrspace(5) %"513", align 4
  %47 = load float, ptr addrspace(5) %"514", align 4
  %48 = call float @llvm.maximumnum.f32(float %46, float %47)
  store float %48, ptr addrspace(5) %"517", align 4
  %49 = load float, ptr addrspace(5) %"515", align 4
  %50 = load float, ptr addrspace(5) %"516", align 4
  %51 = call float @llvm.maximumnum.f32(float %49, float %50)
  store float %51, ptr addrspace(5) %"518", align 4
  %52 = load float, ptr addrspace(5) %"517", align 4
  %53 = load float, ptr addrspace(5) %"518", align 4
  %54 = call float @llvm.maximumnum.f32(float %52, float %53)
  store float %54, ptr addrspace(5) %"519", align 4
  %55 = load float, ptr addrspace(5) %"519", align 4
  %"906" = bitcast float %55 to i32
  %"905" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"906", i32 16, i32 31, i32 -1)
  %"673" = bitcast i32 %"905" to float
  store float %"673", ptr addrspace(5) %"520", align 4
  %56 = load float, ptr addrspace(5) %"519", align 4
  %57 = load float, ptr addrspace(5) %"520", align 4
  %58 = call float @llvm.maximumnum.f32(float %56, float %57)
  store float %58, ptr addrspace(5) %"519", align 4
  %59 = load float, ptr addrspace(5) %"519", align 4
  %"908" = bitcast float %59 to i32
  %"907" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"908", i32 8, i32 31, i32 -1)
  %"678" = bitcast i32 %"907" to float
  store float %"678", ptr addrspace(5) %"520", align 4
  %60 = load float, ptr addrspace(5) %"519", align 4
  %61 = load float, ptr addrspace(5) %"520", align 4
  %62 = call float @llvm.maximumnum.f32(float %60, float %61)
  store float %62, ptr addrspace(5) %"519", align 4
  %63 = load float, ptr addrspace(5) %"519", align 4
  %"910" = bitcast float %63 to i32
  %"909" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"910", i32 4, i32 31, i32 -1)
  %"683" = bitcast i32 %"909" to float
  store float %"683", ptr addrspace(5) %"520", align 4
  %64 = load float, ptr addrspace(5) %"519", align 4
  %65 = load float, ptr addrspace(5) %"520", align 4
  %66 = call float @llvm.maximumnum.f32(float %64, float %65)
  store float %66, ptr addrspace(5) %"519", align 4
  %67 = load float, ptr addrspace(5) %"519", align 4
  %"912" = bitcast float %67 to i32
  %"911" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"912", i32 2, i32 31, i32 -1)
  %"688" = bitcast i32 %"911" to float
  store float %"688", ptr addrspace(5) %"520", align 4
  %68 = load float, ptr addrspace(5) %"519", align 4
  %69 = load float, ptr addrspace(5) %"520", align 4
  %70 = call float @llvm.maximumnum.f32(float %68, float %69)
  store float %70, ptr addrspace(5) %"519", align 4
  %71 = load float, ptr addrspace(5) %"519", align 4
  %"914" = bitcast float %71 to i32
  %"913" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"914", i32 1, i32 31, i32 -1)
  %"693" = bitcast i32 %"913" to float
  store float %"693", ptr addrspace(5) %"520", align 4
  %72 = load float, ptr addrspace(5) %"519", align 4
  %73 = load float, ptr addrspace(5) %"520", align 4
  %74 = call float @llvm.maximumnum.f32(float %72, float %73)
  store float %74, ptr addrspace(5) %"519", align 4
  %75 = load i32, ptr addrspace(5) %"386", align 4
  %76 = icmp eq i32 %75, 0
  store i1 %76, ptr addrspace(5) %"603", align 1
  %77 = load i1, ptr addrspace(5) %"603", align 1
  br i1 %77, label %"245", label %"246"

"245":                                            ; preds = %"378"
  %78 = load i32, ptr addrspace(5) %"474", align 4
  %79 = load float, ptr addrspace(5) %"519", align 4
  %"916" = inttoptr i32 %78 to ptr addrspace(3)
  store float %79, ptr addrspace(3) %"916", align 4
  br label %"246"

"246":                                            ; preds = %"245", %"378"
  call void @__zluda_ptx_impl_bar_sync(i32 0)
  %80 = load float, ptr addrspace(3) @partials_max, align 4
  store float %80, ptr addrspace(5) %"523", align 4
  %81 = load float, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @partials_max, i64 4), align 4
  store float %81, ptr addrspace(5) %"524", align 4
  %82 = load float, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @partials_max, i64 8), align 4
  store float %82, ptr addrspace(5) %"525", align 4
  %83 = load float, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @partials_max, i64 12), align 4
  store float %83, ptr addrspace(5) %"526", align 4
  %84 = load float, ptr addrspace(5) %"523", align 4
  %85 = load float, ptr addrspace(5) %"524", align 4
  %86 = call float @llvm.maximumnum.f32(float %84, float %85)
  store float %86, ptr addrspace(5) %"527", align 4
  %87 = load float, ptr addrspace(5) %"525", align 4
  %88 = load float, ptr addrspace(5) %"526", align 4
  %89 = call float @llvm.maximumnum.f32(float %87, float %88)
  store float %89, ptr addrspace(5) %"528", align 4
  %90 = load float, ptr addrspace(5) %"527", align 4
  %91 = load float, ptr addrspace(5) %"528", align 4
  %92 = call float @llvm.maximumnum.f32(float %90, float %91)
  store float %92, ptr addrspace(5) %"529", align 4
  %93 = load float, ptr addrspace(5) %"503", align 4
  %94 = load float, ptr addrspace(5) %"529", align 4
  %"716" = fsub float %93, %94
  store float %"716", ptr addrspace(5) %"533", align 4
  %95 = load float, ptr addrspace(5) %"533", align 4
  %"719" = fmul float %95, 0x3FF7154760000000
  store float %"719", ptr addrspace(5) %"533", align 4
  %96 = load float, ptr addrspace(5) %"533", align 4
  %"721" = call float @llvm.nvvm.ex2.approx.f(float %96)
  store float %"721", ptr addrspace(5) %"533", align 4
  %97 = load float, ptr addrspace(5) %"504", align 4
  %98 = load float, ptr addrspace(5) %"529", align 4
  %"723" = fsub float %97, %98
  store float %"723", ptr addrspace(5) %"534", align 4
  %99 = load float, ptr addrspace(5) %"534", align 4
  %"726" = fmul float %99, 0x3FF7154760000000
  store float %"726", ptr addrspace(5) %"534", align 4
  %100 = load float, ptr addrspace(5) %"534", align 4
  %"728" = call float @llvm.nvvm.ex2.approx.f(float %100)
  store float %"728", ptr addrspace(5) %"534", align 4
  %101 = load float, ptr addrspace(5) %"505", align 4
  %102 = load float, ptr addrspace(5) %"529", align 4
  %"730" = fsub float %101, %102
  store float %"730", ptr addrspace(5) %"535", align 4
  %103 = load float, ptr addrspace(5) %"535", align 4
  %"733" = fmul float %103, 0x3FF7154760000000
  store float %"733", ptr addrspace(5) %"535", align 4
  %104 = load float, ptr addrspace(5) %"535", align 4
  %"735" = call float @llvm.nvvm.ex2.approx.f(float %104)
  store float %"735", ptr addrspace(5) %"535", align 4
  %105 = load float, ptr addrspace(5) %"506", align 4
  %106 = load float, ptr addrspace(5) %"529", align 4
  %"737" = fsub float %105, %106
  store float %"737", ptr addrspace(5) %"536", align 4
  %107 = load float, ptr addrspace(5) %"536", align 4
  %"740" = fmul float %107, 0x3FF7154760000000
  store float %"740", ptr addrspace(5) %"536", align 4
  %108 = load float, ptr addrspace(5) %"536", align 4
  %"742" = call float @llvm.nvvm.ex2.approx.f(float %108)
  store float %"742", ptr addrspace(5) %"536", align 4
  %109 = load float, ptr addrspace(5) %"507", align 4
  %110 = load float, ptr addrspace(5) %"529", align 4
  %"744" = fsub float %109, %110
  store float %"744", ptr addrspace(5) %"537", align 4
  %111 = load float, ptr addrspace(5) %"537", align 4
  %"747" = fmul float %111, 0x3FF7154760000000
  store float %"747", ptr addrspace(5) %"537", align 4
  %112 = load float, ptr addrspace(5) %"537", align 4
  %"749" = call float @llvm.nvvm.ex2.approx.f(float %112)
  store float %"749", ptr addrspace(5) %"537", align 4
  %113 = load float, ptr addrspace(5) %"508", align 4
  %114 = load float, ptr addrspace(5) %"529", align 4
  %"751" = fsub float %113, %114
  store float %"751", ptr addrspace(5) %"538", align 4
  %115 = load float, ptr addrspace(5) %"538", align 4
  %"754" = fmul float %115, 0x3FF7154760000000
  store float %"754", ptr addrspace(5) %"538", align 4
  %116 = load float, ptr addrspace(5) %"538", align 4
  %"756" = call float @llvm.nvvm.ex2.approx.f(float %116)
  store float %"756", ptr addrspace(5) %"538", align 4
  %117 = load float, ptr addrspace(5) %"509", align 4
  %118 = load float, ptr addrspace(5) %"529", align 4
  %"758" = fsub float %117, %118
  store float %"758", ptr addrspace(5) %"539", align 4
  %119 = load float, ptr addrspace(5) %"539", align 4
  %"761" = fmul float %119, 0x3FF7154760000000
  store float %"761", ptr addrspace(5) %"539", align 4
  %120 = load float, ptr addrspace(5) %"539", align 4
  %"763" = call float @llvm.nvvm.ex2.approx.f(float %120)
  store float %"763", ptr addrspace(5) %"539", align 4
  %121 = load float, ptr addrspace(5) %"510", align 4
  %122 = load float, ptr addrspace(5) %"529", align 4
  %"765" = fsub float %121, %122
  store float %"765", ptr addrspace(5) %"540", align 4
  %123 = load float, ptr addrspace(5) %"540", align 4
  %"768" = fmul float %123, 0x3FF7154760000000
  store float %"768", ptr addrspace(5) %"540", align 4
  %124 = load float, ptr addrspace(5) %"540", align 4
  %"770" = call float @llvm.nvvm.ex2.approx.f(float %124)
  store float %"770", ptr addrspace(5) %"540", align 4
  %125 = load float, ptr addrspace(5) %"533", align 4
  %126 = load float, ptr addrspace(5) %"534", align 4
  %"772" = fadd float %125, %126
  store float %"772", ptr addrspace(5) %"543", align 4
  %127 = load float, ptr addrspace(5) %"535", align 4
  %128 = load float, ptr addrspace(5) %"536", align 4
  %"775" = fadd float %127, %128
  store float %"775", ptr addrspace(5) %"544", align 4
  %129 = load float, ptr addrspace(5) %"537", align 4
  %130 = load float, ptr addrspace(5) %"538", align 4
  %"778" = fadd float %129, %130
  store float %"778", ptr addrspace(5) %"545", align 4
  %131 = load float, ptr addrspace(5) %"539", align 4
  %132 = load float, ptr addrspace(5) %"540", align 4
  %"781" = fadd float %131, %132
  store float %"781", ptr addrspace(5) %"546", align 4
  %133 = load float, ptr addrspace(5) %"543", align 4
  %134 = load float, ptr addrspace(5) %"544", align 4
  %"784" = fadd float %133, %134
  store float %"784", ptr addrspace(5) %"547", align 4
  %135 = load float, ptr addrspace(5) %"545", align 4
  %136 = load float, ptr addrspace(5) %"546", align 4
  %"787" = fadd float %135, %136
  store float %"787", ptr addrspace(5) %"548", align 4
  %137 = load float, ptr addrspace(5) %"547", align 4
  %138 = load float, ptr addrspace(5) %"548", align 4
  %"790" = fadd float %137, %138
  store float %"790", ptr addrspace(5) %"549", align 4
  %139 = load float, ptr addrspace(5) %"549", align 4
  %"922" = bitcast float %139 to i32
  %"921" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"922", i32 16, i32 31, i32 -1)
  %"793" = bitcast i32 %"921" to float
  store float %"793", ptr addrspace(5) %"550", align 4
  %140 = load float, ptr addrspace(5) %"549", align 4
  %141 = load float, ptr addrspace(5) %"550", align 4
  %"795" = fadd float %140, %141
  store float %"795", ptr addrspace(5) %"549", align 4
  %142 = load float, ptr addrspace(5) %"549", align 4
  %"924" = bitcast float %142 to i32
  %"923" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"924", i32 8, i32 31, i32 -1)
  %"798" = bitcast i32 %"923" to float
  store float %"798", ptr addrspace(5) %"550", align 4
  %143 = load float, ptr addrspace(5) %"549", align 4
  %144 = load float, ptr addrspace(5) %"550", align 4
  %"800" = fadd float %143, %144
  store float %"800", ptr addrspace(5) %"549", align 4
  %145 = load float, ptr addrspace(5) %"549", align 4
  %"926" = bitcast float %145 to i32
  %"925" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"926", i32 4, i32 31, i32 -1)
  %"803" = bitcast i32 %"925" to float
  store float %"803", ptr addrspace(5) %"550", align 4
  %146 = load float, ptr addrspace(5) %"549", align 4
  %147 = load float, ptr addrspace(5) %"550", align 4
  %"805" = fadd float %146, %147
  store float %"805", ptr addrspace(5) %"549", align 4
  %148 = load float, ptr addrspace(5) %"549", align 4
  %"928" = bitcast float %148 to i32
  %"927" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"928", i32 2, i32 31, i32 -1)
  %"808" = bitcast i32 %"927" to float
  store float %"808", ptr addrspace(5) %"550", align 4
  %149 = load float, ptr addrspace(5) %"549", align 4
  %150 = load float, ptr addrspace(5) %"550", align 4
  %"810" = fadd float %149, %150
  store float %"810", ptr addrspace(5) %"549", align 4
  %151 = load float, ptr addrspace(5) %"549", align 4
  %"930" = bitcast float %151 to i32
  %"929" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"930", i32 1, i32 31, i32 -1)
  %"813" = bitcast i32 %"929" to float
  store float %"813", ptr addrspace(5) %"550", align 4
  %152 = load float, ptr addrspace(5) %"549", align 4
  %153 = load float, ptr addrspace(5) %"550", align 4
  %"815" = fadd float %152, %153
  store float %"815", ptr addrspace(5) %"549", align 4
  %154 = load i1, ptr addrspace(5) %"603", align 1
  br i1 %154, label %"247", label %"248"

"247":                                            ; preds = %"246"
  %155 = load i32, ptr addrspace(5) %"476", align 4
  %156 = load float, ptr addrspace(5) %"549", align 4
  %"931" = inttoptr i32 %155 to ptr addrspace(3)
  store float %156, ptr addrspace(3) %"931", align 4
  br label %"248"

"248":                                            ; preds = %"247", %"246"
  call void @__zluda_ptx_impl_bar_sync(i32 0)
  %157 = load float, ptr addrspace(3) @partials_sum, align 4
  store float %157, ptr addrspace(5) %"553", align 4
  %158 = load float, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @partials_sum, i64 4), align 4
  store float %158, ptr addrspace(5) %"554", align 4
  %159 = load float, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @partials_sum, i64 8), align 4
  store float %159, ptr addrspace(5) %"555", align 4
  %160 = load float, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @partials_sum, i64 12), align 4
  store float %160, ptr addrspace(5) %"556", align 4
  %161 = load float, ptr addrspace(5) %"553", align 4
  %162 = load float, ptr addrspace(5) %"554", align 4
  %"825" = fadd float %161, %162
  store float %"825", ptr addrspace(5) %"557", align 4
  %163 = load float, ptr addrspace(5) %"555", align 4
  %164 = load float, ptr addrspace(5) %"556", align 4
  %"828" = fadd float %163, %164
  store float %"828", ptr addrspace(5) %"558", align 4
  %165 = load float, ptr addrspace(5) %"557", align 4
  %166 = load float, ptr addrspace(5) %"558", align 4
  %"831" = fadd float %165, %166
  store float %"831", ptr addrspace(5) %"559", align 4
  %167 = load float, ptr addrspace(5) %"559", align 4
  %"834" = call float @llvm.nvvm.rcp.approx.f(float %167)
  store float %"834", ptr addrspace(5) %"563", align 4
  %168 = load float, ptr addrspace(5) %"533", align 4
  %169 = load float, ptr addrspace(5) %"563", align 4
  %"836" = fmul float %168, %169
  store float %"836", ptr addrspace(5) %"573", align 4
  %170 = load float, ptr addrspace(5) %"534", align 4
  %171 = load float, ptr addrspace(5) %"563", align 4
  %"839" = fmul float %170, %171
  store float %"839", ptr addrspace(5) %"574", align 4
  %172 = load float, ptr addrspace(5) %"535", align 4
  %173 = load float, ptr addrspace(5) %"563", align 4
  %"842" = fmul float %172, %173
  store float %"842", ptr addrspace(5) %"575", align 4
  %174 = load float, ptr addrspace(5) %"536", align 4
  %175 = load float, ptr addrspace(5) %"563", align 4
  %"845" = fmul float %174, %175
  store float %"845", ptr addrspace(5) %"576", align 4
  %176 = load float, ptr addrspace(5) %"537", align 4
  %177 = load float, ptr addrspace(5) %"563", align 4
  %"848" = fmul float %176, %177
  store float %"848", ptr addrspace(5) %"577", align 4
  %178 = load float, ptr addrspace(5) %"538", align 4
  %179 = load float, ptr addrspace(5) %"563", align 4
  %"851" = fmul float %178, %179
  store float %"851", ptr addrspace(5) %"578", align 4
  %180 = load float, ptr addrspace(5) %"539", align 4
  %181 = load float, ptr addrspace(5) %"563", align 4
  %"854" = fmul float %180, %181
  store float %"854", ptr addrspace(5) %"579", align 4
  %182 = load float, ptr addrspace(5) %"540", align 4
  %183 = load float, ptr addrspace(5) %"563", align 4
  %"857" = fmul float %182, %183
  store float %"857", ptr addrspace(5) %"580", align 4
  %184 = load i64, ptr addrspace(5) %"486", align 8
  %"936" = inttoptr i64 %184 to ptr addrspace(1)
  %"363" = getelementptr inbounds i8, ptr addrspace(1) %"936", i64 0
  %185 = load float, ptr addrspace(5) %"573", align 4
  store float %185, ptr addrspace(1) %"363", align 4
  %186 = load i64, ptr addrspace(5) %"486", align 8
  %"937" = inttoptr i64 %186 to ptr addrspace(1)
  %"365" = getelementptr inbounds i8, ptr addrspace(1) %"937", i64 512
  %187 = load float, ptr addrspace(5) %"574", align 4
  store float %187, ptr addrspace(1) %"365", align 4
  %188 = load i64, ptr addrspace(5) %"486", align 8
  %"938" = inttoptr i64 %188 to ptr addrspace(1)
  %"367" = getelementptr inbounds i8, ptr addrspace(1) %"938", i64 1024
  %189 = load float, ptr addrspace(5) %"575", align 4
  store float %189, ptr addrspace(1) %"367", align 4
  %190 = load i64, ptr addrspace(5) %"486", align 8
  %"939" = inttoptr i64 %190 to ptr addrspace(1)
  %"369" = getelementptr inbounds i8, ptr addrspace(1) %"939", i64 1536
  %191 = load float, ptr addrspace(5) %"576", align 4
  store float %191, ptr addrspace(1) %"369", align 4
  %192 = load i64, ptr addrspace(5) %"486", align 8
  %"940" = inttoptr i64 %192 to ptr addrspace(1)
  %"371" = getelementptr inbounds i8, ptr addrspace(1) %"940", i64 2048
  %193 = load float, ptr addrspace(5) %"577", align 4
  store float %193, ptr addrspace(1) %"371", align 4
  %194 = load i64, ptr addrspace(5) %"486", align 8
  %"941" = inttoptr i64 %194 to ptr addrspace(1)
  %"373" = getelementptr inbounds i8, ptr addrspace(1) %"941", i64 2560
  %195 = load float, ptr addrspace(5) %"578", align 4
  store float %195, ptr addrspace(1) %"373", align 4
  %196 = load i64, ptr addrspace(5) %"486", align 8
  %"942" = inttoptr i64 %196 to ptr addrspace(1)
  %"375" = getelementptr inbounds i8, ptr addrspace(1) %"942", i64 3072
  %197 = load float, ptr addrspace(5) %"579", align 4
  store float %197, ptr addrspace(1) %"375", align 4
  %198 = load i64, ptr addrspace(5) %"486", align 8
  %"943" = inttoptr i64 %198 to ptr addrspace(1)
  %"377" = getelementptr inbounds i8, ptr addrspace(1) %"943", i64 3584
  %199 = load float, ptr addrspace(5) %"580", align 4
  store float %199, ptr addrspace(1) %"377", align 4
  ret void
}

; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare float @llvm.maximumnum.f32(float, float) #4

attributes #0 = { "denormal-fp-math"="dynamic" "denormal-fp-math-f32"="dynamic" "no-trapping-math"="true" "target-cpu"="sm_110" }
attributes #1 = { nocallback nofree nosync nounwind willreturn memory(none) "denormal-fp-math"="dynamic" "denormal-fp-math-f32"="dynamic" "no-trapping-math"="true" "target-cpu"="sm_110" }
attributes #2 = { nocallback nofree nosync nounwind speculatable willreturn memory(none) "denormal-fp-math"="dynamic" "denormal-fp-math-f32"="dynamic" "no-trapping-math"="true" "target-cpu"="sm_110" }
attributes #3 = { "denormal-fp-math"="preserve-sign" "denormal-fp-math-f32"="ieee" "no-trapping-math"="true" "target-cpu"="sm_110" }
attributes #4 = { nocallback nofree nosync nounwind speculatable willreturn memory(none) }
