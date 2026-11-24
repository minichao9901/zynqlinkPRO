/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    stm32f1xx_it.c
  * @brief   Interrupt Service Routines.
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2025 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */

/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "stm32f1xx_it.h"
#include "usbd_core.h"
#include "trace_hooks.h"
/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN TD */

/* USER CODE END TD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
/* USER CODE BEGIN PV */

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/* External variables --------------------------------------------------------*/
/* USER CODE BEGIN EV */

/* USER CODE END EV */

/******************************************************************************/
/*           Cortex-M3 Processor Interruption and Exception Handlers          */
/******************************************************************************/
/**
  * @brief This function handles Non maskable interrupt.
  */
void NMI_Handler(void)
{
  /* USER CODE BEGIN NonMaskableInt_IRQn 0 */

  /* USER CODE END NonMaskableInt_IRQn 0 */
  /* USER CODE BEGIN NonMaskableInt_IRQn 1 */
   while (1)
  {
  }
  /* USER CODE END NonMaskableInt_IRQn 1 */
}

/**
  * @brief This function handles Hard fault interrupt.
  */
void HardFault_Handler(void)
{
  /* USER CODE BEGIN HardFault_IRQn 0 */

  /* USER CODE END HardFault_IRQn 0 */
  while (1)
  {
    /* USER CODE BEGIN W1_HardFault_IRQn 0 */
    /* USER CODE END W1_HardFault_IRQn 0 */
  }
}

/**
  * @brief This function handles Memory management fault.
  */
void MemManage_Handler(void)
{
  /* USER CODE BEGIN MemoryManagement_IRQn 0 */

  /* USER CODE END MemoryManagement_IRQn 0 */
  while (1)
  {
    /* USER CODE BEGIN W1_MemoryManagement_IRQn 0 */
    /* USER CODE END W1_MemoryManagement_IRQn 0 */
  }
}

/**
  * @brief This function handles Prefetch fault, memory access fault.
  */
void BusFault_Handler(void)
{
  /* USER CODE BEGIN BusFault_IRQn 0 */

  /* USER CODE END BusFault_IRQn 0 */
  while (1)
  {
    /* USER CODE BEGIN W1_BusFault_IRQn 0 */
    /* USER CODE END W1_BusFault_IRQn 0 */
  }
}

/**
  * @brief This function handles Undefined instruction or illegal state.
  */
void UsageFault_Handler(void)
{
  /* USER CODE BEGIN UsageFault_IRQn 0 */

  /* USER CODE END UsageFault_IRQn 0 */
  while (1)
  {
    /* USER CODE BEGIN W1_UsageFault_IRQn 0 */
    /* USER CODE END W1_UsageFault_IRQn 0 */
  }
}

/**
  * @brief This function handles System service call via SWI instruction.
  */
// void SVC_Handler(void)
// {
//   /* USER CODE BEGIN SVCall_IRQn 0 */

//   /* USER CODE END SVCall_IRQn 0 */
//   /* USER CODE BEGIN SVCall_IRQn 1 */

//   /* USER CODE END SVCall_IRQn 1 */
// }

/**
  * @brief This function handles Debug monitor.
  */
void DebugMon_Handler(void)
{
  /* USER CODE BEGIN DebugMonitor_IRQn 0 */

  /* USER CODE END DebugMonitor_IRQn 0 */
  /* USER CODE BEGIN DebugMonitor_IRQn 1 */

  /* USER CODE END DebugMonitor_IRQn 1 */
}

/**
  * @brief This function handles Pendable request for system service.
  */
void PendSV_Handler(void)
{
  /* USER CODE BEGIN PendSV_IRQn 0 */

  /* USER CODE END PendSV_IRQn 0 */
  /* USER CODE BEGIN PendSV_IRQn 1 */

  /* USER CODE END PendSV_IRQn 1 */
}

/**
  * @brief This function handles System tick timer.
  */
void SysTick_Handler(void)
{
  /* USER CODE BEGIN SysTick_IRQn 0 */

  /* USER CODE END SysTick_IRQn 0 */
  HAL_IncTick();
  /* USER CODE BEGIN SysTick_IRQn 1 */

  /* USER CODE END SysTick_IRQn 1 */
}

/******************************************************************************/
/* STM32F1xx Peripheral Interrupt Handlers                                    */
/******************************************************************************/

/*
 * ---------------- USB 中断（两条都要给，原因看这里） ----------------
 *
 * CherryUSB 的 port/fsdev/usb_glue_st.c 在 STM32 上定义了这两个**函数名**：
 *     void USB_IRQHandler(void)   { USBD_IRQHandler(0); }   // 用于 F0/G0/L0 等
 *     void USB_LP_IRQHandler(void){ USBD_IRQHandler(0); }   // 用于 F1 等
 *
 * ⚠️ 关键点：在 STM32F1 里 `USB_LP_IRQHandler` 只是头文件里的**宏别名**
 *    （`#define USB_LP_IRQHandler USB_LP_CAN1_RX0_IRQHandler`），
 *    所以 glue 里那个函数编译出来的符号名其实**就是** USB_LP_CAN1_RX0_IRQHandler，
 *    启动文件的向量能直接指过去 —— 这也是为什么 usb_glue_st.c 里没有 LP 的显式定义也够用。
 *
 *    但 **USB_HP_CAN1_TX_IRQHandler 没有任何宏别名**，glue 一个都没提供。
 *    参考工程的 HAL_PCD_MspInit 把 HP 中断也使能了（两条 NVIC 都开），
 *    所以这里必须补上这个符号，否则链接期就是
 *        undefined reference to `USB_HP_CAN1_TX_IRQHandler'
 *    （这正是把 ST 启动文件的弱别名解开之后暴露出来的东西）。
 *
 * 实现上直接转调 USBD_IRQHandler(0)，与 LP 完全一致：
 * F1 的 USB 外设只是把事件拆到两条向量上，状态机是同一个。
 * 顺便记 HP 向量的进入次数与 CTR 次数到 g_trace，方便排查枚举问题。
 */
void USB_HP_CAN1_TX_IRQHandler(void)
{
    g_trace.usb_hp_irq++;
    if (USB->ISTR & USB_ISTR_CTR) g_trace.usb_ctr++;
    USBD_IRQHandler(0);
}

/**
  * @brief This function handles USB low priority or CAN RX0 interrupts.
  */
//void USB_LP_CAN1_RX0_IRQHandler(void)
//{
//  /* USER CODE BEGIN USB_LP_CAN1_RX0_IRQn 0 */

//  /* USER CODE END USB_LP_CAN1_RX0_IRQn 0 */
//  HAL_PCD_IRQHandler(&hpcd_USB_FS);
//  /* USER CODE BEGIN USB_LP_CAN1_RX0_IRQn 1 */

//  /* USER CODE END USB_LP_CAN1_RX0_IRQn 1 */
//}

/* USER CODE BEGIN 1 */

/* USER CODE END 1 */
