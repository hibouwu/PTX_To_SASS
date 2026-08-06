
%struct.f32.f32.f32.i8 = type { float, float, float, i8 }

@partials_sum = external addrspace(3) global [16 x i8], align 4
@partials_sumsq = external addrspace(3) global [16 x i8], align 4

declare hidden void @__zluda_ptx_impl_bar_sync(i32) #0

; Function Attrs: nocallback nofree nosync nounwind willreturn memory(none)
declare hidden float @llvm.nvvm.rsqrt.approx.f(float) #1

declare hidden i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32, i32, i32, i32) #0

declare hidden %struct.f32.f32.f32.i8 @__zluda_ptx_impl_div_f32_part1(float, float) #0

declare hidden float @__zluda_ptx_impl_div_f32_part2(float, float, float, float, float, i8) #0

; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare hidden noundef range(i32 0, 1024) i32 @llvm.nvvm.read.ptx.sreg.tid.x() #2

; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare hidden noundef range(i32 1, 1025) i32 @llvm.nvvm.read.ptx.sreg.ntid.x() #2

define ptx_kernel void @layernorm(ptr addrspace(101) byref(i64) %"433", ptr addrspace(101) byref(i64) %"434", ptr addrspace(101) byref(i64) %"435", ptr addrspace(101) byref(i64) %"436") #3 {
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
  %"483" = alloca i32, align 4, addrspace(5)
  %"484" = alloca i32, align 4, addrspace(5)
  %"485" = alloca i32, align 4, addrspace(5)
  %"486" = alloca i32, align 4, addrspace(5)
  %"487" = alloca i32, align 4, addrspace(5)
  %"488" = alloca i32, align 4, addrspace(5)
  %"489" = alloca i32, align 4, addrspace(5)
  %"490" = alloca i32, align 4, addrspace(5)
  %"491" = alloca i32, align 4, addrspace(5)
  %"492" = alloca i32, align 4, addrspace(5)
  %"493" = alloca i32, align 4, addrspace(5)
  %"494" = alloca i32, align 4, addrspace(5)
  %"495" = alloca i32, align 4, addrspace(5)
  %"496" = alloca i32, align 4, addrspace(5)
  %"497" = alloca i32, align 4, addrspace(5)
  %"498" = alloca i32, align 4, addrspace(5)
  %"499" = alloca i32, align 4, addrspace(5)
  %"500" = alloca i32, align 4, addrspace(5)
  %"501" = alloca i32, align 4, addrspace(5)
  %"502" = alloca i32, align 4, addrspace(5)
  %"503" = alloca i32, align 4, addrspace(5)
  %"504" = alloca i32, align 4, addrspace(5)
  %"505" = alloca i32, align 4, addrspace(5)
  %"506" = alloca i32, align 4, addrspace(5)
  %"507" = alloca i32, align 4, addrspace(5)
  %"508" = alloca i32, align 4, addrspace(5)
  %"509" = alloca i32, align 4, addrspace(5)
  %"510" = alloca i32, align 4, addrspace(5)
  %"511" = alloca i32, align 4, addrspace(5)
  %"512" = alloca i32, align 4, addrspace(5)
  %"513" = alloca i32, align 4, addrspace(5)
  %"514" = alloca i32, align 4, addrspace(5)
  %"515" = alloca i32, align 4, addrspace(5)
  %"516" = alloca i32, align 4, addrspace(5)
  %"517" = alloca i32, align 4, addrspace(5)
  %"518" = alloca i32, align 4, addrspace(5)
  %"519" = alloca i32, align 4, addrspace(5)
  %"520" = alloca i32, align 4, addrspace(5)
  %"521" = alloca i32, align 4, addrspace(5)
  %"522" = alloca i32, align 4, addrspace(5)
  %"523" = alloca i32, align 4, addrspace(5)
  %"524" = alloca i32, align 4, addrspace(5)
  %"525" = alloca i32, align 4, addrspace(5)
  %"526" = alloca i32, align 4, addrspace(5)
  %"527" = alloca i32, align 4, addrspace(5)
  %"528" = alloca i32, align 4, addrspace(5)
  %"529" = alloca i32, align 4, addrspace(5)
  %"530" = alloca i32, align 4, addrspace(5)
  %"531" = alloca i32, align 4, addrspace(5)
  %"532" = alloca i32, align 4, addrspace(5)
  %"533" = alloca i32, align 4, addrspace(5)
  %"534" = alloca i32, align 4, addrspace(5)
  %"535" = alloca i32, align 4, addrspace(5)
  %"536" = alloca i32, align 4, addrspace(5)
  %"537" = alloca i64, align 8, addrspace(5)
  %"538" = alloca i64, align 8, addrspace(5)
  %"539" = alloca i64, align 8, addrspace(5)
  %"540" = alloca i64, align 8, addrspace(5)
  %"541" = alloca i64, align 8, addrspace(5)
  %"542" = alloca i64, align 8, addrspace(5)
  %"543" = alloca i64, align 8, addrspace(5)
  %"544" = alloca i64, align 8, addrspace(5)
  %"545" = alloca i64, align 8, addrspace(5)
  %"546" = alloca i64, align 8, addrspace(5)
  %"547" = alloca i64, align 8, addrspace(5)
  %"548" = alloca i64, align 8, addrspace(5)
  %"549" = alloca i64, align 8, addrspace(5)
  %"550" = alloca i64, align 8, addrspace(5)
  %"551" = alloca i64, align 8, addrspace(5)
  %"552" = alloca i64, align 8, addrspace(5)
  %"553" = alloca i64, align 8, addrspace(5)
  %"554" = alloca i64, align 8, addrspace(5)
  %"555" = alloca i64, align 8, addrspace(5)
  %"556" = alloca i64, align 8, addrspace(5)
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
  %"603" = alloca float, align 4, addrspace(5)
  %"604" = alloca float, align 4, addrspace(5)
  %"605" = alloca float, align 4, addrspace(5)
  %"606" = alloca float, align 4, addrspace(5)
  %"607" = alloca float, align 4, addrspace(5)
  %"608" = alloca float, align 4, addrspace(5)
  %"609" = alloca float, align 4, addrspace(5)
  %"610" = alloca float, align 4, addrspace(5)
  %"611" = alloca float, align 4, addrspace(5)
  %"612" = alloca float, align 4, addrspace(5)
  %"613" = alloca float, align 4, addrspace(5)
  %"614" = alloca float, align 4, addrspace(5)
  %"615" = alloca float, align 4, addrspace(5)
  %"616" = alloca float, align 4, addrspace(5)
  %"617" = alloca float, align 4, addrspace(5)
  %"618" = alloca float, align 4, addrspace(5)
  %"619" = alloca float, align 4, addrspace(5)
  %"620" = alloca float, align 4, addrspace(5)
  %"621" = alloca float, align 4, addrspace(5)
  %"622" = alloca float, align 4, addrspace(5)
  %"623" = alloca float, align 4, addrspace(5)
  %"624" = alloca float, align 4, addrspace(5)
  %"625" = alloca float, align 4, addrspace(5)
  %"626" = alloca float, align 4, addrspace(5)
  %"627" = alloca float, align 4, addrspace(5)
  %"628" = alloca float, align 4, addrspace(5)
  %"629" = alloca float, align 4, addrspace(5)
  %"630" = alloca float, align 4, addrspace(5)
  %"631" = alloca float, align 4, addrspace(5)
  %"632" = alloca float, align 4, addrspace(5)
  %"633" = alloca float, align 4, addrspace(5)
  %"634" = alloca float, align 4, addrspace(5)
  %"635" = alloca float, align 4, addrspace(5)
  %"636" = alloca float, align 4, addrspace(5)
  %"637" = alloca float, align 4, addrspace(5)
  %"638" = alloca float, align 4, addrspace(5)
  %"639" = alloca float, align 4, addrspace(5)
  %"640" = alloca float, align 4, addrspace(5)
  %"641" = alloca float, align 4, addrspace(5)
  %"642" = alloca float, align 4, addrspace(5)
  %"643" = alloca float, align 4, addrspace(5)
  %"644" = alloca float, align 4, addrspace(5)
  %"645" = alloca float, align 4, addrspace(5)
  %"646" = alloca float, align 4, addrspace(5)
  %"647" = alloca float, align 4, addrspace(5)
  %"648" = alloca float, align 4, addrspace(5)
  %"649" = alloca float, align 4, addrspace(5)
  %"650" = alloca float, align 4, addrspace(5)
  %"651" = alloca float, align 4, addrspace(5)
  %"652" = alloca float, align 4, addrspace(5)
  %"653" = alloca float, align 4, addrspace(5)
  %"654" = alloca float, align 4, addrspace(5)
  %"655" = alloca float, align 4, addrspace(5)
  %"656" = alloca float, align 4, addrspace(5)
  %"657" = alloca float, align 4, addrspace(5)
  %"658" = alloca float, align 4, addrspace(5)
  %"659" = alloca float, align 4, addrspace(5)
  %"660" = alloca float, align 4, addrspace(5)
  %"661" = alloca float, align 4, addrspace(5)
  %"662" = alloca float, align 4, addrspace(5)
  %"663" = alloca float, align 4, addrspace(5)
  %"664" = alloca float, align 4, addrspace(5)
  %"665" = alloca float, align 4, addrspace(5)
  %"666" = alloca float, align 4, addrspace(5)
  %"667" = alloca float, align 4, addrspace(5)
  %"668" = alloca float, align 4, addrspace(5)
  %"669" = alloca float, align 4, addrspace(5)
  %"670" = alloca float, align 4, addrspace(5)
  %"671" = alloca float, align 4, addrspace(5)
  %"672" = alloca float, align 4, addrspace(5)
  %"673" = alloca float, align 4, addrspace(5)
  %"674" = alloca float, align 4, addrspace(5)
  %"675" = alloca float, align 4, addrspace(5)
  %"676" = alloca float, align 4, addrspace(5)
  %"677" = alloca i1, align 1, addrspace(5)
  %"678" = alloca i1, align 1, addrspace(5)
  %"679" = alloca i1, align 1, addrspace(5)
  %"680" = alloca i1, align 1, addrspace(5)
  %"681" = alloca i1, align 1, addrspace(5)
  %"682" = alloca i1, align 1, addrspace(5)
  %"683" = alloca i1, align 1, addrspace(5)
  %"684" = alloca i1, align 1, addrspace(5)
  %"685" = alloca i1, align 1, addrspace(5)
  %"686" = alloca i1, align 1, addrspace(5)
  br label %1

