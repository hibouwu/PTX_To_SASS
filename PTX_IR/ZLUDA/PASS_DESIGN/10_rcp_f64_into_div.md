# Pass 10：`rcp_f64_into_div`

源码：[`../ptx/src/pass/rcp_f64_into_div.rs`](../ptx/src/pass/rcp_f64_into_div.rs)

## 契约与变换

匹配所有 `RcpKind::Compliant(rnd)`，创建同类型常量 `1.0`，再生成保留 rounding 和 FTZ 的浮点 `Div`。approx reciprocal 不变。

输出不变量：compliant reciprocal 不再存在，后续统一处理浮点除法。文件名中的 `f64` 不是当前匹配条件，不能据此把行为限定为 f64。

## 顺序依赖

必须在 Pass 11 和 Pass 14 前运行：新 `Div` 需要参与 helper 拆分与浮点模式分析。

## 现代指令接入

与非 reciprocal 现代指令无关。若新增低精度 reciprocal 类型，应先验证 `ImmediateValue::F64(1.0)` 到目标类型的常量发射以及 Pass 11 的类型分类；不宜自动落入现有 f32/f64 路径。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| compliant f32 | 匹配不检查 `type_ == F64` | 会被改写；旧文档按文件名解释是错误的 |
| 新 f16/bf16 compliant rcp | 仍会产生对应类型 Div | 后续 Pass 11 把非 F64 当 F32，存在错误风险 |
| approximate rcp | pattern 仅 `Compliant` | 正确保留给 intrinsic/direct emitter |

## 测试要求

当前无专属 fixture。补 f32/f64、每种 rounding/FTZ、approx 不变，以及低精度类型必须显式拒绝或完整支持的测试。
