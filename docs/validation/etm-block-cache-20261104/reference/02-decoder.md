# 02 · 解码器设计（核心算法）

> 这是整个产品最难、也最值钱的部分。分两层：**包层**（字节 → 事件）和
> **展开层**（事件 + 代码 → 逐条指令）。两层之间只传 `Element`。

---

## 1. 先理解 ETM 到底记录了什么

ETM **不记录**每一条指令。它只记录**控制流的不连续点**：

| 事件 | ETM 里有什么 | 例 |
|---|---|---|
| 顺序执行 | 什么都没有 | `mov r0, #1` |
| 条件分支 | 1 bit：走没走 | `beq label` |
| 直接跳转 | 通常也没有（目标可静态算出） | `b label` |
| 间接跳转 | 完整/压缩目标地址 | `bx r3` / `pop {pc}` |
| 异常进入/返回 | 异常号或入口地址 | SVC / IRQ |
| 时间 | 周期计数增量（可选） | |

所以"解码"= **用代码镜像把中间那些没被记录的指令补出来**。
这就是为什么 Ozone 强制要求"指令缓存"（UM08025 §5.16）——没有代码就补不出来。

```
ETM 流:   [sync pc=0x8000] [atom taken] [addr 0x8123] [timestamp +137]
              │                │             │
              ▼                ▼             ▼
展开结果:  0x8000 0x8002 0x8004 ... 0x8010  → 0x8120 ... 0x8122 → 0x8123 ...
           └──── 从代码镜像走出来的 ────┘     └─ 地址包直接给出 ─┘
```

---

## 2. 包层（L2）

### 2.1 表驱动分派

**不要写 `switch (header)` 瀑布。** SEGGER 的做法是一张 64 项函数指针表，
索引 `header >> 2`，每项 16 字节 `{handler, name}`。热路径 3 条指令：

```cpp
std::size_t EtmV4Decoder::feed(const std::uint8_t* p, std::size_t n) {
    std::size_t used = 0;
    while (used < n) {
        if (!have_header_) {                       // 找一个合法的包头
            const std::uint8_t b = p[used];
            if ((b & 0x03) != 0 || b == 0) { ++used; continue; }  // 非包头，丢弃
            header_ = b; have_header_ = true; ++used; continue;
        }
        const std::size_t idx = header_ >> 2;      // 0..63
        const Handler h = kTable[idx].fn;
        const std::size_t consumed = (this->*h)(p + used, n - used);
        if (consumed == kNeedMore) break;          // ★ 半个包，等下一批数据
        used += consumed;
        have_header_ = false;
    }
    return used;
}
```

`kNeedMore` 是流式解码的关键：**解码器必须能"吃一半就停"**，下次从断点继续。
这个状态（`header_` + 已解析的载荷字节）是解码器对象的一部分，不是局部变量。

### 2.2 变长载荷：7-bit 小端组

```cpp
// 返回消耗的字节数；*out 为值
std::size_t read_varint(const std::uint8_t* p, std::size_t n, std::uint32_t* out) {
    std::uint32_t v = 0;
    int shift = 0;
    for (std::size_t i = 0; i < n; ++i) {
        const std::uint8_t b = p[i];
        v |= std::uint32_t(b & 0x7F) << shift;
        if ((b & 0x80) == 0) { *out = v; return i + 1; }
        shift += 7;
        if (shift > 28) return kMalformed;         // ★ 超过 5 字节 = 流坏了
    }
    return kNeedMore;
}
```

> 从 SEGGER 的实现里确认：超过 5 字节直接判错并打印
> *"Parsed trace packet has payload unexpectedly larger than 5 bytes"*，
> **不会**继续往下猜。这是对的——继续猜只会产生一串错误地址。

### 2.3 地址压缩（最容易写错的地方）

ETM 的地址包不是存绝对地址，而是：

```
new_addr = (payload << 1) XOR last_addr
```

SEGGER 的 `0x10fd80` 就是这么写的（反汇编证据）：

