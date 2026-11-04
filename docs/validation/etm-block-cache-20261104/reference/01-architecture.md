# 01 · 总体架构

> 目标：做一个能对标 Ozone / Lauterbach TRACE32 的 **ARM ETM 指令级 trace 分析工具**。
> 本文只讲"怎么搭"，算法细节见 `02-decoder.md`，排期见 `03-roadmap.md`。

---

## 1. 范围与取舍

| 做 | 不做（第一版） |
|---|---|
| Cortex-M (Thumb-2) 指令级 trace | Cortex-A / AArch64（接口预留） |
| ETMv4 + ETMv3 包解析 | 数据 trace / 功耗 trace |
| 指令窗口、时间轴、代码覆盖率、调用帧 | 指令级反向调试 |
| 实时流式 + 离线文件回放 | 多核同步（第二版） |
| 与 ELF/DWARF 关联到源码行 | 自研编译器工具链集成 |

**核心判断**：这个产品的护城河不在 UI，在 **"把稀疏的 ETM 事件还原成逐条指令"** 的那一层。
UI 是体力活，指令展开是技术活。所以架构上必须把这一层做成独立、可单测、可对拍的库。

---

## 2. 三种接入方式（先想清楚数据从哪来）

```
                    ┌────────────────────────────────────────────┐
   J-Trace Pro ────▶│ A. J-Link SDK  (JLINK_RAWTRACE_Read)       │
                    │    最快出原型，但被 SEGGER 绑定              │
   自有探针    ────▶│ B. 自定义 USB3/Ethernet 协议                │
                    │    自由，但 framing 要自己定                 │
   .trace 文件 ───▶│ C. 文件回放（离线分析 / 回归测试）           │
                    └──────────────────┬─────────────────────────┘
                                       ▼
                              ITraceSource（统一接口）
```

三种方式统一到一个接口，**上层完全不感知数据来源**：

```cpp
class ITraceSource {
public:
    virtual ~ITraceSource() = default;
    /// 拉一批原始字节。返回 >0 表示拿到数据，0 表示暂无，<0 表示错误/结束。
    /// 必须是非阻塞或可中断的，否则 UI 会卡。
    virtual int read(std::uint8_t* dst, std::size_t max_bytes) = 0;
    /// 探针侧状态：溢出计数、当前速率、是否还在采
    virtual TraceStatus status() const = 0;
    virtual void start() = 0;
    virtual void stop() = 0;
};
```

推荐路线：
- **第 1 个月**：A + C。用 J-Link SDK 的 RAWTRACE 拿原始字节，用文件回放做回归。
- **第 2 个月起**：B 与 A 并行，A 只作为"参考数据源"保留（对拍用）。

> 注意：`JLINK_STRACE_Read` 给你的是**已解码的地址流**，不是原始字节。
> 想自己做解码，必须用 `JLINK_RAWTRACE_Read`（约 1:1 的原始 trace 字节）。

---

## 3. 分层

```
┌──────────────────────────────────────────────────────────────────────┐
│ L5 View        Qt Model/View · 虚拟列表 · 时间轴 · 覆盖率热图          │
├──────────────────────────────────────────────────────────────────────┤
│ L4 Model       TraceStore：指令流 · trace 块 · 调用帧 · 覆盖率         │
├──────────────────────────────────────────────────────────────────────┤
│ L3 Flow        FlowEngine：稀疏事件 + 代码镜像 → 逐条指令（含投机回滚） │
├──────────────────────────────────────────────────────────────────────┤
│ L2 Packet      EtmDecoder：字节流 → TraceElement（表驱动状态机）        │
├──────────────────────────────────────────────────────────────────────┤
│ L1 Frame       Framing：raw → frame → payload（端口宽度/对齐/溢出）     │
├──────────────────────────────────────────────────────────────────────┤
│ L0 Transport   ITraceSource（J-Link / 自有探针 / 文件）                │
└──────────────────────────────────────────────────────────────────────┘
```

**分层铁律**：L2 不知道 L4 存在，L3 不知道数据是 USB 来的还是文件来的。
这样每一层都能单独喂合成数据做单测。

### 3.1 为什么 L1 和 L2 要分开

