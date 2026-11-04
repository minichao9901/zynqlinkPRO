# J-Trace ETMv3 解码算法（反编译分析）

> 对象：`JLink_x64.dll` 8.68，模块区间 `0x10a000–0x116000`（326 个函数，43 KB 代码）
> 方法：`.pdata` 定界 + 字符串交叉引用 + Capstone 手工反编译
> 结论先行：**DLL 里确实有完整的 ETMv3 解码器**，而且它的指令展开模型和我们写的不一样

---

## 1. 模块结构（四类 trace source）

字符串表里有四个"类名"：

| 名字 | RVA | 角色 |
|---|---|---|
| `LTRACE_ETM` | 0x10a373 | 实时 ETM 流分析 |
| `LTRACE_RX` | 0x113580 / 0x1141f0 | 接收（USB/以太网传输层） |
| `LTRACE_FILE` | 0x10e670 | 从文件回放 |
| `LTRACE_PRE` | 0x1109e0 | 预分析源（喂已解好的数据） |

四者之间用**有界环队列**串起来（`0x13f9e0` 里初始化 4 个容量 0x100000 的队列），
每级一个 worker，`MaxTraceWorker` 可配。

---

## 2. 包层：`0x10b5c7`（ETMv3 包头解码）

这是我们找的那段。判定链（按出现顺序）：

```c
uint8_t b = *p++;

// --- P-header（原子包）: 位7=1, 位1=0, 位0=0
if ((b & 0x83) == 0x80) {
    uint32_t E = (b >> 2) & 0xF;          // 已执行的指令数
    uint32_t N = (b >> 6) & 1;            // 末尾是否有 1 个未执行
    uint32_t En = (1u << E) - 1;          // 原子位图（LSB-first）
    AtomHandler(ctx, En, E + N);          // ★ 见 §3
    return;
}

// --- 0x82/0x83 变体：只计数，无载荷
if ((b & 0xF3) == 0x82) { ctx->pkt_count++; return; }

// --- 时间戳: (b & 0xFB) == 0x42
if ((b & 0xFB) == 0x42) {
    p++;                                   // 载荷：连续 bit7=1 的字节，最多 9 个
    while (p < end && (*p & 0x80)) p++;
    return;
}

// --- 分支地址包: b 的 bit0 = 1
if (b & 1) {
    int n = BranchHandler(ctx, p - 1, remain);   // ★ 见 §5
    p += (n - 1);
    return;
}
```

> 注意 P-header 的判定是 `(b & 0x83) == 0x80`，比 OpenCSD 的 `(b & 0x81) == 0x80`
> 多检查了 bit1 —— 说明 ETMv3.4 的 P-header 位1 恒为 0。

---

## 3. 原子处理：`0x10c000`（算法核心）

```c
void AtomHandler(Ctx *ctx, uint32_t En_bits, uint32_t num_atoms)
{
    State *st = ctx->state;                  // [ctx+0x40]

    if (st->count <= 0) return;              // 还没开始
    uint32_t pc      = st->pc_lo;            // [st+0x148]
    uint32_t pc_hi   = st->pc_hi;            // [st+0x140]   (=0xFFF 表示无效)
    if (pc_hi == -1 || !st->valid || !st->page_table) goto fail;

    for (i = 0; i < num_atoms; i++) {
        Entry *e = icache_lookup(ctx, pc);   // ★ 32 字节/项，见 §4

        e->refcount++;
        if (e->inited == 0) {
            ctx->miss_count++;
            icache_fill(ctx, e, pc);          // ★ 调 CPU 解码器，见 §4
        }

        if ((En_bits & 1) == 0) {            // 原子 = N（未执行）
            pc += e->size;                    //   顺序前进
            e->n_count++;
        } else {                              // 原子 = E（执行）
            if ((e->flags & 4) == 0) {        //   不需要 trace 地址
                pc    = e->next_lo;           //   ★ 直接用缓存的"下一条地址"
                pc_hi = e->next_hi;
            }
            // 否则：pc 不动，等分支地址包来设置
        }
        En_bits >>= 1;                        // LSB-first
    }

    st->pc_lo = pc; st->pc_hi = pc_hi;
    st->dirty = 1;
    return;
fail:
    st->pc_hi = 0xFFF;                        // ★ 非法 PC 哨兵（就是那个 0xFFF）
    st->valid = 0;
}
```

**三条规则**，比我们的模型多了一条：

| 原子 | 动作 |
|---|---|
| `N`（未执行） | `PC += 指令长度` |
| `E` 且 `flags & 4 == 0` | `PC = 缓存的下一条地址`（**不是**现算分支目标） |
| `E` 且 `flags & 4 != 0` | `PC` 保持不变，等下一个分支地址包 |

