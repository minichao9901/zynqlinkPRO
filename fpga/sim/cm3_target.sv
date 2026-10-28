`timescale 1ns/1ps
// Cortex-M3 DesignStart target for simulation.
//
// Wraps the Xilinx-encrypted CortexM3DbgAXI IP (ARM DesignStart FPGA) with two
// behavioural AXI3 memories: the CODE port fetches every instruction as 0, so
// the core takes a fault and stays out of the way, while the SYS port is the
// memory the debugger reaches through the AHB-AP. Both are real AXI3 slaves,
// so AP traffic, RTT and HSS exercise the same bus the silicon uses.
//
// The IP is not in this repository. Point `CM3_RTL` at the directory that
// holds cortexm3_integration.v, dapswjdp.v, ... (see the README next to it).
module cm3_target #(
    parameter integer WORDS      = 4096,
    parameter integer ADDR_BITS  = 12
) (
    input  wire        clk,        // HCLK
    input  wire        rst_n,      // SYSRESETn
    input  wire        dbg_rst_n,  // DBGRESETn
    input  wire        trst_n,     // nTRST
    input  wire        swclktck,   // TCK / SWCLK
    input  wire        swditms,    // TMS / SWDIO (input side)
    input  wire        tdi,
    output wire        tdo,
    output wire        ntdoen,
    output wire        swdo,
    output wire        swdoen,
    output wire        jtag_nsw,
    output wire [31:0] sys_dout,
    output wire [15:0] sys_writes
);
    wire [31:0] s_awaddr;  wire [3:0] s_awlen;  wire [2:0] s_awsize;
    wire [1:0]  s_awburst; wire [1:0] s_awlock; wire [3:0] s_awcache;
    wire [2:0]  s_awprot;  wire       s_awuser; wire       s_awvalid;
    wire        s_awready;
    wire [3:0]  s_wstrb;   wire       s_wlast;  wire       s_wvalid;
    wire        s_wready;
    wire [31:0] s_wdata;
    wire [1:0]  s_bresp;   wire       s_bvalid; wire       s_bready;
    wire [31:0] s_araddr;  wire [3:0] s_arlen;  wire [2:0] s_arsize;
    wire [1:0]  s_arburst; wire [1:0] s_arlock; wire [3:0] s_arcache;
    wire [2:0]  s_arprot;  wire       s_aruser; wire       s_arvalid;
    wire        s_arready;
    wire [31:0] s_rdata;   wire [1:0] s_rresp;  wire       s_rlast;
    wire        s_rvalid;  wire       s_rready;

    wire [31:0] c_awaddr;  wire [3:0] c_awlen;  wire [2:0] c_awsize;
    wire [1:0]  c_awburst; wire [1:0] c_awlock; wire [3:0] c_awcache;
    wire [2:0]  c_awprot;  wire       c_awuser; wire       c_awvalid;
    wire        c_awready;
    wire [3:0]  c_wstrb;   wire       c_wlast;  wire       c_wvalid;
    wire        c_wready;
    wire [31:0] c_wdata;
    wire [1:0]  c_bresp;   wire       c_bvalid; wire       c_bready;
    wire [31:0] c_araddr;  wire [3:0] c_arlen;  wire [2:0] c_arsize;
    wire [1:0]  c_arburst; wire [1:0] c_arlock; wire [3:0] c_arcache;
    wire [2:0]  c_arprot;  wire       c_aruser; wire       c_arvalid;
    wire        c_arready;
    wire [31:0] c_rdata;   wire [1:0] c_rresp;  wire       c_rlast;
    wire        c_rvalid;  wire       c_rready;

    wire sysresetreq, dbgrestarted, lockup, halted, wakeup, wicenack;
    wire jtagtop, trcena, traceclk, swv;
    wire [3:0] tracedata;

    CortexM3DbgAXI u_cm3 (
        .SYSRESETREQ   (sysresetreq),
        .DBGRESTARTED  (dbgrestarted),
        .LOCKUP        (lockup),
        .HALTED        (halted),
        .WAKEUP        (wakeup),
        .WICENACK      (wicenack),
        .JTAGNSW       (jtag_nsw),
        .JTAGTOP       (jtagtop),
        .SWDO          (swdo),
        .SWDOEN        (swdoen),
        .TDO           (tdo),
        .nTDOEN        (ntdoen),
        .TRCENA        (trcena),
        .TRACECLK      (traceclk),
        .TRACEDATA     (tracedata),
        .SWV           (swv),
        .HCLK          (clk),
        .SYSRESETn     (rst_n),
        .IRQ           (16'd0),
        .NMI           (1'b0),
        .CFGITCMEN     (2'b00),
        .DBGRESETn     (dbg_rst_n),
        .DBGRESTART    (1'b0),
        .EDBGRQ        (1'b0),
        .STCLK         (clk),
        .WICENREQ      (1'b0),
        .SWCLKTCK      (swclktck),
        .SWDITMS       (swditms),
        .nTRST         (trst_n),
        .TDI           (tdi),

        .AWADDRS       (s_awaddr),   .AWLENS  (s_awlen),   .AWSIZES (s_awsize),
        .AWBURSTS      (s_awburst),  .AWLOCKS (s_awlock),  .AWCACHES(s_awcache),
        .AWPROTS       (s_awprot),   .AWUSERS (s_awuser),  .AWVALIDS(s_awvalid),
        .AWREADYS      (s_awready),
        .WSTRBS        (s_wstrb),    .WLASTS  (s_wlast),   .WVALIDS (s_wvalid),
        .WREADYS       (s_wready),   .HWDATAS (s_wdata),
        .BRESPS        (s_bresp),    .BVALIDS (s_bvalid),  .BREADYS (s_bready),
        .ARADDRS       (s_araddr),   .ARLENS  (s_arlen),   .ARSIZES (s_arsize),
        .ARBURSTS      (s_arburst),  .ARLOCKS (s_arlock),  .ARCACHES(s_arcache),
        .ARPROTS       (s_arprot),   .ARUSERS (s_aruser),  .ARVALIDS(s_arvalid),
        .ARREADYS      (s_arready),
        .RRESPS        (s_rresp),    .RLASTS  (s_rlast),   .RVALIDS (s_rvalid),
        .RREADYS       (s_rready),   .HRDATAS (s_rdata),

        .AWADDRC       (c_awaddr),   .AWLENC  (c_awlen),   .AWSIZEC (c_awsize),
        .AWBURSTC      (c_awburst),  .AWLOCKC (c_awlock),  .AWCACHEC(c_awcache),
        .AWPROTC       (c_awprot),   .AWUSERC (c_awuser),  .AWVALIDC(c_awvalid),
        .AWREADYC      (c_awready),
        .WSTRBC        (c_wstrb),    .WLASTC  (c_wlast),   .WVALIDC (c_wvalid),
        .WREADYC       (c_wready),   .HWDATAC (c_wdata),
        .BRESPC        (c_bresp),    .BVALIDC (c_bvalid),  .BREADYC (c_bready),
        .ARADDRC       (c_araddr),   .ARLENC  (c_arlen),   .ARSIZEC (c_arsize),
        .ARBURSTC      (c_arburst),  .ARLOCKC (c_arlock),  .ARCACHEC(c_arcache),
        .ARPROTC       (c_arprot),   .ARUSERC (c_aruser),  .ARVALIDC(c_arvalid),
        .ARREADYC      (c_arready),
        .RRESPC        (c_rresp),    .RLASTC  (c_rlast),   .RVALIDC (c_rvalid),
        .RREADYC       (c_rready),   .HRDATAC (c_rdata)
    );

    axi3_sram #(.WORDS(WORDS), .ADDR_BITS(ADDR_BITS)) u_sys (
        .clk(clk), .rst_n(rst_n),
        .awaddr(s_awaddr), .awlen(s_awlen), .awsize(s_awsize), .awburst(s_awburst),
        .awvalid(s_awvalid), .awready(s_awready),
        .wdata(s_wdata), .wstrb(s_wstrb), .wlast(s_wlast), .wvalid(s_wvalid), .wready(s_wready),
        .bresp(s_bresp), .bvalid(s_bvalid), .bready(s_bready),
        .araddr(s_araddr), .arlen(s_arlen), .arsize(s_arsize), .arburst(s_arburst),
        .arvalid(s_arvalid), .arready(s_arready),
        .rdata(s_rdata), .rresp(s_rresp), .rlast(s_rlast), .rvalid(s_rvalid), .rready(s_rready),
        .dbg_dout(sys_dout), .dbg_writes(sys_writes)
    );

    axi3_sram #(.WORDS(WORDS), .ADDR_BITS(ADDR_BITS)) u_code (
        .clk(clk), .rst_n(rst_n),
        .awaddr(c_awaddr), .awlen(c_awlen), .awsize(c_awsize), .awburst(c_awburst),
        .awvalid(c_awvalid), .awready(c_awready),
        .wdata(c_wdata), .wstrb(c_wstrb), .wlast(c_wlast), .wvalid(c_wvalid), .wready(c_wready),
        .bresp(c_bresp), .bvalid(c_bvalid), .bready(c_bready),
        .araddr(c_araddr), .arlen(c_arlen), .arsize(c_arsize), .arburst(c_arburst),
        .arvalid(c_arvalid), .arready(c_arready),
        .rdata(c_rdata), .rresp(c_rresp), .rlast(c_rlast), .rvalid(c_rvalid), .rready(c_rready),
        .dbg_dout(), .dbg_writes()
    );
endmodule