1:                                                ; preds = %0
  br label %"425"

"425":                                            ; preds = %1
  %"305" = call i32 @llvm.nvvm.read.ptx.sreg.tid.x()
  store i32 %"305", ptr addrspace(5) %"437", align 4
  %"306" = call i32 @llvm.nvvm.read.ptx.sreg.ntid.x()
  store i32 %"306", ptr addrspace(5) %"438", align 4
  %2 = load i32, ptr addrspace(5) %"437", align 4
  %3 = lshr i32 %2, 5
  %"902" = select i1 false, i32 0, i32 %3
  store i32 %"902", ptr addrspace(5) %"439", align 4
  %4 = load i32, ptr addrspace(5) %"437", align 4
  %"691" = and i32 %4, 31
  store i32 %"691", ptr addrspace(5) %"440", align 4
  %5 = load i32, ptr addrspace(5) %"439", align 4
  %6 = shl i32 %5, 2
  %"693" = select i1 false, i32 0, i32 %6
  store i32 %"693", ptr addrspace(5) %"441", align 4
  store i32 ptrtoint (ptr addrspace(3) @partials_sum to i32), ptr addrspace(5) %"527", align 4
  %7 = load i32, ptr addrspace(5) %"527", align 4
  %8 = load i32, ptr addrspace(5) %"441", align 4
  %"906" = add i32 %7, %8
  store i32 %"906", ptr addrspace(5) %"528", align 4
  store i32 ptrtoint (ptr addrspace(3) @partials_sumsq to i32), ptr addrspace(5) %"529", align 4
  %9 = load i32, ptr addrspace(5) %"529", align 4
  %10 = load i32, ptr addrspace(5) %"441", align 4
  %"911" = add i32 %9, %10
  store i32 %"911", ptr addrspace(5) %"530", align 4
  %11 = load i64, ptr addrspace(101) %"433", align 8
  store i64 %11, ptr addrspace(5) %"537", align 8
  %12 = load i64, ptr addrspace(101) %"434", align 8
  store i64 %12, ptr addrspace(5) %"538", align 8
  %13 = load i64, ptr addrspace(101) %"435", align 8
  store i64 %13, ptr addrspace(5) %"539", align 8
  %14 = load i64, ptr addrspace(101) %"436", align 8
  store i64 %14, ptr addrspace(5) %"540", align 8
  %15 = load i32, ptr addrspace(5) %"437", align 4
  %16 = load i64, ptr addrspace(5) %"537", align 8
  %17 = zext i32 %15 to i64
  %18 = mul i64 %17, 4
  %"918" = add i64 %18, %16
  store i64 %"918", ptr addrspace(5) %"541", align 8
  %19 = load i32, ptr addrspace(5) %"437", align 4
  %20 = load i64, ptr addrspace(5) %"539", align 8
  %21 = zext i32 %19 to i64
  %22 = mul i64 %21, 4
  %"921" = add i64 %22, %20
  store i64 %"921", ptr addrspace(5) %"542", align 8
  %23 = load i32, ptr addrspace(5) %"437", align 4
  %24 = load i64, ptr addrspace(5) %"540", align 8
  %25 = zext i32 %23 to i64
  %26 = mul i64 %25, 4
  %"924" = add i64 %26, %24
  store i64 %"924", ptr addrspace(5) %"543", align 8
  %27 = load i64, ptr addrspace(5) %"541", align 8
  %"927" = inttoptr i64 %27 to ptr addrspace(1)
  %"314" = getelementptr inbounds i8, ptr addrspace(1) %"927", i64 0
  %28 = load float, ptr addrspace(1) %"314", align 4
  store float %28, ptr addrspace(5) %"557", align 4
  %29 = load i64, ptr addrspace(5) %"541", align 8
  %"928" = inttoptr i64 %29 to ptr addrspace(1)
  %"316" = getelementptr inbounds i8, ptr addrspace(1) %"928", i64 512
  %30 = load float, ptr addrspace(1) %"316", align 4
  store float %30, ptr addrspace(5) %"558", align 4
  %31 = load i64, ptr addrspace(5) %"541", align 8
  %"929" = inttoptr i64 %31 to ptr addrspace(1)
  %"318" = getelementptr inbounds i8, ptr addrspace(1) %"929", i64 1024
  %32 = load float, ptr addrspace(1) %"318", align 4
  store float %32, ptr addrspace(5) %"559", align 4
  %33 = load i64, ptr addrspace(5) %"541", align 8
  %"930" = inttoptr i64 %33 to ptr addrspace(1)
  %"320" = getelementptr inbounds i8, ptr addrspace(1) %"930", i64 1536
  %34 = load float, ptr addrspace(1) %"320", align 4
  store float %34, ptr addrspace(5) %"560", align 4
  %35 = load i64, ptr addrspace(5) %"541", align 8
  %"931" = inttoptr i64 %35 to ptr addrspace(1)
  %"322" = getelementptr inbounds i8, ptr addrspace(1) %"931", i64 2048
  %36 = load float, ptr addrspace(1) %"322", align 4
  store float %36, ptr addrspace(5) %"561", align 4
  %37 = load i64, ptr addrspace(5) %"541", align 8
  %"932" = inttoptr i64 %37 to ptr addrspace(1)
  %"324" = getelementptr inbounds i8, ptr addrspace(1) %"932", i64 2560
  %38 = load float, ptr addrspace(1) %"324", align 4
  store float %38, ptr addrspace(5) %"562", align 4
  %39 = load i64, ptr addrspace(5) %"541", align 8
  %"933" = inttoptr i64 %39 to ptr addrspace(1)
  %"326" = getelementptr inbounds i8, ptr addrspace(1) %"933", i64 3072
  %40 = load float, ptr addrspace(1) %"326", align 4
  store float %40, ptr addrspace(5) %"563", align 4
  %41 = load i64, ptr addrspace(5) %"541", align 8
  %"934" = inttoptr i64 %41 to ptr addrspace(1)
  %"328" = getelementptr inbounds i8, ptr addrspace(1) %"934", i64 3584
  %42 = load float, ptr addrspace(1) %"328", align 4
  store float %42, ptr addrspace(5) %"564", align 4
  %43 = load float, ptr addrspace(5) %"557", align 4
  %44 = load float, ptr addrspace(5) %"558", align 4
  %"732" = fadd float %43, %44
  store float %"732", ptr addrspace(5) %"567", align 4
  %45 = load float, ptr addrspace(5) %"559", align 4
  %46 = load float, ptr addrspace(5) %"560", align 4
  %"735" = fadd float %45, %46
  store float %"735", ptr addrspace(5) %"568", align 4
  %47 = load float, ptr addrspace(5) %"561", align 4
  %48 = load float, ptr addrspace(5) %"562", align 4
  %"738" = fadd float %47, %48
  store float %"738", ptr addrspace(5) %"569", align 4
  %49 = load float, ptr addrspace(5) %"563", align 4
  %50 = load float, ptr addrspace(5) %"564", align 4
  %"741" = fadd float %49, %50
  store float %"741", ptr addrspace(5) %"570", align 4
  %51 = load float, ptr addrspace(5) %"567", align 4
  %52 = load float, ptr addrspace(5) %"568", align 4
  %"744" = fadd float %51, %52
  store float %"744", ptr addrspace(5) %"571", align 4
  %53 = load float, ptr addrspace(5) %"569", align 4
  %54 = load float, ptr addrspace(5) %"570", align 4
  %"747" = fadd float %53, %54
  store float %"747", ptr addrspace(5) %"572", align 4
  %55 = load float, ptr addrspace(5) %"571", align 4
  %56 = load float, ptr addrspace(5) %"572", align 4
  %"750" = fadd float %55, %56
  store float %"750", ptr addrspace(5) %"573", align 4
  %57 = load float, ptr addrspace(5) %"557", align 4
  %58 = load float, ptr addrspace(5) %"557", align 4
  %"753" = fmul float %57, %58
  store float %"753", ptr addrspace(5) %"577", align 4
  %59 = load float, ptr addrspace(5) %"558", align 4
  %60 = load float, ptr addrspace(5) %"558", align 4
  %61 = load float, ptr addrspace(5) %"577", align 4
  %"756" = call float @llvm.fma.f32(float %59, float %60, float %61)
  store float %"756", ptr addrspace(5) %"577", align 4
  %62 = load float, ptr addrspace(5) %"559", align 4
  %63 = load float, ptr addrspace(5) %"559", align 4
  %64 = load float, ptr addrspace(5) %"577", align 4
  %"760" = call float @llvm.fma.f32(float %62, float %63, float %64)
  store float %"760", ptr addrspace(5) %"577", align 4
  %65 = load float, ptr addrspace(5) %"560", align 4
  %66 = load float, ptr addrspace(5) %"560", align 4
  %67 = load float, ptr addrspace(5) %"577", align 4
  %"764" = call float @llvm.fma.f32(float %65, float %66, float %67)
  store float %"764", ptr addrspace(5) %"577", align 4
  %68 = load float, ptr addrspace(5) %"561", align 4
  %69 = load float, ptr addrspace(5) %"561", align 4
  %70 = load float, ptr addrspace(5) %"577", align 4
  %"768" = call float @llvm.fma.f32(float %68, float %69, float %70)
  store float %"768", ptr addrspace(5) %"577", align 4
  %71 = load float, ptr addrspace(5) %"562", align 4
  %72 = load float, ptr addrspace(5) %"562", align 4
  %73 = load float, ptr addrspace(5) %"577", align 4
  %"772" = call float @llvm.fma.f32(float %71, float %72, float %73)
  store float %"772", ptr addrspace(5) %"577", align 4
  %74 = load float, ptr addrspace(5) %"563", align 4
  %75 = load float, ptr addrspace(5) %"563", align 4
  %76 = load float, ptr addrspace(5) %"577", align 4
  %"776" = call float @llvm.fma.f32(float %74, float %75, float %76)
  store float %"776", ptr addrspace(5) %"577", align 4
  %77 = load float, ptr addrspace(5) %"564", align 4
  %78 = load float, ptr addrspace(5) %"564", align 4
  %79 = load float, ptr addrspace(5) %"577", align 4
  %"780" = call float @llvm.fma.f32(float %77, float %78, float %79)
  store float %"780", ptr addrspace(5) %"577", align 4
  %80 = load float, ptr addrspace(5) %"573", align 4
  %"936" = bitcast float %80 to i32
  %"935" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"936", i32 16, i32 31, i32 -1)
  %"784" = bitcast i32 %"935" to float
  store float %"784", ptr addrspace(5) %"574", align 4
  %81 = load float, ptr addrspace(5) %"573", align 4
  %82 = load float, ptr addrspace(5) %"574", align 4
  %"786" = fadd float %81, %82
  store float %"786", ptr addrspace(5) %"573", align 4
  %83 = load float, ptr addrspace(5) %"573", align 4
  %"938" = bitcast float %83 to i32
  %"937" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"938", i32 8, i32 31, i32 -1)
  %"789" = bitcast i32 %"937" to float
  store float %"789", ptr addrspace(5) %"574", align 4
  %84 = load float, ptr addrspace(5) %"573", align 4
  %85 = load float, ptr addrspace(5) %"574", align 4
  %"791" = fadd float %84, %85
  store float %"791", ptr addrspace(5) %"573", align 4
  %86 = load float, ptr addrspace(5) %"573", align 4
  %"940" = bitcast float %86 to i32
  %"939" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"940", i32 4, i32 31, i32 -1)
  %"794" = bitcast i32 %"939" to float
  store float %"794", ptr addrspace(5) %"574", align 4
  %87 = load float, ptr addrspace(5) %"573", align 4
  %88 = load float, ptr addrspace(5) %"574", align 4
  %"796" = fadd float %87, %88
  store float %"796", ptr addrspace(5) %"573", align 4
  %89 = load float, ptr addrspace(5) %"573", align 4
  %"942" = bitcast float %89 to i32
  %"941" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"942", i32 2, i32 31, i32 -1)
  %"799" = bitcast i32 %"941" to float
  store float %"799", ptr addrspace(5) %"574", align 4
  %90 = load float, ptr addrspace(5) %"573", align 4
  %91 = load float, ptr addrspace(5) %"574", align 4
  %"801" = fadd float %90, %91
  store float %"801", ptr addrspace(5) %"573", align 4
  %92 = load float, ptr addrspace(5) %"573", align 4
  %"944" = bitcast float %92 to i32
  %"943" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"944", i32 1, i32 31, i32 -1)
  %"804" = bitcast i32 %"943" to float
  store float %"804", ptr addrspace(5) %"574", align 4
  %93 = load float, ptr addrspace(5) %"573", align 4
  %94 = load float, ptr addrspace(5) %"574", align 4
  %"806" = fadd float %93, %94
  store float %"806", ptr addrspace(5) %"573", align 4
  %95 = load i32, ptr addrspace(5) %"440", align 4
  %96 = icmp eq i32 %95, 0
  store i1 %96, ptr addrspace(5) %"677", align 1
  %97 = load i1, ptr addrspace(5) %"677", align 1
  br i1 %97, label %"267", label %"268"