```asm
lea  rsi, [rax+rax]            ; payload << 1
xor  rsi, qword ptr [rbx+0x18] ; ^ last_addr
mov  [rbx+0x18], rsi           ; last_addr = new
mov  [rbx+0x10], rsi           ; current PC = new
```

实现：

```cpp
void on_address(std::uint32_t payload) {
    const std::uint32_t a = (payload << 1) ^ state_.last_addr;
    state_.last_addr = a;
    state_.pc = a & ~1u;
    state_.pc_valid = true;
    emit(Element{ElemType::Address, state_.pc});
}
```

**必须重置 `last_addr` 的时机**（漏一个就全错）：

- 同步包 / Trace Info 之后
- 异常进入之后（handler 地址是新的基准）
- `Cancel` / `Overflow` 之后
- 上下文切换（Context 包）之后

### 2.4 同步、失步、溢出

```
        ┌──────────── 正常解码 ────────────┐
   ─────┤                                   ├─────✗ 未知包 / 校验失败
        └───────────────────────────────────┘
                     ▲
                     │ 只能在 A-SYNC / Trace Info 处重新对齐
                     │
        ┌────────────┴────────────┐
        │ 丢弃直到下一个同步点      │  ← 期间所有地址都不可信，绝不输出
        └─────────────────────────┘
```

规则：
1. 连续 N 个（建议 8）未知包头 → 判定失步 → 进入丢弃模式。
2. 丢弃模式下只找同步序列，**不产生任何指令**。
3. `Overflow` 包 = 探针侧丢数据 → 必须走同一条路径，并且计数上报。

### 2.5 时间戳

- 周期计数是**增量**，累加到 `state_.cycles`。
- 会回绕（32 位）：检测到大幅回退就当作回绕处理，不要当负数。
- 只有在 `VAR_TRACE_TIMESTAMPS_ENABLED` 打开时才有；关掉能省 20–30% 带宽。
- UI 上换算：`t_us = cycles * 1e6 / core_clock_hz`。

---

## 3. 投机执行与回滚（很多人栽在这）

现代 CPU（Cortex-M7/M33/M55）会**推测执行**。ETM 先把推测路径上的指令发出来，
后面再告诉你"这段取消了"（cancel），或者"这段确认了"（commit）。

如果你的解码器一边解一边往最终结果里写，遇到 cancel 就**无法撤销**——UI 上会看到
一段"执行过但其实没执行"的指令，比不显示还糟。

### 3.1 方案：提交水位（watermark）

```
items:  [===========================================]
                       ▲ commit_idx           ▲ write_idx
                       └── 已确认，不可撤销 ────┘
                                             └ 投机区，可整体丢弃
```

```cpp
void append(addr) { items.push_back({addr}); }

void commit() { commit_idx = items.size(); }        // 水位前移

void cancel() {
    items.resize(commit_idx);                        // 截断投机区
    shadow_stack.rollback(commit_depth);             // 调用栈也要回滚
}
```

要点：
- **commit 是批量的**（每个 commit 包覆盖一段），所以水位更新很便宜。
- **调用栈、覆盖率统计也要一起回滚**，否则统计会多算。
  （所以 `TraceStore` 里 `count()` 的累加最好延迟到 commit 之后做。）
- 投机窗口通常只有几十条指令，内存开销可忽略。

框架里 `TraceStore::rollback()` + `mark_commit()` 已经实现并单测（selftest T6）。

---

## 4. 展开层（L3）—— 真正的难点

### 4.1 主循环

```cpp
void FlowEngine::run() {
    while (state_ == State::Running) {
        const Insn in = decode(pc_);          // 见 4.2
        emit(pc_);                            // 发射一条
        switch (in.flow) {
        case Flow::Seq:        pc_ += in.len;                    break;
        case Flow::BranchDir:
            if (!in.conditional) { pc_ = in.target; }            // 无条件：直接走
            else { taken_target_ = in.target;
                   fallthrough_  = pc_ + in.len;
                   state_ = State::WaitBranch; }                 // ★ 停下等 atom
            break;
        case Flow::Call:       push_return(pc_ + in.len); pc_ = in.target; break;
        case Flow::BranchInd:
        case Flow::CallInd:
        case Flow::Return:     state_ = State::WaitIndirect; break;  // ★ 停下等地址包
        case Flow::Halt:       state_ = State::Halted; break;
        }
    }
}
```

