//-----------------------------------------------------------------------------
// Module: swd_controller
// Description: AXI-Lite Wrapper for SWD Core
//              Compatible with Xilinx Vivado Block Design
//-----------------------------------------------------------------------------

`timescale 1ns/1ps
module swd_controller #(
    parameter C_S_AXI_DATA_WIDTH = 32,
    parameter C_S_AXI_ADDR_WIDTH = 8,
    parameter integer SWDIO_IN_DELAY_NS = 0
)(
    input  wire                                    clk,
    input  wire                                    rst_n,
    
    // AXI-Lite Slave Interface
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]           s_axi_awaddr,
    input  wire [2:0]                              s_axi_awprot,
    input  wire                                    s_axi_awvalid,
    output wire                                    s_axi_awready,
    input  wire [C_S_AXI_DATA_WIDTH-1:0]           s_axi_wdata,
    input  wire [(C_S_AXI_DATA_WIDTH/8)-1:0]       s_axi_wstrb,
    input  wire                                    s_axi_wvalid,
    output wire                                    s_axi_wready,
    output wire [1:0]                              s_axi_bresp,
    output wire                                    s_axi_bvalid,
    input  wire                                    s_axi_bready,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]           s_axi_araddr,
    input  wire [2:0]                              s_axi_arprot,
    input  wire                                    s_axi_arvalid,
    output wire                                    s_axi_arready,
    output wire [C_S_AXI_DATA_WIDTH-1:0]           s_axi_rdata,
    output wire [1:0]                              s_axi_rresp,
    output wire                                    s_axi_rvalid,
    input  wire                                    s_axi_rready,
    
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 CMD_BRAM CLK" *)
    input wire  cmd_bram_clk,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 CMD_BRAM RST" *)
    input wire  cmd_bram_rst,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 CMD_BRAM EN" *)
    input wire  cmd_bram_en,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 CMD_BRAM WE" *)
    input wire [3:0] cmd_bram_we,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 CMD_BRAM ADDR" *)
    input wire [31:0] cmd_bram_addr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 CMD_BRAM DIN" *)
    input wire [31:0] cmd_bram_wrdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 CMD_BRAM DOUT" *)
    output wire [31:0] cmd_bram_rddata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 RSP_BRAM CLK" *)
    input wire  rsp_bram_clk,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 RSP_BRAM RST" *)
    input wire  rsp_bram_rst,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 RSP_BRAM EN" *)
    input wire  rsp_bram_en,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 RSP_BRAM WE" *)
    input wire [3:0] rsp_bram_we,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 RSP_BRAM ADDR" *)
    input wire [31:0] rsp_bram_addr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 RSP_BRAM DIN" *)
    input wire [31:0] rsp_bram_wrdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 RSP_BRAM DOUT" *)
    output wire [31:0] rsp_bram_rddata,

    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 PKT_BRAM CLK" *)
    input wire pkt_bram_clk,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 PKT_BRAM RST" *)
    input wire pkt_bram_rst,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 PKT_BRAM EN" *)
    input wire pkt_bram_en,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 PKT_BRAM WE" *)
    input wire [3:0] pkt_bram_we,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 PKT_BRAM ADDR" *)
    input wire [31:0] pkt_bram_addr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 PKT_BRAM DIN" *)
    input wire [31:0] pkt_bram_wrdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:bram:1.0 PKT_BRAM DOUT" *)
    output wire [31:0] pkt_bram_rddata,

    // SWD Physical Interface
    output wire                                    swclk,
    inout  wire                                    swdio,
    // Existing B19/A20/E19/E18 connector, with JTAG TDI/TDO muxed onto 0/1.
    inout wire [3:0] gpio_aux,
    input wire [3:0] gpio_out,gpio_tri,
    output wire [3:0] gpio_in
);

    // Declare pad control before the generate block. Vivado 2018.3 otherwise
    // creates undriven generate-local implicit nets for forward references.
    reg [31:0] jtag_config,jtag_ir_config,jtag_dr_config,manual_pins;
    reg [2:0] jtag_operation;
    reg jtag_seq_tms,jtag_sample_early;
    reg jtag_return_late;
    wire jtag_enabled=jtag_config[0] && jtag_config[1];
    wire jtag_tck,jtag_tms,jtag_tdi,jtag_busy,jtag_result_valid,jtag_next_ready;
    wire [2:0] core_ack;
    wire core_parity_err,core_busy,core_result_valid,core_next_ready;
    wire [15:0] core_timestamp;
    wire [31:0] core_rdata;
    // First 32 physical DR scans after an explicit arm, independent of the
    // frontend result history. Capture both intended data and serial echoes.
    wire jtag_debug_valid;
    wire [31:0] jtag_debug_meta,jtag_debug_wdata,jtag_debug_tx,jtag_debug_sense,jtag_debug_rx;
    wire [31:0] jtag_debug_alternate,jtag_debug_samples;
    wire [5:0] jtag_debug_tx_req;
    reg [31:0] diag_meta[0:31],diag_front[0:31],diag_latched[0:31],diag_tx[0:31],
               diag_sense[0:31],diag_rx[0:31],diag_extra[0:31],diag_alternate[0:31],diag_samples[0:31];
    reg [4:0] diag_head,diag_index;
    reg [5:0] diag_count;
    reg diag_armed,diag_frozen;

    //=========================================================================
    // IOBUF for SWDIO (bidirectional)
    //=========================================================================
    wire        swdio_o;
    wire        swdio_i;
    wire        swdio_i_fall;
    wire        swdio_t;
    wire        core_swclk;
    wire        swclk_buf;
    wire        swdio_i_fall_raw;
    wire        swdio_i_rise_raw; // unused Q1 retained for primitive clarity
    reg         cfg_sample_rise;
    reg         cfg_rx_boundary;
    reg         swdio_early;
    wire        swdio_i_iddr;
    
    wire swdio_i_raw;
    IOBUF u_swdio_iobuf (
        .IO(swdio),
        .I (manual_pins[8] ? manual_pins[1] : jtag_enabled ? jtag_tms : swdio_o),
        .O (swdio_i_raw),
        .T (!jtag_config[1] || (!manual_pins[8] && !jtag_enabled && swdio_t))
    );
    `ifndef SYNTHESIS
        assign #(SWDIO_IN_DELAY_NS) swdio_i = swdio_i_raw;
        assign swdio_i_iddr = swdio_i;
    `else
        assign swdio_i = swdio_i_raw;
        assign swdio_i_iddr = swdio_i_raw;
    `endif

    // Keep sampling in the FCLK domain. A second global clock tree on the
    // gated SWCLK adds skew to the input return path and limits high rates.
    assign swclk_buf = core_swclk;
    always @(posedge clk) begin
        // Phase 1 samples after the SWCLK rising launch; phase 0 uses IDDR
        // Q2 at the earlier FCLK falling point.
        if (core_swclk) swdio_early <= swdio_i_raw;
    end

    IDDR #(
        .DDR_CLK_EDGE("OPPOSITE_EDGE"),
        .INIT_Q1(1'b0),
        .INIT_Q2(1'b0),
        .SRTYPE("SYNC")
    ) u_swdio_iddr (
        .Q1(swdio_i_rise_raw),
        .Q2(swdio_i_fall_raw),
        .C (clk),
        .CE(1'b1),
        .D (swdio_i_iddr),
        .R (1'b0),
        .S (1'b0)
    );

    // Q1 samples on the next FCLK rising edge after a SWCLK launch; Q2 is the
    // earlier FCLK falling-edge sample. This gives one selectable phase step.
    assign swdio_i_fall = cfg_sample_rise ? swdio_i_rise_raw : swdio_i_fall_raw;
    assign swclk = manual_pins[8] ? manual_pins[0] : jtag_enabled ? jtag_tck : swclk_buf;
    for(genvar gi=0;gi<4;gi=gi+1) begin:g_aux
        wire pin_o=gi==0 && jtag_enabled ? (manual_pins[8] ? manual_pins[2] : jtag_tdi) : gpio_out[gi];
        wire pin_t=!jtag_config[1] || (gi==1 && jtag_enabled) || (!(gi==0 && jtag_enabled) && gpio_tri[gi]);
        IOBUF u_pin(.IO(gpio_aux[gi]),.I(pin_o),.T(pin_t),.O(gpio_in[gi]));
    end

    //=========================================================================
    // Address Map
    //=========================================================================
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_CTRL          = 7'h00;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_STATUS        = 7'h04;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_CFG           = 7'h08;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_SWJ_COUNT     = 7'h0C;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_SWJ_DATA0     = 7'h10;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_SWJ_DATA1     = 7'h14;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_SWJ_DATA2     = 7'h18;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_SWJ_DATA3     = 7'h1C;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_SWJ_DATA4     = 7'h20;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_SWJ_DATA5     = 7'h24;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_SWJ_DATA6     = 7'h28;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_SWJ_DATA7     = 7'h2C;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_BATCH_CTRL    = 7'h30;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_BATCH_STATUS  = 7'h34;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_BATCH_ADDR    = 7'h38;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_BATCH_DATA    = 7'h3C;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_PACKET_CTRL   = 7'h40;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_PACKET_LEN    = 7'h44;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_PACKET_STATUS = 7'h48;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_FEATURES      = 7'h4C;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_ENGINE_RESET  = 7'h50;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_TRACE_CTRL    = 7'h54;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_TRACE_INDEX   = 7'h58;
    localparam [C_S_AXI_ADDR_WIDTH-1:0] ADDR_TRACE_DATA    = 7'h5C;
    reg [31:0] transfer_trace [0:15];
    reg [3:0] trace_head,trace_index;
    reg [15:0] trace_count;
    reg trace_frozen;
    reg trace_raw_mode,trace_raw_armed,trace_raw_active,trace_previous_t;
    wire trace_clear = s_axi_wvalid && s_axi_wready &&
                       write_addr == ADDR_TRACE_CTRL && s_axi_wdata[0];
    // Out-of-band forensic history; freeze on an invalid ACK/parity failure.
    // Do not log at request publication: preserve the result actually completed.
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            trace_head<=0;trace_count<=0;trace_frozen<=0;
            trace_raw_mode<=0;trace_raw_armed<=0;trace_raw_active<=0;trace_previous_t<=0;
        end else begin
            trace_previous_t<=swdio_t;
            if(trace_clear) begin
                trace_head<=0;trace_count<=0;trace_frozen<=0;
                trace_raw_mode<=s_axi_wdata[1];trace_raw_armed<=s_axi_wdata[1];trace_raw_active<=0;
            end else if(trace_raw_mode)begin
                // Passive SWD receive history: first 16 FCLK samples from
                // SWDIO release. Keep the existing JTAG history independent.
                if(!jtag_enabled && ((trace_raw_armed && swdio_t && !trace_previous_t) || trace_raw_active))begin
                    transfer_trace[trace_head]<={4'ha,trace_head,core_req_sel,3'd0,cfg_rx_boundary,cfg_sample_rise,
                        core_result_valid,core_parity_err,core_ack,swdio_t,swdio_o,core_swclk,
                        swdio_i_raw,swdio_i_rise_raw,swdio_i_fall_raw};
                    trace_head<=trace_head+1'b1;trace_count<=trace_count+1'b1;
                    trace_raw_armed<=0;trace_raw_active<=1;
                    if(trace_head==15)begin trace_raw_active<=0;trace_frozen<=1;end
                end
            end
            else if(core_result_valid && !trace_frozen) begin
                transfer_trace[trace_head]<={trace_count,core_req_sel,4'd0,core_parity_err,core_ack};
                trace_head<=trace_head+1'b1;trace_count<=trace_count+1'b1;
                if(core_parity_err || (core_ack!=1 && core_ack!=2 && core_ack!=4))trace_frozen<=1;
            end
        end
    end
    reg engine_reset;
    reg [31:0] engine_reset_count;
    wire engine_rst_n = rst_n & ~engine_reset;
    wire [2:0] jtag_ack;
    wire [31:0] jtag_rdata,jtag_cached_ir;
    wire jtag_cache_valid;
    wire [255:0] jtag_sequence_data;
    wire jtag_tdo_fall,jtag_tdo_rise;
    wire jtag_fence_req,jtag_fence_done,jtag_fence_error;
    wire swd_busy,swd_result_valid,swd_next_ready,swd_parity_err;
    wire [2:0] swd_ack;
    wire [31:0] swd_rdata;
    wire [15:0] swd_timestamp;
    reg [15:0] jtag_timestamp;
    always @(posedge clk or negedge rst_n)
        if(!rst_n) jtag_timestamp<=0;else jtag_timestamp<=jtag_timestamp+1'b1;
    IDDR #(.DDR_CLK_EDGE("OPPOSITE_EDGE"),.INIT_Q1(0),.INIT_Q2(0),.SRTYPE("SYNC")) u_tdo_iddr(
        .C(clk),.CE(1'b1),.D(gpio_in[1]),.Q1(jtag_tdo_rise),.Q2(jtag_tdo_fall),.R(1'b0),.S(1'b0));
    // Scan statistics reported by jtag_core: PHY wait cycles, bits scanned and
    // completed scans. Software divides them to recover the half-cycle delay
    // the PHY actually used, which the requested clock does not guarantee.
    wire [31:0] jtag_stat_cycles,jtag_stat_bits,jtag_stat_transfers;
    wire jtag_invalidate=s_axi_wvalid && s_axi_wready &&
        ((write_addr==8'h80 && s_axi_wdata!=jtag_config) ||
         (write_addr==8'h84 && s_axi_wdata!=jtag_ir_config) ||
         (write_addr==8'h88 && s_axi_wdata!=jtag_dr_config) || write_addr==8'h94);
    assign core_busy=jtag_enabled ? jtag_busy : swd_busy;
    assign core_ack=jtag_enabled ? jtag_ack : swd_ack;
    assign core_parity_err=jtag_enabled ? 1'b0 : swd_parity_err;
    assign core_rdata=jtag_enabled ? jtag_rdata : swd_rdata;
    assign core_result_valid=jtag_enabled ? jtag_result_valid : swd_result_valid;
    assign core_next_ready=jtag_enabled ? jtag_next_ready : swd_next_ready;
    assign core_timestamp=jtag_enabled ? jtag_timestamp : swd_timestamp;

    // ADDR_CFG (0x08) bit definition:
    //   [3:0]   turnaround_fixed      SWD turnaround cycles (fixed to 1)
    //   [7:4]   cfg_idle_cycles       SWD idle cycles after transfer
    //   [8]     cfg_data_phase        Enable WAIT/FAULT data phase handling
    //   [12:9]  cfg_clock_delay       SWJ sequence half-cycle delay
    //   [16:13] cfg_delay_fast        Transfer half-cycle delay
    //   [17]    cfg_sample_rise       1=FCLK Q1, 0=FCLK Q2
    //   [18]    cfg_rx_boundary       1=short-return RX boundary, 0=legacy
    //   [24:23] cfg_turn_extra       Extra low half-cycle steps before ACK
    //   [27:25] cfg_ack_delay        0=legacy; 1..7=ACK hold/capture schedule
    //   [31:29] Reserved

    //=========================================================================
    // Registers
    //=========================================================================
    reg         ctrl_mode;
    reg         ctrl_timestamp_en;
    reg  [3:0]  cfg_idle_cycles;
    reg         cfg_data_phase;
    reg  [3:0]  cfg_clock_delay;
    reg  [3:0]  cfg_delay_fast;
    reg  [1:0]  cfg_turn_extra;
    reg  [2:0]  cfg_ack_delay;
    reg  [255:0] swj_data;
    reg  [7:0]   swj_count;
    reg  [7:0]   xfer_request;
    reg  [31:0]  xfer_wdata;
    reg  [15:0]  packet_len_reg;
    reg          packet_start_pulse;
    
    //=========================================================================
    // AXI-Lite Internal Signals
    //=========================================================================
    reg         aw_en;
    reg  [C_S_AXI_ADDR_WIDTH-1:0] aw_addr;
    reg  [C_S_AXI_ADDR_WIDTH-1:0] ar_addr;
    reg         bvalid_reg;
    reg         rvalid_reg;
    reg  [C_S_AXI_DATA_WIDTH-1:0] rdata_reg;
    //=========================================================================
    // SWD Core Interface
    //=========================================================================
    wire        packet_core_next_valid;
    wire [7:0]  packet_core_next_request;
    wire [31:0] packet_core_next_wdata;
    wire        batch_active;
    wire [31:0] batch_host_rdata;
    wire         packet_active, packet_busy, packet_done, packet_error;
    wire [15:0]  packet_response_words;
    wire [4:0]   packet_state;
    wire         packet_cmd_en, packet_rsp_en;
    wire [9:0]   packet_cmd_addr, packet_rsp_addr;
    wire [31:0]  packet_cmd_data, packet_rsp_data;
    wire [3:0]   packet_rsp_we;
    wire         packet_core_start, packet_core_mode;
    wire [7:0]   packet_core_req;
    wire [31:0]  packet_core_wdata;
    wire        batch_core_start;
    wire        batch_core_mode;
    wire [255:0] batch_core_swj_data;
    wire [7:0]  batch_core_swj_count;
    wire [7:0]  batch_core_req;
    wire [31:0] batch_core_wdata;
    wire        batch_wr_en;
    wire        batch_rd_en;
    wire [1:0]  batch_host_addr;
    wire [31:0] batch_host_wdata;
    wire [3:0]  batch_host_wstrb;
    wire        core_start_sel;
    wire        core_mode_sel;
    wire [255:0] core_swj_data_sel;
    wire [7:0]  core_swj_count_sel;
    wire [7:0]  core_req_sel;
    wire [31:0] core_wdata_sel;
    wire        core_next_valid_sel;
    wire [7:0]  core_next_req_sel;
    wire [31:0] core_next_wdata_sel;

    //=========================================================================
    // Start Pulse Generation
    //=========================================================================
    reg start_pulse;
    wire stream_active, sampler_active, sampler_start;
    wire [7:0] sampler_req;
    wire [31:0] sampler_wdata;
    wire sampler_next_valid;
    wire [7:0] sampler_next_req;
    wire rtt_active,rtt_start,rtt_next_valid;
    wire [7:0] rtt_req,rtt_next_req;
    wire [31:0] rtt_wdata;
    wire sample_pop,sample_empty;
    wire [31:0] sample_data,sample_tick;
    wire [31:0] sample_validation_count;
    wire stream_start = rtt_active ? rtt_start : sampler_start;
    wire [7:0] stream_req;
    wire [31:0] stream_wdata, stream_rdata;
    wire stream_next_valid;
    wire [7:0] stream_next_req;
    wire [31:0] stream_next_wdata;
    assign stream_active = sampler_active || rtt_active;
    assign stream_req = rtt_active ? rtt_req : sampler_req;
    assign stream_wdata = rtt_active ? rtt_wdata : sampler_wdata;
    assign stream_next_valid = rtt_active ? rtt_next_valid : sampler_next_valid;
    assign stream_next_req = rtt_active ? rtt_next_req : sampler_next_req;
    assign stream_next_wdata = 0;
    wire stream_wr = s_axi_wvalid && s_axi_wready && !write_addr[7] && write_addr[6:5]==2'b11 && &s_axi_wstrb;
    wire stream_rd = s_axi_arvalid && s_axi_arready && !s_axi_araddr[7] && s_axi_araddr[6:5]==2'b11;
    probe_sample_engine u_probe_sampler (
        .clk(clk), .rst_n(engine_rst_n), .wr(stream_wr), .rd(stream_rd),
        .waddr(write_addr[4:2]), .raddr(s_axi_araddr[4:2]),
        .wdata(s_axi_wdata), .rdata(stream_rdata),
        .available(!core_busy && !rtt_active && !batch_active && !packet_active && !start_pulse),
        .stream_pop(sample_pop),.stream_empty(sample_empty),.stream_data(sample_data),.timer_tick(sample_tick),
        .validation_count(sample_validation_count),
        .active(sampler_active), .core_start(sampler_start), .core_req(sampler_req),
        .core_wdata(sampler_wdata), .core_next_valid(sampler_next_valid),
        .core_next_req(sampler_next_req), .core_next_wdata(), .core_busy(core_busy),.core_next_ready(core_next_ready),
        .core_result_valid(core_result_valid), .core_ack(core_ack),
        .core_parity_err(core_parity_err), .core_rdata(core_rdata)
    );
    probe_stream_engine u_probe_stream (
        .clk(clk),.rst_n(engine_rst_n),.host_en(pkt_bram_en),.host_we(pkt_bram_we),
        .host_addr(pkt_bram_addr),.host_wdata(pkt_bram_wrdata),.host_rdata(pkt_bram_rddata),
        .sample_empty(sample_empty),.sample_data(sample_data),.tick(sample_tick),
        .sampler_active(sampler_active),.sample_pop(sample_pop),.rtt_active(rtt_active),
        .core_start(rtt_start),.core_req(rtt_req),.core_wdata(rtt_wdata),
        .core_next_valid(rtt_next_valid),.core_next_req(rtt_next_req),
        .core_available(!sampler_active && !batch_active && !packet_active && !start_pulse),
        .core_busy(core_busy),.core_result_valid(core_result_valid),.core_next_ready(core_next_ready),
        .core_ack(core_ack),.core_parity_err(core_parity_err),.core_rdata(core_rdata),
        .transport_jtag(jtag_enabled),.fence_req(jtag_fence_req),.fence_done(jtag_fence_done),.fence_error(jtag_fence_error),
        .sample_validation_count(sample_validation_count)
    );
    wire        start_req;
    assign start_req = (s_axi_wvalid && s_axi_wready && 
                        ((aw_en && s_axi_awaddr == ADDR_CTRL[C_S_AXI_ADDR_WIDTH-1:0]) || 
                         (!aw_en && aw_addr == ADDR_CTRL[C_S_AXI_ADDR_WIDTH-1:0])) && 
                        s_axi_wdata[0]);
    // Status must cover the accepted-command/start-pulse interval, before
    // backend busy updates on the following edge. PS polling can reach that
    // edge through AXI register slices and otherwise consume stale ACK/data.
    wire scalar_status_busy=core_busy || start_pulse || (start_req && !stream_active);
    wire packet_start_req=s_axi_wvalid && s_axi_wready && write_addr==ADDR_PACKET_CTRL &&
                          s_axi_wdata[0] && !packet_busy && !batch_active && !core_busy && !stream_active;
    wire packet_launch_pending=packet_start_req || packet_start_pulse;
    wire packet_status_busy=packet_busy || packet_launch_pending;

    always @(posedge clk or negedge rst_n) begin
        if(!rst_n)begin diag_head<=0;diag_count<=0;diag_armed<=0;diag_frozen<=0;end
        else if(s_axi_wvalid && s_axi_wready && write_addr==8'hcc)begin
            if(s_axi_wdata[0])begin
                diag_head<=0;diag_count<=0;diag_armed<=s_axi_wdata[1];diag_frozen<=0;
            end else if(s_axi_wdata[2])begin diag_armed<=0;diag_frozen<=1;end
        end else if(jtag_debug_valid && diag_armed)begin
            diag_meta[diag_head]<={jtag_timestamp[12:0],jtag_debug_meta[18:0]};
            diag_front[diag_head]<=core_wdata_sel;
            diag_latched[diag_head]<=jtag_debug_wdata;
            diag_tx[diag_head]<=jtag_debug_tx;
            diag_sense[diag_head]<=jtag_debug_sense;
            diag_rx[diag_head]<=jtag_debug_rx;
            diag_alternate[diag_head]<=jtag_debug_alternate;
            diag_samples[diag_head]<=jtag_debug_samples;
            diag_extra[diag_head]<={8'd0,core_req_sel,packet_state,stream_active,packet_active,batch_active,
                                   core_next_valid_sel,core_next_ready,jtag_debug_tx_req};
            diag_count<=diag_count+1'b1;
            if(diag_head==31)begin diag_armed<=0;diag_frozen<=1;end
            else diag_head<=diag_head+1'b1;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            start_pulse <= 1'b0;
        end
        else begin
            start_pulse <= start_req && !stream_active;
        end
    end

    //=========================================================================
    // AXI-Lite Write Logic
    //=========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            aw_en <= 1'b1;
            aw_addr <= {C_S_AXI_ADDR_WIDTH{1'b0}};
            bvalid_reg <= 1'b0;
            ctrl_mode <= 1'b0;
            ctrl_timestamp_en <= 1'b0;
            cfg_idle_cycles <= 4'd0;
            cfg_data_phase <= 1'b0;
            cfg_clock_delay <= 4'd5;
            cfg_delay_fast <= 4'd0;
            cfg_turn_extra <= 2'd0;
            cfg_ack_delay <= 3'd0;
            cfg_sample_rise <= 1'b1;
            cfg_rx_boundary <= 1'b0;
            packet_len_reg <= 16'd0;
            packet_start_pulse <= 1'b0;
            engine_reset <= 1'b0;
            engine_reset_count <= 0;
            trace_index <= 0;
            diag_index <= 0;
            jtag_config<=2;jtag_ir_config<=4;jtag_dr_config<=0;jtag_operation<=0;
            jtag_seq_tms<=0;jtag_sample_early<=0;jtag_return_late<=0;manual_pins<=0;
            swj_data <= 256'd0;
            swj_count <= 8'd0;
            xfer_request <= 8'd0;
            xfer_wdata <= 32'd0;
        end
        else begin
            packet_start_pulse <= 1'b0;
            engine_reset <= 1'b0;
            if(core_start_sel) manual_pins[8]<=0;
            // BRESP/BVALID handshake
            if (s_axi_bready && bvalid_reg) begin
                bvalid_reg <= 1'b0;
                aw_en <= 1'b1;
            end

            // Address phase - latch address when awvalid && awready
            if (s_axi_awvalid && s_axi_awready) begin
                aw_addr <= s_axi_awaddr;
                aw_en <= 1'b0;
            end

            // Data phase - write to registers
            if (s_axi_wvalid && s_axi_wready) begin
                bvalid_reg <= 1'b1;
                
                // Use write_addr which handles both same-cycle and latched address
                case (write_addr)
                    ADDR_CTRL: begin
                        ctrl_mode <= s_axi_wdata[1];
                        ctrl_timestamp_en <= s_axi_wdata[2];
                        xfer_request <= s_axi_wdata[15:8];  // move here
                    end
                    ADDR_CFG: if (!core_busy && !batch_active && !packet_busy && !stream_active) begin
                        cfg_idle_cycles <= s_axi_wdata[7:4];
                        cfg_data_phase <= s_axi_wdata[8];
                        cfg_clock_delay <= s_axi_wdata[12:9];
                        cfg_delay_fast <= s_axi_wdata[16:13];
                        cfg_sample_rise <= s_axi_wdata[17];
                        cfg_rx_boundary <= s_axi_wdata[18];
                        cfg_turn_extra <= s_axi_wdata[24:23];
                        cfg_ack_delay <= s_axi_wdata[27:25];
                    end
                    ADDR_SWJ_DATA0: begin
                        swj_data[31:0] <= s_axi_wdata;
                        // xfer_request <= s_axi_wdata[7:0];
                    end
                    ADDR_SWJ_DATA1: begin
                        swj_data[63:32] <= s_axi_wdata;
                        xfer_wdata <= s_axi_wdata;
                    end
                    ADDR_SWJ_DATA2: begin
                        swj_data[95:64] <= s_axi_wdata;
                    end
                    ADDR_SWJ_DATA3: swj_data[127:96] <= s_axi_wdata;
                    ADDR_SWJ_DATA4: swj_data[159:128] <= s_axi_wdata;
                    ADDR_SWJ_DATA5: swj_data[191:160] <= s_axi_wdata;
                    ADDR_SWJ_DATA6: swj_data[223:192] <= s_axi_wdata;
                    ADDR_SWJ_DATA7: swj_data[255:224] <= s_axi_wdata;
                    ADDR_SWJ_COUNT: swj_count <= s_axi_wdata[7:0];
                    ADDR_PACKET_LEN: packet_len_reg <= s_axi_wdata[15:0];
                    ADDR_PACKET_CTRL: if (s_axi_wdata[0] && !packet_busy && !batch_active && !core_busy && !stream_active)
                        packet_start_pulse <= 1'b1;
                    ADDR_ENGINE_RESET: if (s_axi_wstrb[0] && s_axi_wdata[0]) begin
                        // Keep AXI, clocks, configuration and BRAM alive. Reset
                        // only the execution state machines, even while busy.
                        engine_reset <= 1'b1;
                        engine_reset_count <= engine_reset_count + 1'b1;
                    end
                    ADDR_TRACE_INDEX: trace_index<=s_axi_wdata[3:0];
                    8'hd0:diag_index<=s_axi_wdata[4:0];
                    8'h80: if(!core_busy && !stream_active && !packet_active && !batch_active) jtag_config<=s_axi_wdata;
                    8'h84: if(!core_busy && !stream_active && !packet_active && !batch_active) jtag_ir_config<=s_axi_wdata;
                    8'h88: if(!core_busy && !stream_active && !packet_active && !batch_active) jtag_dr_config<=s_axi_wdata;
                    8'h8c: if(!core_busy) jtag_operation<=s_axi_wdata[2:0];
                    8'h90: if(!core_busy) jtag_seq_tms<=s_axi_wdata[0];
                    8'h94: if(!core_busy) begin manual_pins<=s_axi_wdata;end
                    8'h98: if(!core_busy) begin jtag_sample_early<=s_axi_wdata[0];jtag_return_late<=s_axi_wdata[4];end
                    default: ;
                endcase
            end
        end
    end

    // Combinational address selection for write
    wire [C_S_AXI_ADDR_WIDTH-1:0] write_addr;
    assign write_addr = (s_axi_awvalid && s_axi_awready) ? s_axi_awaddr : aw_addr;

    //=========================================================================
    // AXI-Lite Read Logic
    //=========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ar_addr <= {C_S_AXI_ADDR_WIDTH{1'b0}};
            rvalid_reg <= 1'b0;
            rdata_reg <= {C_S_AXI_DATA_WIDTH{1'b0}};
        end
        else begin
            if (s_axi_arready && s_axi_arvalid && ~rvalid_reg) begin
                rvalid_reg <= 1'b1;
                ar_addr <= s_axi_araddr;
                case (s_axi_araddr)
                    ADDR_CTRL: begin
                        rdata_reg <= {16'd0, xfer_request, 5'd0, ctrl_timestamp_en, ctrl_mode, scalar_status_busy};
                    end
                    ADDR_FEATURES: rdata_reg <= 32'h4450_000f;
                    ADDR_ENGINE_RESET: rdata_reg <= engine_reset_count;
                    ADDR_TRACE_CTRL: rdata_reg <= {trace_frozen,trace_raw_mode,trace_raw_active,trace_raw_armed,8'd0,trace_count,trace_head};
                    ADDR_TRACE_INDEX: rdata_reg <= {28'd0,trace_index};
                    ADDR_TRACE_DATA: rdata_reg <= transfer_trace[trace_index];
                    ADDR_STATUS: begin
                        // 32-bit STATUS layout: [31:16] timestamp, [7] parity_err,
                        // [3:1] ack, [0] busy. Reserved bits read as 0.
                        rdata_reg <= {core_timestamp, 8'd0, core_parity_err, 3'd0, core_ack, scalar_status_busy};
                    end
                    ADDR_CFG: begin
                        rdata_reg <= {4'd0, cfg_ack_delay, cfg_turn_extra, 4'd0, cfg_rx_boundary, cfg_sample_rise, cfg_delay_fast, cfg_clock_delay, cfg_data_phase, cfg_idle_cycles, 4'd1};
                    end
                    ADDR_SWJ_DATA0: begin
                        rdata_reg <= (ctrl_mode) ? {32'd0} : swj_data[31:0];
                    end
                    ADDR_SWJ_DATA1: begin
                        rdata_reg <= (ctrl_mode) ? xfer_wdata : swj_data[63:32];
                    end
                    ADDR_SWJ_DATA2: begin
                        rdata_reg <= (ctrl_mode) ? core_rdata : swj_data[95:64];
                    end
                    ADDR_SWJ_DATA3: begin
                        rdata_reg <= swj_data[127:96];
                    end
                    ADDR_SWJ_DATA4: begin
                        rdata_reg <= swj_data[159:128];
                    end
                    ADDR_SWJ_DATA5: begin
                        rdata_reg <= swj_data[191:160];
                    end
                    ADDR_SWJ_DATA6: begin
                        rdata_reg <= swj_data[223:192];
                    end
                    ADDR_SWJ_DATA7: begin
                        rdata_reg <= swj_data[255:224];
                    end
                    ADDR_SWJ_COUNT: begin
                        rdata_reg <= {24'd0, swj_count};
                    end
                    ADDR_BATCH_CTRL,
                    ADDR_BATCH_STATUS,
                    ADDR_BATCH_ADDR,
                    ADDR_BATCH_DATA: begin
                        rdata_reg <= batch_host_rdata;
                    end
                    ADDR_PACKET_LEN: rdata_reg <= {16'd0,packet_len_reg};
                    ADDR_PACKET_STATUS: rdata_reg <= {packet_response_words,8'd0,packet_state,packet_error,
                                                    packet_done && !packet_launch_pending,packet_status_busy};
                    8'h80:rdata_reg<=jtag_config;
                    8'h84:rdata_reg<=jtag_ir_config;
                    8'h88:rdata_reg<=jtag_dr_config;
                    8'h8c:rdata_reg<={29'd0,jtag_operation};
                    8'h90:rdata_reg<={31'd0,jtag_seq_tms};
                    8'h94:rdata_reg<={23'd0,manual_pins[8],gpio_in[2],1'b0,gpio_in[3],1'b0,gpio_in[1],gpio_in[0],swdio_i_raw,swclk};
                    8'h98:rdata_reg<={27'd0,jtag_return_late,jtag_fence_error,jtag_cache_valid,jtag_busy,jtag_sample_early};
                    8'h9c:rdata_reg<=jtag_cached_ir;
                    8'ha0:rdata_reg<=jtag_sequence_data[31:0];
                    8'ha4:rdata_reg<=jtag_sequence_data[63:32];
                    8'ha8:rdata_reg<=jtag_sequence_data[95:64];
                    8'hac:rdata_reg<=jtag_sequence_data[127:96];
                    8'hb0:rdata_reg<=jtag_sequence_data[159:128];
                    8'hb4:rdata_reg<=jtag_sequence_data[191:160];
                    8'hb8:rdata_reg<=jtag_sequence_data[223:192];
                    8'hbc:rdata_reg<=jtag_sequence_data[255:224];
                    8'hc0:rdata_reg<=jtag_stat_cycles;
                    8'hc4:rdata_reg<=jtag_stat_bits;
                    8'hc8:rdata_reg<=jtag_stat_transfers;
                    8'hcc:rdata_reg<={16'h4a54,3'd0,diag_frozen,diag_armed,diag_count,diag_head};
                    8'hd0:rdata_reg<={27'd0,diag_index};
                    8'hd4:rdata_reg<=diag_meta[diag_index];
                    8'hd8:rdata_reg<=diag_front[diag_index];
                    8'hdc:rdata_reg<=diag_latched[diag_index];
                    8'he0:rdata_reg<=diag_tx[diag_index];
                    8'he4:rdata_reg<=diag_sense[diag_index];
                    8'he8:rdata_reg<=diag_rx[diag_index];
                    8'hec:rdata_reg<=diag_extra[diag_index];
                    8'hf0:rdata_reg<=diag_alternate[diag_index];
                    8'hf4:rdata_reg<=diag_samples[diag_index];
                    default: begin
                        rdata_reg <= !s_axi_araddr[7] && s_axi_araddr[6:5]==2'b11 ? stream_rdata : 32'd0;
                    end
                endcase
            end
            else if (rvalid_reg && s_axi_rready) begin
                rvalid_reg <= 1'b0;
            end
        end
    end

    //=========================================================================
    // AXI-Lite Output Assignments
    //=========================================================================
    assign s_axi_awready = aw_en && !bvalid_reg;
    assign s_axi_wready = !bvalid_reg && (!aw_en || s_axi_awvalid);
    assign s_axi_bresp = 2'b00;  // OKAY
    assign s_axi_bvalid = bvalid_reg;
    
    assign s_axi_arready = !rvalid_reg;
    assign s_axi_rdata = rdata_reg;
    assign s_axi_rresp = 2'b00;  // OKAY
    assign s_axi_rvalid = rvalid_reg;

    assign batch_wr_en = !stream_active && s_axi_wvalid && s_axi_wready &&
                         ((write_addr == ADDR_BATCH_CTRL) ||
                          (write_addr == ADDR_BATCH_ADDR) ||
                          (write_addr == ADDR_BATCH_DATA));
    assign batch_rd_en = s_axi_arready && s_axi_arvalid && ~rvalid_reg &&
                         ((s_axi_araddr == ADDR_BATCH_CTRL) ||
                          (s_axi_araddr == ADDR_BATCH_STATUS) ||
                          (s_axi_araddr == ADDR_BATCH_ADDR) ||
                          (s_axi_araddr == ADDR_BATCH_DATA));
    assign batch_host_addr  = batch_wr_en ? write_addr[3:2] : s_axi_araddr[3:2];
    assign batch_host_wdata = s_axi_wdata;
    assign batch_host_wstrb = s_axi_wstrb;
    // Include the one-cycle start pulse so the BRAM read issued on the
    // launch edge is not lost while packet_busy is still being registered.
    assign packet_active = packet_busy | packet_start_pulse;

    //=========================================================================
    // Batch Engine
    //=========================================================================
    swd_batch_engine u_swd_batch_engine (
        .clk          (clk),
        .rst_n        (engine_rst_n),
        .host_wr_en   (batch_wr_en),
        .host_rd_en   (batch_rd_en),
        .host_addr    (batch_host_addr),
        .host_wdata   (batch_host_wdata),
        .host_wstrb   (batch_host_wstrb),
        .host_rdata   (batch_host_rdata),
        .cmd_bram_en(cmd_bram_en),
        .cmd_bram_we(cmd_bram_we),
        .cmd_bram_addr(cmd_bram_addr),
        .cmd_bram_wrdata(cmd_bram_wrdata),
        .cmd_bram_rddata(cmd_bram_rddata),
        .rsp_bram_en(rsp_bram_en),
        .rsp_bram_we(rsp_bram_we),
        .rsp_bram_addr(rsp_bram_addr),
        .rsp_bram_wrdata(rsp_bram_wrdata),
        .rsp_bram_rddata(rsp_bram_rddata),
        .active       (batch_active),
        .core_start   (batch_core_start),
        .core_mode    (batch_core_mode),
        .core_swj_data(batch_core_swj_data),
        .core_swj_count(batch_core_swj_count),
        .core_req     (batch_core_req),
        .core_wdata   (batch_core_wdata),
        .core_busy    (core_busy),
        .core_ack     (core_ack),
        .core_parity_err(core_parity_err),
        .core_rdata   (core_rdata),
        .packet_active(packet_active),
        .packet_cmd_en(packet_cmd_en),
        .packet_cmd_addr(packet_cmd_addr),
        .packet_cmd_data(packet_cmd_data),
        .packet_rsp_en(packet_rsp_en),
        .packet_rsp_we(packet_rsp_we),
        .packet_rsp_addr(packet_rsp_addr),
        .packet_rsp_data(packet_rsp_data)
    );

    dap_transfer_block_engine #(.ENABLE_CHAIN(1)) u_dap_packet_engine (
        .clk(clk), .rst_n(engine_rst_n), .start(packet_start_pulse),
        .packet_len(packet_len_reg), .busy(packet_busy), .done(packet_done),
        .error(packet_error), .response_words(packet_response_words),
        .state_dbg(packet_state),
        .cmd_en(packet_cmd_en), .cmd_addr(packet_cmd_addr), .cmd_data(packet_cmd_data),
        .rsp_en(packet_rsp_en), .rsp_we(packet_rsp_we), .rsp_addr(packet_rsp_addr),
        .rsp_data(packet_rsp_data), .core_start(packet_core_start),
        .core_mode(packet_core_mode), .core_req(packet_core_req),
        .core_wdata(packet_core_wdata), .core_busy(core_busy),
        .core_result_valid(core_result_valid), .core_next_ready(core_next_ready),
        .core_next_valid(packet_core_next_valid),
        .core_next_request(packet_core_next_request), .core_next_wdata(packet_core_next_wdata),
        .core_ack(core_ack), .core_parity_err(core_parity_err), .core_rdata(core_rdata)
    );

    assign core_start_sel    = stream_active ? stream_start : packet_active ? packet_core_start : (batch_active ? batch_core_start    : start_pulse);
    assign core_mode_sel     = stream_active ? 1'b1 : packet_active ? packet_core_mode  : (batch_active ? batch_core_mode     : ctrl_mode);
    assign core_swj_data_sel = batch_active ? batch_core_swj_data : swj_data;
    assign core_swj_count_sel= batch_active ? batch_core_swj_count: swj_count;
    assign core_req_sel      = stream_active ? stream_req : packet_active ? packet_core_req   : (batch_active ? batch_core_req      : xfer_request);
    assign core_wdata_sel    = stream_active ? stream_wdata : packet_active ? packet_core_wdata : (batch_active ? batch_core_wdata    : xfer_wdata);
    assign core_next_valid_sel = stream_active ? stream_next_valid :
                                 packet_active ? packet_core_next_valid : 1'b0;
    assign core_next_req_sel = stream_active ? stream_next_req : packet_core_next_request;
    assign core_next_wdata_sel = stream_active ? stream_next_wdata : packet_core_next_wdata;

    //=========================================================================
    // SWD Core Instance
    //=========================================================================
    swd_core u_swd_core (
        .clk           (clk),
        .rst_n         (engine_rst_n),
        .start         (core_start_sel && !jtag_enabled),
        .next_valid    (core_next_valid_sel && !jtag_enabled),
        .next_request  (core_next_req_sel),
        .next_wdata    (core_next_wdata_sel),
        .next_ready    (swd_next_ready),
        .result_valid  (swd_result_valid),
        .mode          (core_mode_sel),
        .timestamp_en  (ctrl_timestamp_en),
        .idle_cycles   (cfg_idle_cycles),
        .data_phase    (cfg_data_phase),
        .clock_delay   (cfg_clock_delay),
        .delay_fast    (cfg_delay_fast),
        .turn_extra   (cfg_turn_extra),
        .ack_delay     (cfg_ack_delay),
        .rx_boundary   (cfg_rx_boundary),
        .swj_data      (core_swj_data_sel),
        .swj_count     (core_swj_count_sel),
        .xfer_request  (core_req_sel),
        .xfer_wdata    (core_wdata_sel),
        .xfer_rdata    (swd_rdata),
        .ack           (swd_ack),
        .parity_err    (swd_parity_err),
        .busy          (swd_busy),
        .timestamp     (swd_timestamp),
        .swclk         (core_swclk),
        .swdio_o       (swdio_o),
        .swdio_i       (swdio_i),
        .swdio_i_fall  (swdio_i_fall),
        .swdio_t      (swdio_t)
    );
    jtag_core u_jtag_core (
        .clk(clk),.rst_n(engine_rst_n),.start(core_start_sel && jtag_enabled),.invalidate(jtag_invalidate),
        .operation(!core_mode_sel ? 3'd6 : stream_active || packet_active || batch_active ? 3'd0 : jtag_operation),
        .request(core_req_sel),.wdata(core_wdata_sel),.seq_count(swj_count==0 ? 9'd256 : {1'b0,swj_count}),
        .seq_data(swj_data),.seq_tms(jtag_seq_tms),.ir_length(jtag_ir_config[7:0]),
        .ir_before(jtag_ir_config[18:8]),.ir_after(jtag_ir_config[29:19]),
        .dr_before(jtag_dr_config[7:0]),.dr_after(jtag_dr_config[15:8]),
        .half_delay(cfg_delay_fast),.idle_cycles(cfg_idle_cycles),
        .late_return(jtag_return_late),
        // Both phases use the IOB IDDR. Q1 is consumed one FCLK after its
        // rising sample, Q2 half an FCLK after its falling sample. The DR
        // window offset independently selects current/previous scan bit.
        .tdo(jtag_sample_early ? jtag_tdo_rise : jtag_tdo_fall),.tdi_sense(gpio_in[0]),
        .tdo_alternate(jtag_sample_early ? jtag_tdo_fall : jtag_tdo_rise),
        .next_valid(core_next_valid_sel && jtag_enabled),.next_request(core_next_req_sel),.next_wdata(core_next_wdata_sel),
        .next_ready(jtag_next_ready),.result_valid(jtag_result_valid),.busy(jtag_busy),.ack(jtag_ack),.rdata(jtag_rdata),
        .tck(jtag_tck),.tms(jtag_tms),.tdi(jtag_tdi),.cached_instruction(jtag_cached_ir),
        .cache_valid(jtag_cache_valid),.sequence_result(jtag_sequence_data),
        .fence_req(jtag_fence_req && jtag_enabled),.fence_done(jtag_fence_done),.fence_error(jtag_fence_error),
        .stat_cycles(jtag_stat_cycles),.stat_bits(jtag_stat_bits),.stat_transfers(jtag_stat_transfers),
        .debug_valid(jtag_debug_valid),.debug_meta(jtag_debug_meta),.debug_wdata(jtag_debug_wdata),
        .debug_tx(jtag_debug_tx),.debug_sense(jtag_debug_sense),.debug_rx(jtag_debug_rx),.debug_tx_req(jtag_debug_tx_req),
        .debug_alternate(jtag_debug_alternate),.debug_samples(jtag_debug_samples)
    );

endmodule