- L1 处理的是**物理层遗留问题**：4-bit 端口一次只来半个字节、A-SYNC 要对齐、
  probe 会在任意位置切断。这部分和 CPU 架构无关。
- L2 处理的是**架构语义**：包类型、地址压缩、时间戳。
- 混在一起写，最后一定变成一坨 `if (isCortexM7)`。

### 3.2 为什么 L3 必须独立

指令展开是**纯函数**：`(代码镜像, 事件序列) -> 指令序列`。
独立出来才能：
1. 用"人工构造的事件序列"做单元测试（不需要真硬件）；
2. 和 OpenCSD 对拍时只替换 L0–L2；
3. 将来支持 Cortex-A 时只换 `<arch>/thumb.hpp`。

---

## 4. 线程模型

```
  [IO 线程]                [Decode 线程]            [Expand 线程]         [UI 线程]
  source.read()   ──▶ Q_raw ──▶ L1+L2 解析  ──▶ Q_elem ──▶ L3 展开  ──▶ Q_item ──▶ 增量刷新
      │                          │                          │                      │
      └── 探针溢出计数            └── 失步/丢弃计数            └── 回滚计数            └── 60 fps 合并
```

- 每级一个 `SpscRing`，深度 4096–64K（按吞吐调）。
- **主链路一律 `Policy::Block`**：trace 丢一个包，后面全错，宁可反压也不能丢。
- 只有 UI 预览旁路用 `Policy::Drop`。
- 每级循环带 **时间预算**（默认 5 ms），超了 `yield()`，避免饿死 UI。
- 关停顺序：`request_stop()` 最上游 → **边排空末端边 `wait()`** → 逐级向下。
  （框架里 `Stage` 就是这么实现的，`selftest` 的 T5 覆盖了这个路径。）

### 4.1 容量估算（重要，别拍脑袋）

| 量 | 估算 | 说明 |
|---|---|---|
| Cortex-M7 @ 480 MHz 全速执行 | ~480 M inst/s | 上限场景 |
| ETM 压缩比（典型控制流） | 1:8 ~ 1:20 | 分支密集时代码更低 |
| 原始 trace 带宽 | 25–60 MB/s | 4-bit 端口 @ 100 MHz DDR ≈ 50 MB/s |
| 解码后指令流 | 480 M × 8 B = 3.8 GB/s | **绝不可能全存** |
| 实际方案 | 只存最近 10 M 条 = 80 MB | 环形淘汰最旧 |

结论：**必须边解边丢（丢最旧）+ 聚合统计**，这正是 Ozone 的 `VAR_TRACE_MAX_INST_CNT = 10 M` 的由来。

---

## 5. 关键接口

### 5.1 包层

```cpp
enum class ElemType : std::uint8_t {
    Sync,        // 同步点，携带确定的 PC
    Address,     // 间接分支目标
    Atom,        // 条件分支结果（taken/not-taken）
    Exception,   // 异常入口
    Timestamp,   // 周期计数
    Commit,      // 提交水位
    Cancel,      // 回滚
    Overflow,    // 丢包，必须重新同步
    Context,     // 上下文/ASID/安全态切换
};

struct Element {
    ElemType type;
    std::uint32_t addr;    // Sync/Address/Exception 有效
    std::uint32_t ts;      // 相对增量
    std::uint8_t  flags;
};

class IEtmDecoder {
public:
    virtual ~IEtmDecoder() = default;
    /// 喂入原始 payload 字节；返回消费了多少字节（可能 < n，剩余留在内部）
    virtual std::size_t feed(const std::uint8_t* data, std::size_t n) = 0;
    /// 取出已解析的元素
    virtual std::size_t drain(Element* out, std::size_t max_n) = 0;
    virtual DecoderStats stats() const = 0;   // 失步次数、未知包数、丢弃字节数
};
```

> `feed` 返回"消费了多少"而不是"全吃完"，是为了处理**跨 chunk 的半个包**：
> 剩下几个字节留在解码器内部，等下一批数据来了再拼。这是流式解码的必备语义。

### 5.2 展开层

```cpp
class FlowEngine {
public:
    void sync(std::uint32_t pc);
    void branch_taken(bool taken);
    void indirect(std::uint32_t target);
    void exception(std::uint32_t handler);
    void commit();      // 提交水位前移
    void cancel();      // 回滚到上次 commit
    void halt(HaltReason r);
};
```