关键差别：**SEGGER 不在解码时计算分支目标**。每个地址第一次遇到时，
由 CPU 插件把"下一条地址"算好存进缓存；之后每次执行只是查表赋值。

---

## 4. 指令缓存：`0x10aaa0`（每地址 32 字节）

### 4.1 索引方式

```c
uint32_t page = pc >> 17;              // 128 KB 地址空间一页
uint32_t idx  = (pc >> 1) & 0xFFFF;    // 页内 64 K 项
Entry *e = page_table[page] + idx * 32;
```

页表在 `ctx->[0x128]`，页最大数在 `ctx->[0x130]`。

### 4.2 表项布局（32 字节）

| 偏移 | 含义 |
|---|---|
| +0x00 | refcount（该地址被执行/经过的次数） |
| +0x04 | n_count（原子=N 的次数） |
| +0x08 | **instr_size** |
| +0x0c | **flags** |
| +0x10 | **next_addr_lo** |
| +0x14 | **next_addr_hi** |
| +0x18 | opcode（16 位，调试用） |

### 4.3 填充：调用外部解码器

```c
void icache_fill(Ctx *ctx, Entry *e, uint32_t pc)
{
    DecodeFn fn = ctx->decoder_table[pc >> 17];   // ★ [ctx+0x128] 里的函数指针
    DecodeOut out;
    out.in_addr = pc;
    out.req_bytes = 4;
    fn(&out);                                     // 由 CPU 插件解码

    e->flags   = 4;                               // 默认"下一条地址不可知，需 trace"
    if (out.next_known)    e->flags = 2;          // 下一条地址可静态算出 → 2
    if (out.is_link)       e->flags |= 8;         // 调用
    if (out.is_exception)  e->flags |= 0x10;      // 异常
    e->size    = out.instr_size;
    e->next_lo = out.next_addr_lo;
    e->next_hi = out.next_addr_hi;
    e->opcode  = *(uint16_t*)out.code_ptr;
}
```

**架构要点**：SEGGER 不硬编码 ARM/Thumb 解码，而是注册一张
`pc >> 17 → 解码函数` 的表。同一份解码器可以服务不同 ISA（ARM/Thumb/RISC-V）。

这和 Ozone 的 `Plugins\Core\CorePluginARM.dll` 是同一套设计。

---

## 5. 分支地址包：`0x10bd40`

入口先调 `0x12fa50`（包长/字段解析），再按位拼地址：

- 第 1 字节：`(b >> 1) & 0x3F` → 6 位
- 后续字节：`(b & 0x7F)` 7 位（交替编码下最后一字节 `& 0x3F`）
- 第 5 字节：`(b & 0x0F)` 4 位（Thumb）+ 异常字段

和 OpenCSD 的 `extractBrAddrPkt` 等价，也和我们的实现一致。

差异点：地址拼好后不是直接写 `st->pc`，而是写进
`st->pc_lo/pc_hi` 并置 `dirty` —— 因为**分支包可能先于原子包到达**，
所以用"置位 + 延迟生效"而不是立即跳转。

---

## 6. 和我们实现的对比

| 维度 | SEGGER | 我们（etraced） |
|---|---|---|
| 原子语义 | 1 atom = 1 指令，LSB-first | 同 ✅ |
| `N` 处理 | `PC += size` | 同 ✅ |
| `E` 处理 | 查缓存 `next_addr` | 现场计算分支目标 ❌ |
| 分支目标 | 缓存 + 插件决定"是否需要 trace 地址" | 按指令类型猜 ❌ |
| 指令缓存 | 32 B/项，按 `pc>>17` 分页 | 无 ❌ |
| CPU 解码器 | 可插拔函数表 | 硬编码 Thumb 子集 |
| 非法 PC | `0xFFF` 哨兵 | `pc = None` |

### 这解释了我们的 22%

我们卡在"哪些分支消费地址包"上，一直在**按指令类型猜**（BX/POP/LDR PC…）。
SEGGER 不猜：这个信息是 **CPU 解码器给出的 `flags`**，`flags & 4` 决定是否等地址包。

对我们最实际的启示：不需要猜，可以**从数据反推**——
对每个唯一 PC，观察它后面是否紧跟一个分支地址包，用约束求解把
`needs_addr` 标出来，再固化进实现。1467 个唯一 PC，几分钟就能收敛。

---

## 7. 可直接抄的三件事

1. **每地址指令缓存 + 预存 next_addr**：把"解码"变成"查表"，
   这是 10 倍性能的来源，也天然实现基本块缓存。