"267":                                            ; preds = %"425"
  %98 = load i32, ptr addrspace(5) %"528", align 4
  %99 = load float, ptr addrspace(5) %"573", align 4
  %"946" = inttoptr i32 %98 to ptr addrspace(3)
  store float %99, ptr addrspace(3) %"946", align 4
  br label %"268"

"268":                                            ; preds = %"267", %"425"
  call void @__zluda_ptx_impl_bar_sync(i32 0)
  %100 = load float, ptr addrspace(3) @partials_sum, align 4
  store float %100, ptr addrspace(5) %"587", align 4
  %101 = load float, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @partials_sum, i64 4), align 4
  store float %101, ptr addrspace(5) %"588", align 4
  %102 = load float, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @partials_sum, i64 8), align 4
  store float %102, ptr addrspace(5) %"589", align 4
  %103 = load float, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @partials_sum, i64 12), align 4
  store float %103, ptr addrspace(5) %"590", align 4
  %104 = load float, ptr addrspace(5) %"587", align 4
  %105 = load float, ptr addrspace(5) %"588", align 4
  %"818" = fadd float %104, %105
  store float %"818", ptr addrspace(5) %"591", align 4
  %106 = load float, ptr addrspace(5) %"589", align 4
  %107 = load float, ptr addrspace(5) %"590", align 4
  %"821" = fadd float %106, %107
  store float %"821", ptr addrspace(5) %"592", align 4
  %108 = load float, ptr addrspace(5) %"591", align 4
  %109 = load float, ptr addrspace(5) %"592", align 4
  %"824" = fadd float %108, %109
  store float %"824", ptr addrspace(5) %"593", align 4
  %110 = load float, ptr addrspace(5) %"577", align 4
  %"952" = bitcast float %110 to i32
  %"951" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"952", i32 16, i32 31, i32 -1)
  %"827" = bitcast i32 %"951" to float
  store float %"827", ptr addrspace(5) %"578", align 4
  %111 = load float, ptr addrspace(5) %"577", align 4
  %112 = load float, ptr addrspace(5) %"578", align 4
  %"829" = fadd float %111, %112
  store float %"829", ptr addrspace(5) %"577", align 4
  %113 = load float, ptr addrspace(5) %"577", align 4
  %"954" = bitcast float %113 to i32
  %"953" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"954", i32 8, i32 31, i32 -1)
  %"832" = bitcast i32 %"953" to float
  store float %"832", ptr addrspace(5) %"578", align 4
  %114 = load float, ptr addrspace(5) %"577", align 4
  %115 = load float, ptr addrspace(5) %"578", align 4
  %"834" = fadd float %114, %115
  store float %"834", ptr addrspace(5) %"577", align 4
  %116 = load float, ptr addrspace(5) %"577", align 4
  %"956" = bitcast float %116 to i32
  %"955" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"956", i32 4, i32 31, i32 -1)
  %"837" = bitcast i32 %"955" to float
  store float %"837", ptr addrspace(5) %"578", align 4
  %117 = load float, ptr addrspace(5) %"577", align 4
  %118 = load float, ptr addrspace(5) %"578", align 4
  %"839" = fadd float %117, %118
  store float %"839", ptr addrspace(5) %"577", align 4
  %119 = load float, ptr addrspace(5) %"577", align 4
  %"958" = bitcast float %119 to i32
  %"957" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"958", i32 2, i32 31, i32 -1)
  %"842" = bitcast i32 %"957" to float
  store float %"842", ptr addrspace(5) %"578", align 4
  %120 = load float, ptr addrspace(5) %"577", align 4
  %121 = load float, ptr addrspace(5) %"578", align 4
  %"844" = fadd float %120, %121
  store float %"844", ptr addrspace(5) %"577", align 4
  %122 = load float, ptr addrspace(5) %"577", align 4
  %"960" = bitcast float %122 to i32
  %"959" = call i32 @__zluda_ptx_impl_shfl_sync_down_b32(i32 %"960", i32 1, i32 31, i32 -1)
  %"847" = bitcast i32 %"959" to float
  store float %"847", ptr addrspace(5) %"578", align 4
  %123 = load float, ptr addrspace(5) %"577", align 4
  %124 = load float, ptr addrspace(5) %"578", align 4
  %"849" = fadd float %123, %124
  store float %"849", ptr addrspace(5) %"577", align 4
  %125 = load i1, ptr addrspace(5) %"677", align 1
  br i1 %125, label %"269", label %"270"