**"停下等事件"是整个设计的关键**：解码线程不会因为等 trace 数据而阻塞，
它只是把状态置成 `WaitBranch`，然后回去处理下一个元素。数据来了再继续。

### 4.2 Thumb 指令分类

判定表（Cortex-M，16 位优先）：

| 编码 | 指令 | 分类 |
|---|---|---|
| `11100 xxxxxxxxxxx` | `B` (T2) | BranchDir |
| `1101 cond xxxxxxxx` | `B<c>` (T1) | BranchDir + conditional |
| `1011 0 0 i 1 imm5 Rn` | `CBZ` | BranchDir + conditional |
| `1011 1 0 i 1 imm5 Rn` | `CBNZ` | BranchDir + conditional |
| `010001 11 0 Rm 000` | `BX Rm` | BranchInd |
| `010001 11 1 Rm 000` | `BLX Rm` | CallInd |
| `1011 110 P reglist` (bit8=1) | `POP {..,PC}` | Return |
| `1100 1 Rn reglist` (bit8=1) | `LDM {..,PC}` | Return |
| `11110 ...` | 32 位前缀 | 再判 `BL` / `B.W` / `B<c>.W` |

32 位判定：`(hw1 >> 11) >= 0b11101`。

偏移计算（最容易错的地方，注意 `pc+4` 而不是 `pc`）：

```cpp
// B.W / BL 的 25 位偏移：S:I1:I2:imm10:imm11:0
const std::uint32_t i1 = ~(j1 ^ s) & 1;
const std::uint32_t i2 = ~(j2 ^ s) & 1;
const std::uint32_t imm = (s << 24) | (i1 << 23) | (i2 << 22)
                        | ((hw1 & 0x3FF) << 12) | ((hw2 & 0x7FF) << 1);
target = pc + 4 + sext(imm, 25);
```

（完整实现见 `include/etrace/thumb.hpp`，selftest T2 验证了 `BL` 目标计算。）

### 4.3 IT 块（Cortex-M 的坑）

`IT` 指令让后面最多 4 条指令条件执行。**没执行的那几条不会产生 trace**，
但它们占地址空间。如果不处理 ITSTATE，你会把不该算的指令算进去。

处理方式：
1. 遇到 `IT`（`0xBF00 | cond<<4 | mask`）→ 解析出 8 位 ITSTATE；
2. 后续每条指令消耗 ITSTATE 的一个 4 位字段；
3. 条件不满足的指令**不发射**，但仍要 `pc += len`；
4. 条件结果从哪来？ETMv4 对条件执行有专门的包；如果没有，就只能保守处理
   （发射但标记 `maybe`）。

### 4.4 异常与返回

- 异常进入：ETM 给异常号 → 查向量表（`VTOR + 4*n`）得到 handler 地址。
  向量表要读目标内存，必须缓存。
- 异常返回：`BX LR` 且 LR 是 EXC_RETURN 魔数（`0xFFFFFFF1/F9/FD`）→ 特殊处理，
  回到被打断的地址（需要维护异常栈）。

### 4.5 调用帧（Call Frame）

维护一个影子调用栈：

```
Call  → push (return_addr, target)
Return→ pop
```

这样 UI 上的"调用帧树"是**解码时顺带生成的**，不需要事后重新分析整条 trace。
Ozone 的 call frame 折叠/展开就是靠这个（它还带每条帧的指令数和耗时）。

---

## 5. 性能：怎么做到 100 MB/s

朴素实现大概 50–100 M inst/s，勉强够。但 480 MHz 的 M7 全速跑会到 480 M inst/s，
必须优化。

### 5.1 基本块缓存（必做，收益 5–10×）

直线代码段（两个分支之间）是**常量**。缓存它：

```cpp
struct BasicBlock {
    std::uint32_t start;
    std::vector<std::uint16_t> addrs_delta;  // 指令地址增量
    Flow terminator;                          // 末尾那条控制流
    std::uint32_t target;
};

// 展开一个块 = memcpy 一段 + 更新 pc，不用逐条解码
```