（完整实现见 `include/etrace/flow.hpp`，已在 selftest 里跑通 taken / not-taken 两条路径。）

### 5.3 代码镜像

```cpp
class ICodeReader {
public:
    virtual bool fetch4(std::uint32_t addr, std::uint32_t& out) = 0;
};
```

实现要点：
- **三级来源**：ELF 段 → 目标内存（经调试口） → 用户手工指定。
- **页级缓存**（4 KB），命中率通常 > 99%（trace 的时间局部性极强）。
- 目标内存读很慢（~10 µs/次），必须**预取**：解码到某地址时，异步把后 4 KB 拉进来。
- 读不到时**不能猜**：标记 `Unknown`，UI 上显示警告图标（Ozone 也是这么做的）。

---

## 6. 内存预算（10 M 条为例）

| 组件 | 大小 | 备注 |
|---|---|---|
| 指令流 `Item{addr,ts}` | 80 MB | 8 B/条；Ozone 只存 4 B（无时间戳） |
| 代码页缓存 | 8 MB | 2048 × 4 KB |
| 覆盖率哈希表 | 20–40 MB | 按 100 万条不同地址估 |
| 流水线队列 | 4 × 64K × 8 B ≈ 2 MB | |
| 反汇编文本缓存 | 16 MB | 只缓存可视区附近 |
| **合计** | **~150 MB** | 可接受 |

---

## 7. 错误处理哲学

**宁可不显示，也不显示错的。**

| 情况 | 处理 |
|---|---|
| 探针溢出 | 立刻插一个 `Overflow` 元素 → 展开层丢弃当前块 → UI 打红条 |
| 包失步（连续 N 个未知头） | 丢弃直到下一个 A-SYNC，统计 `desync_count` |
| 代码不可读 | 该条指令标记 `Unknown`，不中断解码 |
| 地址不在任何已知段 | 同上，UI 标黄 |
| 解码器内部异常 | 降级为"只显示统计"，不崩 |

所有"丢了多少"必须**可见**（Ozone 的 `Lost (current)/Lost (total)` 面板）。用户最怕的是
"看起来连续、其实是拼接的"。

---

## 8. 与 Ozone 的对照

| 维度 | Ozone | 本方案 |
|---|---|---|
| 解码位置 | 在 JLink DLL 里（黑盒） | 自己的库，可调试、可对拍 |
| 数据源 | 只能用 J-Link/J-Trace | 三种源可插拔 |
| 指令流粒度 | 4 B 地址 | 8 B（地址+时间戳），可切 4 B 模式 |
| 背压 | 有界队列 + 丢包即停流 | Block 反压 + 显式丢失记账 |
| 平台 | Windows/Linux x64 | 先 Windows，接口层不绑平台 |
| 扩展性 | 插件（JS） | C++ 插件 + 脚本绑定（后期） |

---

## 9. 目录结构（当前骨架）

```
etraced/
├─ CMakeLists.txt
├─ include/etrace/
│   ├─ ring.hpp        SpscRing：有界无锁环
│   ├─ pipeline.hpp    Stage：带线程/预算/策略的流水级
│   ├─ thumb.hpp       Thumb-2 长度与控制流分类
│   ├─ flow.hpp        FlowEngine：指令展开 + 投机回滚
│   └─ store.hpp       TraceStore：指令流/块/覆盖率
├─ src/selftest.cpp    6 个自测（已全绿）
└─ docs/
```

**下一步该长出来的东西**（按优先级）：

```
├─ include/etrace/
│   ├─ source.hpp      ITraceSource + 三种实现
│   ├─ decode.hpp      IEtmDecoder + etmv4/etmv3 实现
│   └─ elf.hpp         ELF/DWARF 符号与行号
├─ src/
│   ├─ etmv4.cpp       包解析（核心工作量）
│   ├─ framing.cpp     4/2/1-bit 端口重组
│   ├─ elf.cpp
│   └─ cli.cpp         命令行：回放 + 统计 + 导出
├─ tests/
│   ├─ etmv4_vectors/  规范附录里的样例流
│   └─ golden/         真实抓包 + 期望输出
└─ ui/                 Qt 6 Model/View
```
