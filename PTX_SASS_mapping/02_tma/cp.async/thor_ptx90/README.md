# `cp.async` Thor/PTX 9.0 静态映射实验

状态：`FRAMEWORK_VALIDATED`（本机 CUDA 13.0：18 个 syntax + 27 个 expanded case 于 O0–O3 共 180 次编译、反汇编与 `LDGSTS` 归属全部通过；7 个负向探针全部按预期拒绝且诊断子串匹配）

## 目标

用与 `01_tcgen05` 各指令套件相同的静态证据结构研究经典 `cp.async`（global→shared 异步拷贝）：有限合法语法矩阵、受控上下文变化、O0–O3 编译、带机器编码的反汇编、`LDGSTS` 归属、正向/逆向规则候选及预期拒绝边界。`cp.async.commit_group` 与 `cp.async.wait_group` 只作为本目录 case 的 observation 上下文出现，其规则归属由各自目录独立持有。

## 一键运行

```bash
cd PTX_SASS_mapping/02_tma/cp.async/thor_ptx90
./check_all.sh 8
```

## 语法矩阵摘要

- cache-op × cp-size 合法面：`ca` × {4, 8, 16}、`cg` × {16}；
- `shared::cta` 显式拼写变体（与 generic `shared` 同一 semantic form）；
- src-size（zero-fill）轴：(16,8)、(16,4)、(16,12)、(8,4)、(16,0)——已校准 (16,0) 折叠为 ignore-src 操作数形态 `, !PT`；
- ignore-src 谓词轴（不可折叠谓词）；
- `.L2::{64,128,256}B` prefetch 轴与 `.L2::cache_hint` 轴（后者改变操作数形态：dst 迁移到 UR 并出现 `desc[UR]`）；
- expanded 追加：可折叠谓词、guard、同 group 双拷贝、双 group `wait_group 1/0`、`wait_all`、commit→wait 距离、global 地址间接 producer、加宽 kernel 签名（P1-1 模板轴）。

## 判定规则

`check_all.sh` 只有在全部合法 case 于 O0–O3 编译和反汇编成功、全部 case 完成 `LDGSTS` 归属、且全部阴性探针被拒绝并匹配登记的诊断子串时才通过。该 PASS 证明静态实验闭环，不证明实机拷贝、zero-fill 或 group 完成语义。
