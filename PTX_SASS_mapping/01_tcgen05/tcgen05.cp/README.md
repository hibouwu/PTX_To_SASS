# `tcgen05.cp`

状态：`FRAMEWORK_VALIDATED`（静态实验框架已通过 CUDA 13.0 O0–O3 自检；规则文档待由结果继续归纳）

实验入口：[`thor_ptx90/`](thor_ptx90/)

## 研究边界

研究 PTX ISA 9.0、Thor `sm_110a` 上 `tcgen05.cp` 的全部合法形态，从源 TMEM 区域向目标 TMEM 区域发起异步 copy 时，shape、CTA group、地址来源和完成协议如何决定 SASS。精确 qualifier 集合将在 `factors.yaml` 冻结前依据 PTX 9.0 文法重新枚举。

## 主要因素

| 因素 | 计划水平 | 重点问题 |
|---|---|---|
| shape/方向 | PTX 9.0 全部合法形态 | 核心 copy opcode、modifier 和操作数形状 |
| CTA group | 合法的 group 1/2 形态 | peer CTA 参与是否进入核心编码 |
| 源/目标地址来源 | 参数、alloc 结果、派生链 | GPR/UR 路由和外围地址计算 |
| completion | 无、commit+mbarrier、显式 fence | copy 完成和跨线程可见性如何建立 |
| guard/issuer | uniform、divergent、单 issuer | 异步发射的谓词和控制流 lowering |

## 完成门槛

必须分别归纳核心发射、完成通知、消费者排序和资源复用在静态序列中的 lowering，并保存机器编码和合法性边界；核心 SASS 相同只能建立静态编码碰撞，不能被写成运行时等价结论。
