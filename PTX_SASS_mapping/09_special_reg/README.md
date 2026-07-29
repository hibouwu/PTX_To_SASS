# 09 · Special register

状态：`NOT_STARTED`

## 范围

覆盖 thread、CTA、lane、warp、cluster、clock、性能计数和其他目标 PTX 版本合法的
special register 读取。该分类在参考实验中没有独立 testcase，本实验从零建立范围。

## 优先上下文

- special register 种类、位宽、目标 SM 和 PTX ISA 可用性；
- 编译器可证明的 uniformity 与运行时 uniformity；
- GPR/UR producer、重复读取、缓存或复用；
- 作为地址、predicate、branch、shuffle 或函数参数的 consumer；
- 跨基本块/循环活跃和寄存器压力。

## 本族完成门槛

special register 是 PTX 可控 producer；最终落到 SASS special register、GPR 或 UR
是观测结果，必须通过 manipulation check 确认。

