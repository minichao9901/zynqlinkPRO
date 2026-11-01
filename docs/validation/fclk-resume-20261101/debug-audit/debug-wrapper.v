// (c) Copyright 1995-2026 Xilinx, Inc. All rights reserved.
// 
// This file contains confidential and proprietary information
// of Xilinx, Inc. and is protected under U.S. and
// international copyright and other intellectual property
// laws.
// 
// DISCLAIMER
// This disclaimer is not a license and does not grant any
// rights to the materials distributed herewith. Except as
// otherwise provided in a valid license issued to you by
// Xilinx, and to the maximum extent permitted by applicable
// law: (1) THESE MATERIALS ARE MADE AVAILABLE "AS IS" AND
// WITH ALL FAULTS, AND XILINX HEREBY DISCLAIMS ALL WARRANTIES
// AND CONDITIONS, EXPRESS, IMPLIED, OR STATUTORY, INCLUDING
// BUT NOT LIMITED TO WARRANTIES OF MERCHANTABILITY, NON-
// INFRINGEMENT, OR FITNESS FOR ANY PARTICULAR PURPOSE; and
// (2) Xilinx shall not be liable (whether in contract or tort,
// including negligence, or under any other theory of
// liability) for any loss or damage of any kind or nature
// related to, arising under or in connection with these
// materials, including for any direct, or any indirect,
// special, incidental, or consequential loss or damage
// (including loss of data, profits, goodwill, or any type of
// loss or damage suffered as a result of any action brought
// by a third party) even if such damage or loss was
// reasonably foreseeable or Xilinx had been advised of the
// possibility of the same.
// 
// CRITICAL APPLICATIONS
// Xilinx products are not designed or intended to be fail-
// safe, or for use in any application requiring fail-safe
// performance, such as life-support or safety devices or
// systems, Class III medical devices, nuclear facilities,
// applications related to the deployment of airbags, or any
// other applications that could lead to death, personal
// injury, or severe property or environmental damage
// (individually and collectively, "Critical
// Applications"). Customer assumes the sole risk and
// liability of any use of Xilinx products in Critical
// Applications, subject only to applicable laws and
// regulations governing limitations on product liability.
// 
// THIS COPYRIGHT NOTICE AND DISCLAIMER MUST BE RETAINED AS
// PART OF THIS FILE AT ALL TIMES.
// 
// DO NOT MODIFY THIS FILE.


// IP VLNV: xilinx.com:module_ref:swd_controller:1.0
// IP Revision: 1

(* X_CORE_INFO = "swd_controller,Vivado 2018.3" *)
(* CHECK_LICENSE_TYPE = "system_swd_controller_0_0,swd_controller,{}" *)
(* CORE_GENERATION_INFO = "system_swd_controller_0_0,swd_controller,{x_ipProduct=Vivado 2018.3,x_ipVendor=xilinx.com,x_ipLibrary=module_ref,x_ipName=swd_controller,x_ipVersion=1.0,x_ipCoreRevision=1,x_ipLanguage=VERILOG,x_ipSimLanguage=MIXED,C_S_AXI_DATA_WIDTH=32,C_S_AXI_ADDR_WIDTH=8,ENABLE_DIAGNOSTICS=0,SWDIO_IN_DELAY_NS=0}" *)
(* IP_DEFINITION_SOURCE = "module_ref" *)
(* DowngradeIPIdentifiedWarnings = "yes" *)
module system_swd_controller_0_0 (
  clk,
  rst_n,
  s_axi_awaddr,
  s_axi_awprot,
  s_axi_awvalid,
  s_axi_awready,
  s_axi_wdata,
  s_axi_wstrb,
  s_axi_wvalid,
  s_axi_wready,
  s_axi_bresp,
  s_axi_bvalid,
  s_axi_bready,
  s_axi_araddr,
  s_axi_arprot,
  s_axi_arvalid,
  s_axi_arready,
  s_axi_rdata,
  s_axi_rresp,
  s_axi_rvalid,
  s_axi_rready,
  cmd_bram_clk,
  cmd_bram_rst,
  cmd_bram_en,
  cmd_bram_we,
  cmd_bram_addr,
  cmd_bram_wrdata,
  cmd_bram_rddata,
  rsp_bram_clk,
  rsp_bram_rst,
  rsp_bram_en,
  rsp_bram_we,
  rsp_bram_addr,
  rsp_bram_wrdata,
  rsp_bram_rddata,
  pkt_bram_clk,
  pkt_bram_rst,
  pkt_bram_en,
  pkt_bram_we,
  pkt_bram_addr,
  pkt_bram_wrdata,
  pkt_bram_rddata,
  swclk,
  swdio,
  gpio_aux,
  gpio_out,
  gpio_tri,
  gpio_in
);

(* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME clk, ASSOCIATED_BUSIF s_axi, FREQ_HZ 100000000, PHASE 0.000, CLK_DOMAIN system_processing_system7_0_0_FCLK_CLK0, INSERT_VIP 0" *)
(* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 clk CLK" *)
input wire clk;
(* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME rst_n, POLARITY ACTIVE_LOW, INSERT_VIP 0" *)
(* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 rst_n RST" *)
input wire rst_n;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWADDR" *)
input wire [7 : 0] s_axi_awaddr;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWPROT" *)
input wire [2 : 0] s_axi_awprot;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWVALID" *)
input wire s_axi_awvalid;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWREADY" *)
output wire s_axi_awready;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WDATA" *)
input wire [31 : 0] s_axi_wdata;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WSTRB" *)
input wire [3 : 0] s_axi_wstrb;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WVALID" *)
input wire s_axi_wvalid;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WREADY" *)
output wire s_axi_wready;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BRESP" *)
output wire [1 : 0] s_axi_bresp;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BVALID" *)
output wire s_axi_bvalid;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BREADY" *)
input wire s_axi_bready;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARADDR" *)
input wire [7 : 0] s_axi_araddr;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARPROT" *)
input wire [2 : 0] s_axi_arprot;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARVALID" *)
input wire s_axi_arvalid;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARREADY" *)
output wire s_axi_arready;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RDATA" *)
output wire [31 : 0] s_axi_rdata;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RRESP" *)
output wire [1 : 0] s_axi_rresp;
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RVALID" *)
output wire s_axi_rvalid;
(* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi, DATA_WIDTH 32, PROTOCOL AXI4LITE, FREQ_HZ 100000000, ID_WIDTH 0, ADDR_WIDTH 8, AWUSER_WIDTH 0, ARUSER_WIDTH 0, WUSER_WIDTH 0, RUSER_WIDTH 0, BUSER_WIDTH 0, READ_WRITE_MODE READ_WRITE, HAS_BURST 0, HAS_LOCK 0, HAS_PROT 1, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, HAS_WSTRB 1, HAS_BRESP 1, HAS_RRESP 1, SUPPORTS_NARROW_BURST 0, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1, MAX_BURST_LENGTH 1, PHASE 0.000, CLK_DOMAIN system_processing_system7_0_0_FCLK_CLK0, NUM_READ_THREADS 1\
, NUM_WRITE_THREADS 1, RUSER_BITS_PER_BYTE 0, WUSER_BITS_PER_BYTE 0, INSERT_VIP 0" *)
(* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RREADY" *)
input wire s_axi_rready;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 CMD_BRAM CLK" *)
input wire cmd_bram_clk;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 CMD_BRAM RST" *)
input wire cmd_bram_rst;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 CMD_BRAM EN" *)
input wire cmd_bram_en;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 CMD_BRAM WE" *)
input wire [3 : 0] cmd_bram_we;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 CMD_BRAM ADDR" *)
input wire [31 : 0] cmd_bram_addr;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 CMD_BRAM DIN" *)
input wire [31 : 0] cmd_bram_wrdata;
(* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME CMD_BRAM, MEM_SIZE 8192, MEM_WIDTH 32, MEM_ECC NONE, MASTER_TYPE OTHER, READ_LATENCY 1" *)
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 CMD_BRAM DOUT" *)
output wire [31 : 0] cmd_bram_rddata;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 RSP_BRAM CLK" *)
input wire rsp_bram_clk;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 RSP_BRAM RST" *)
input wire rsp_bram_rst;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 RSP_BRAM EN" *)
input wire rsp_bram_en;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 RSP_BRAM WE" *)
input wire [3 : 0] rsp_bram_we;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 RSP_BRAM ADDR" *)
input wire [31 : 0] rsp_bram_addr;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 RSP_BRAM DIN" *)
input wire [31 : 0] rsp_bram_wrdata;
(* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME RSP_BRAM, MEM_SIZE 8192, MEM_WIDTH 32, MEM_ECC NONE, MASTER_TYPE OTHER, READ_LATENCY 1" *)
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 RSP_BRAM DOUT" *)
output wire [31 : 0] rsp_bram_rddata;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 PKT_BRAM CLK" *)
input wire pkt_bram_clk;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 PKT_BRAM RST" *)
input wire pkt_bram_rst;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 PKT_BRAM EN" *)
input wire pkt_bram_en;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 PKT_BRAM WE" *)
input wire [3 : 0] pkt_bram_we;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 PKT_BRAM ADDR" *)
input wire [31 : 0] pkt_bram_addr;
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 PKT_BRAM DIN" *)
input wire [31 : 0] pkt_bram_wrdata;
(* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME PKT_BRAM, MEM_SIZE 8192, MEM_WIDTH 32, MEM_ECC NONE, MASTER_TYPE OTHER, READ_LATENCY 1" *)
(* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 PKT_BRAM DOUT" *)
output wire [31 : 0] pkt_bram_rddata;
inout wire swclk;
inout wire swdio;
inout wire [3 : 0] gpio_aux;
input wire [3 : 0] gpio_out;
input wire [3 : 0] gpio_tri;
output wire [3 : 0] gpio_in;

  swd_controller #(
    .C_S_AXI_DATA_WIDTH(32),
    .C_S_AXI_ADDR_WIDTH(8),
    .ENABLE_DIAGNOSTICS(1),
    .SWDIO_IN_DELAY_NS(0)
  ) inst (
    .clk(clk),
    .rst_n(rst_n),
    .s_axi_awaddr(s_axi_awaddr),
    .s_axi_awprot(s_axi_awprot),
    .s_axi_awvalid(s_axi_awvalid),
    .s_axi_awready(s_axi_awready),
    .s_axi_wdata(s_axi_wdata),
    .s_axi_wstrb(s_axi_wstrb),
    .s_axi_wvalid(s_axi_wvalid),
    .s_axi_wready(s_axi_wready),
    .s_axi_bresp(s_axi_bresp),
    .s_axi_bvalid(s_axi_bvalid),
    .s_axi_bready(s_axi_bready),
    .s_axi_araddr(s_axi_araddr),
    .s_axi_arprot(s_axi_arprot),
    .s_axi_arvalid(s_axi_arvalid),
    .s_axi_arready(s_axi_arready),
    .s_axi_rdata(s_axi_rdata),
    .s_axi_rresp(s_axi_rresp),
    .s_axi_rvalid(s_axi_rvalid),
    .s_axi_rready(s_axi_rready),
    .cmd_bram_clk(cmd_bram_clk),
    .cmd_bram_rst(cmd_bram_rst),
    .cmd_bram_en(cmd_bram_en),
    .cmd_bram_we(cmd_bram_we),
    .cmd_bram_addr(cmd_bram_addr),
    .cmd_bram_wrdata(cmd_bram_wrdata),
    .cmd_bram_rddata(cmd_bram_rddata),
    .rsp_bram_clk(rsp_bram_clk),
    .rsp_bram_rst(rsp_bram_rst),
    .rsp_bram_en(rsp_bram_en),
    .rsp_bram_we(rsp_bram_we),
    .rsp_bram_addr(rsp_bram_addr),
    .rsp_bram_wrdata(rsp_bram_wrdata),
    .rsp_bram_rddata(rsp_bram_rddata),
    .pkt_bram_clk(pkt_bram_clk),
    .pkt_bram_rst(pkt_bram_rst),
    .pkt_bram_en(pkt_bram_en),
    .pkt_bram_we(pkt_bram_we),
    .pkt_bram_addr(pkt_bram_addr),
    .pkt_bram_wrdata(pkt_bram_wrdata),
    .pkt_bram_rddata(pkt_bram_rddata),
    .swclk(swclk),
    .swdio(swdio),
    .gpio_aux(gpio_aux),
    .gpio_out(gpio_out),
    .gpio_tri(gpio_tri),
    .gpio_in(gpio_in)
  );
endmodule
