#include "fixture.h"
#include "engine.h"
#include "model.h"

/* 内核私有外设（不需要开任何时钟） */
#define SYST_CSR   (*(volatile uint32_t *)0xE000E010u)
#define SYST_RVR   (*(volatile uint32_t *)0xE000E014u)
#define SYST_CVR   (*(volatile uint32_t *)0xE000E018u)
#define SCB_ICSR   (*(volatile uint32_t *)0xE000ED04u)
#define ICSR_PENDSVSET  (1u << 28)

#define TICK_HZ     10000u
#define PENDSV_EVERY 1000u             /* 每 1000 tick 触发一次 PendSV（10 Hz） */

#define STAGE_COUNT 12u

#ifdef TARGET_H743
volatile float g_exception_fp;
#endif
volatile uint32_t g_ticks;             /* SysTick 计数（ISR 里 ++） */
volatile uint32_t g_pendsv_count;      /* PendSV 计数 */
volatile uint32_t g_loops;             /* 主循环轮数 */
volatile uint32_t g_stage;             /* 当前在第几段（0..STAGE_COUNT-1） */
volatile uint32_t g_last_result;       /* 上一段返回值 */
volatile uint32_t g_checksum;          /* 每轮算一次：用来判断"代码真的在跑" */
volatile uint32_t g_seq_slot[8];       /* engine_linear / engine_linear_os 的写出目标 */
volatile uint32_t g_isr_seen;          /* ISR 里能看到的"主循环轮数快照" */

void SysTick_Handler(void)
{
  g_ticks = g_ticks + 1u;
  g_isr_seen = g_loops;
  if ((g_ticks % PENDSV_EVERY) == 0u){
    SCB_ICSR = ICSR_PENDSVSET;         /* 软触发 PendSV（最低优先级） */
  }
}

void PendSV_Handler(void)
{
  g_pendsv_count = g_pendsv_count + 1u;
#ifdef TARGET_H743
  extern volatile float g_exception_fp;
  g_exception_fp += 0.25f;
#endif
}

/* 空转：让主循环一轮大约几十微秒 —— 单步时不会被"下一轮"追着跑 */
static void spin(uint32_t n)
{
  while (n != 0u){
    __asm__ volatile("nop");
    n--;
  }
}

static uint32_t stage_run(uint32_t s)
{
  switch (s){
    case 0:  return engine_linear(&g_seq_slot[0], g_loops);            /* O0 线性序列（对照靶子） */
    case 1:  return engine_linear_os(&g_seq_slot[0], g_loops ^ 0x5A5A5A5Au);
    case 2:  return engine_deep_chain(g_loops);                        /* 6 层嵌套 */
    case 3:  return engine_rec_fib(10u);                               /* 递归 */
    case 4:  return engine_rec_ack(2u, 3u);                            /* 更深递归 */
    case 5:  return (uint32_t)engine_mutual(g_loops);                  /* 互递归 */
    case 6:  return engine_dispatch(g_loops & 3u, g_loops);            /* 函数指针（BLX Rn） */
    case 7:  return engine_branchy(g_loops);                           /* 分支/循环/switch */
    case 8:  return engine_uses_inline(g_loops);                       /* 内联 */
    case 9:  model_bitfield_touch(g_loops); return g_model.flags.word; /* 位域 */
    case 11: return engine_frame_stage();                          /* deterministic locals / frames */
    default: return model_update(g_loops);                             /* 结构体全量更新 */
  }
}

int main(void)
{
  if (!target_clock_init()) for (;;) {}
  debug_observables_init();
  model_init();

  /* SysTick uses the actual CPU clock. PendSV can be preempted by SysTick. */
  *(volatile uint8_t *)0xe000ed22u = 0xffu;
  SYST_RVR = (g_cpu_hz / TICK_HZ) - 1u;
  SYST_CVR = 0u;
  SYST_CSR = 0x7u;                     /* ENABLE | TICKINT | CLKSOURCE=处理器时钟 */

  for (;;){
    uint32_t s;

    g_loops = g_loops + 1u;
    for (s = 0; s < STAGE_COUNT; s++){
      g_stage = s;                     /* volatile：停下来就能看到"停在第几段" */
      g_last_result = stage_run(s);
    }
    g_checksum = model_checksum() ^ g_seq_slot[7] ^ g_last_result;
    debug_observables_poll();
    spin(4000u);
  }
}