2. **`flags` 位域**：`2=顺序`、`4=需 trace 地址`、`8=link`、`0x10=异常`。
   比我们现在的 `enum Flow` 更适合查表。
3. **可插拔 CPU 解码器**：`pc>>17 → 函数指针`，一份 trace 框架支持多 ISA。

## 8. 还没啃下来的

- `0x12fa50`（分支包字段解析，~1 KB）—— 异常字段的具体语义
- **CPU 解码器插件本身** —— 决定 `flags` 的那一侧（见 §9）
- `0x10c170`（原子包之后的后处理）—— 见 §9.3

---

## 9. 第二轮：数据通路补全

### 9.1 trace source 是四选一的多态对象

`0x10ad50`（TraceSource_Setup）按全局配置选一个 vtable 装进 `state+0x418`：

```c
if (g_trace_mode == 1) {                 // 单源
    state->vtable = &VT_1;  init = 0xf199e0;
} else {
    state->mode = 3 + (g_cpu == 4);      // 3 或 4
    state->vtable = &VT_2;
    if (g_x != 0) { state->vtable = &VT_3; init = 0xf18520; }
    else if (g_cpu == 4) { state->vtable = &VT_4; init = 0xf18570; }
    else init = 0xf18548;
}
init(&state->src_ctx);
state->mem_accessor = 0x12d7e0;          // ★ 装内存访问器
state->vtable->on_ready(ctx, state);     // 可选的第二钩子
```

vtable 地址：`0x55d9e0 / 0x55ce50 / 0x55def0 / 0x55cf50`。

### 9.2 内存访问器 `0x12d7e0`

不是简单 memcpy，是**按 1 MB 区间查表**的读函数：

```c
ReadMemory(addr, len, dst, src_ctx)
{
    for (;;) {
        page = addr & 0xFFF00000;               // 1 MB 对齐
        for (i = 0; i < 0x1000; i++)            // 0x18 字节/项的区域表
            if (region[i].base == page && region[i].ptr) break;
        if (i == 0x1000) return -1;

        n = min(len, 0x100000 - (addr & 0xFFFFF));
        memcpy(dst, region[i].ptr + (addr & 0xFFFFF), n);
        addr += n; dst += n; len -= n;
        if (!len) return total;
    }
}
```

区域表在 `0x18bfc40`，每项 `{u32 base; u32 pad; void *ptr;}`。
这解释了 icache 为什么要"先查表再读码"——目标内存可能分布在 Flash/SRAM/外设多个区间。

### 9.3 元素输出队列 `0x10c170`

每个包头处理前都会调它，把**待提交元素**刷出去：

```c
FlushPending(ctx, limit, unused)
{
    State *st = ctx->[0x28];
    Entry *q  = st->[0x40138];            // 元素数组
    for (i = ctx->[0x400fc]; i < st->[0x40144]; i++) {
        Elem *e = &q[i * 32];             // ★ 32 字节/元素
        if (e->[8] > limit) break;

        uint32_t tag = e->[0x1c];         // 打包字段
        uint32_t idx  = tag & 0x3FF;
        uint32_t kind = tag & 0xC00;      // bit11:10

        if (kind == 0x400) {              // 需要合并?
            ...
            e->[0x18] = ctx->[0x40000 + idx*4];
            count = last + 1;
        } else if (kind == 0xC00) {
            count++;
        }
        e->[0x10] = count;
        Emit(ctx, e);                     // 0x10bab0
        ctx->[0x400fc]++;
    }
}
```

`0x1c` 的位域：`[9:0]` 索引、`[11:10]` 元素子类型。这是"覆盖率/调用帧"聚合的落点。

---

## 10. 当前完整度的诚实评估

```
  ┌──────────────────────────────────────────────┐
  │ 字节流 → 包头识别 0x10b5c7          ✅ 100%   │
  │ P-header → 原子 0x10c000            ✅ 100%   │
  │ 分支包 → 地址                       ✅ ~90%   │
  │ 指令缓存 {size,next,flags}          ✅ 结构    │
  │   └── CPU 解码器插件（flags 来源）   ❌ 0%     │
  │ 元素输出队列 0x10c170               ✅ ~70%   │
  │ 内存访问器 0x12d7e0                 ✅ 100%   │
  │ trace source 多态 0x10ad50          ✅ ~80%   │
  └──────────────────────────────────────────────┘
```

**唯一的关键缺口**：`state+0x128` 那张"每页一个解码函数指针"的表是**运行期填的**，
静态找不到写入点（全库只有 7 处写 `+0x128`，都是栈或别的结构）。

这不是死路：`flags` 的实际取值可以从**抓包数据反推**（每个唯一 PC 后面是否紧跟
一个分支地址包），比继续挖 DLL 更快、更可靠。