命中率通常在 85–95%（循环！），吞吐能到 500 M inst/s 以上。

### 5.2 其它

| 优化 | 收益 | 复杂度 |
|---|---|---|
| 页级代码缓存（4 KB） | 减少调试口读 | 低 |
| 异步预取 | 隐藏 ~10 µs 读延迟 | 中 |
| 分支目标预计算（反汇编期建 CFG） | 省掉运行时解码 | 中 |
| 批量 emit（一次写 16 条） | 少一次函数调用开销 | 低 |
| 覆盖率用开放寻址哈希而非 `std::unordered_map` | 3–5× | 低 |

---

## 6. 正确性怎么保证（这条最重要）

**没有对拍，不要相信自己写的解码器。**

### 6.1 三层验证

| 层 | 方法 | 频率 |
|---|---|---|
| 单元 | 手工构造 `Element` 序列 + 手工构造代码镜像 → 断言指令序列 | 每次提交 |
| 规范 | ARM ETMv4 规范附录里的示例包流 | 里程碑 |
| 对拍 | 同一份 raw capture，我们的输出 vs **OpenCSD** 的输出，逐元素 diff | 每次发版 |

OpenCSD 是 ARM 官方的开源解码库，作为"金标准"最合适。做法：

```
raw.bin ──┬──▶ 我们的解码器 ──▶ elements_A.json
          └──▶ OpenCSD       ──▶ elements_B.json
                                     │
                                  diff（允许时间戳表述差异，不允许地址差异）
```

### 6.2 真实数据从哪来

1. 自己焊一块 Cortex-M7 板子（或 STM32H7 Nucleo + 飞线到 J-Trace）。
2. 写一个覆盖度高的测试程序：if/else、switch、间接调用、函数指针、异常、IT 块、
   递归、浮点。
3. 用 J-Trace 抓，同时用 `JLINK_STRACE_Read` 拿 SEGGER 的解码结果做"第二参考"。
4. 把 `(raw.bin, expected.json)` 存进仓库做回归。

> SEGGER 的 `JLINK_STRACE_Read` 输出可以直接当 golden reference（它给的是 4 字节地址流，
> 倒序、最新在前）。这等于免费拿到了一个商业级对拍基准。

---

## 7. 坑清单（都是别人踩过的）

| # | 坑 | 后果 | 对策 |
|---|---|---|---|
| 1 | 载荷 > 5 字节还继续解析 | 后面全乱 | 直接判错、重新同步 |
| 2 | `last_addr` 忘了在异常后重置 | 之后的地址全错 | 集中管理 `reset_addr_base()` |
| 3 | payload 字节被误当成包头 | 花式错误 | **按长度字段跳过**，绝不扫描 |
| 4 | 跨 chunk 的半个包丢了状态 | 随机丢指令 | `feed()` 保留 `header_` + 半包缓存 |
| 5 | 丢包后继续解码 | 输出"看起来连续"的假数据 | 必须等到同步点 |
| 6 | 时间戳回绕当负数 | 时间轴负跳变 | 检测回退 → 加 2³² |
| 7 | 忘记 IT 块 | 多算指令、覆盖率偏高 | 维护 ITSTATE |
| 8 | 忘记投机回滚 | 显示未执行的指令 | commit/cancel 水位 |
| 9 | 32 位指令边界算错（`pc+4` vs `pc`） | 分支目标偏 2 | 单测覆盖所有分支类型 |
| 10 | 覆盖率用 `unordered_map` | 解码被统计拖慢 3× | 开放寻址 / 排序数组 |

---

## 8. 落地顺序（建议）

1. **先做 L3 展开层**（不依赖硬件，纯函数，最好测）。
2. 再做 L2 包层，用**手工构造的字节流**测（不需要真板子）。
3. 接 L0/L1，用 J-Link RAWTRACE 拿真数据。
4. 最后做 L4/L5。

理由：L3 是纯逻辑，一天能跑通；L2 没有真数据很难调；反过来会很痛苦。
