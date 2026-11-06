import { toast } from './toast.js';

/** Keep the existing clear handlers and log nodes; add the same tools to each bus log. */
export function initEventLogs(){
  // SPI / SPI-QSPI 屏 / I2C 三页已从工作台移除，它们共用的日志头也就不再需要。
  // 保留这个入口，避免 main.js 的初始化顺序为一个空功能分支。
}