"269":                                            ; preds = %"268"
  %126 = load i32, ptr addrspace(5) %"530", align 4
  %127 = load float, ptr addrspace(5) %"577", align 4
  %"961" = inttoptr i32 %126 to ptr addrspace(3)
  store float %127, ptr addrspace(3) %"961", align 4
  br label %"270"

"270":                                            ; preds = %"269", %"268"
  call void @__zluda_ptx_impl_bar_sync(i32 0)
  %128 = load float, ptr addrspace(3) @partials_sumsq, align 4
  store float %128, ptr addrspace(5) %"597", align 4
  %129 = load float, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @partials_sumsq, i64 4), align 4
  store float %129, ptr addrspace(5) %"598", align 4
  %130 = load float, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @partials_sumsq, i64 8), align 4
  store float %130, ptr addrspace(5) %"599", align 4
  %131 = load float, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @partials_sumsq, i64 12), align 4
  store float %131, ptr addrspace(5) %"600", align 4
  %132 = load float, ptr addrspace(5) %"597", align 4
  %133 = load float, ptr addrspace(5) %"598", align 4
  %"859" = fadd float %132, %133
  store float %"859", ptr addrspace(5) %"601", align 4
  %134 = load float, ptr addrspace(5) %"599", align 4
  %135 = load float, ptr addrspace(5) %"600", align 4
  %"862" = fadd float %134, %135
  store float %"862", ptr addrspace(5) %"602", align 4
  %136 = load float, ptr addrspace(5) %"601", align 4
  %137 = load float, ptr addrspace(5) %"602", align 4
  %"865" = fadd float %136, %137
  store float %"865", ptr addrspace(5) %"603", align 4
  %138 = load float, ptr addrspace(5) %"593", align 4
  %139 = call %struct.f32.f32.f32.i8 @__zluda_ptx_impl_div_f32_part1(float %138, float 1.024000e+03)
  %"391" = extractvalue %struct.f32.f32.f32.i8 %139, 0
  %"392" = extractvalue %struct.f32.f32.f32.i8 %139, 1
  %"393" = extractvalue %struct.f32.f32.f32.i8 %139, 2
  %"394" = extractvalue %struct.f32.f32.f32.i8 %139, 3
  %140 = load float, ptr addrspace(5) %"593", align 4
  %"869" = call float @__zluda_ptx_impl_div_f32_part2(float %140, float 1.024000e+03, float %"391", float %"392", float %"393", i8 %"394")
  store float %"869", ptr addrspace(5) %"607", align 4
  %141 = load float, ptr addrspace(5) %"603", align 4
  %142 = call %struct.f32.f32.f32.i8 @__zluda_ptx_impl_div_f32_part1(float %141, float 1.024000e+03)
  %"395" = extractvalue %struct.f32.f32.f32.i8 %142, 0
  %"396" = extractvalue %struct.f32.f32.f32.i8 %142, 1
  %"397" = extractvalue %struct.f32.f32.f32.i8 %142, 2
  %"398" = extractvalue %struct.f32.f32.f32.i8 %142, 3
  %143 = load float, ptr addrspace(5) %"603", align 4
  %"872" = call float @__zluda_ptx_impl_div_f32_part2(float %143, float 1.024000e+03, float %"395", float %"396", float %"397", i8 %"398")
  store float %"872", ptr addrspace(5) %"608", align 4
  %144 = load float, ptr addrspace(5) %"607", align 4
  %145 = load float, ptr addrspace(5) %"607", align 4
  %"874" = fmul float %144, %145
  store float %"874", ptr addrspace(5) %"609", align 4
  %146 = load float, ptr addrspace(5) %"608", align 4
  %147 = load float, ptr addrspace(5) %"609", align 4
  %"877" = fsub float %146, %147
  store float %"877", ptr addrspace(5) %"610", align 4
  %148 = load float, ptr addrspace(5) %"610", align 4
  %"880" = fadd float %148, 0x3EE4F8B580000000
  store float %"880", ptr addrspace(5) %"611", align 4
  %149 = load float, ptr addrspace(5) %"611", align 4
  %"882" = call float @llvm.nvvm.rsqrt.approx.f(float %149)
  store float %"882", ptr addrspace(5) %"612", align 4
  %150 = load i64, ptr addrspace(5) %"542", align 8
  %"966" = inttoptr i64 %150 to ptr addrspace(1)
  %"382" = getelementptr inbounds i8, ptr addrspace(1) %"966", i64 0
  %151 = load float, ptr addrspace(1) %"382", align 4
  store float %151, ptr addrspace(5) %"617", align 4
  %152 = load i64, ptr addrspace(5) %"543", align 8
  %"967" = inttoptr i64 %152 to ptr addrspace(1)
  %"384" = getelementptr inbounds i8, ptr addrspace(1) %"967", i64 0
  %153 = load float, ptr addrspace(1) %"384", align 4
  store float %153, ptr addrspace(5) %"618", align 4
  %154 = load float, ptr addrspace(5) %"557", align 4
  %155 = load float, ptr addrspace(5) %"607", align 4
  %"888" = fsub float %154, %155
  store float %"888", ptr addrspace(5) %"627", align 4
  %156 = load float, ptr addrspace(5) %"627", align 4
  %157 = load float, ptr addrspace(5) %"612", align 4
  %"891" = fmul float %156, %157
  store float %"891", ptr addrspace(5) %"627", align 4
  %158 = load float, ptr addrspace(5) %"627", align 4
  %159 = load float, ptr addrspace(5) %"617", align 4
  %160 = load float, ptr addrspace(5) %"618", align 4
  %"894" = call float @llvm.fma.f32(float %158, float %159, float %160)
  store float %"894", ptr addrspace(5) %"627", align 4
  %161 = load i64, ptr addrspace(5) %"541", align 8
  %"968" = inttoptr i64 %161 to ptr addrspace(1)
  %"386" = getelementptr inbounds i8, ptr addrspace(1) %"968", i64 0
  %162 = load float, ptr addrspace(5) %"627", align 4
  store float %162, ptr addrspace(1) %"386", align 4
  ret void
}

; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare float @llvm.fma.f32(float, float, float) #4

attributes #0 = { "denormal-fp-math"="dynamic" "denormal-fp-math-f32"="dynamic" "no-trapping-math"="true" "target-cpu"="sm_110" }
attributes #1 = { nocallback nofree nosync nounwind willreturn memory(none) "denormal-fp-math"="dynamic" "denormal-fp-math-f32"="dynamic" "no-trapping-math"="true" "target-cpu"="sm_110" }
attributes #2 = { nocallback nofree nosync nounwind speculatable willreturn memory(none) "denormal-fp-math"="dynamic" "denormal-fp-math-f32"="dynamic" "no-trapping-math"="true" "target-cpu"="sm_110" }
attributes #3 = { "denormal-fp-math"="preserve-sign" "denormal-fp-math-f32"="ieee" "no-trapping-math"="true" "target-cpu"="sm_110" }
attributes #4 = { nocallback nofree nosync nounwind speculatable willreturn memory(none) }
