//-----------------------------------------------------------------------------
// Module: swd_controller
// Description: AXI-Lite Wrapper for SWD Core
//              Compatible with Xilinx Vivado Block Design
//-----------------------------------------------------------------------------

`timescale 1ns/1ps
module swd_controller #(
    parameter C_S_AXI_DATA_WIDTH = 32,
    parameter C_S_AXI_ADDR_WIDTH = 6,
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

    // SWD Physical Interface
    output wire                                    swclk,
    inout  wire                                    swdio
);

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
    reg         swdio_early;
    wire        swdio_i_iddr;
    
    wire swdio_i_raw;
    IOBUF u_swdio_iobuf (
        .IO(swdio),
        .I (swdio_o),
        .O (swdio_i_raw),
        .T (swdio_t)
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
    assign swclk = swclk_buf;

    //=========================================================================
    // Address Map
    //=========================================================================
    localparam ADDR_CTRL          = 6'h00;
    localparam ADDR_STATUS        = 6'h04;
    localparam ADDR_CFG           = 6'h08;
    localparam ADDR_SWJ_COUNT     = 6'h0C;
    localparam ADDR_SWJ_DATA0     = 6'h10;
    localparam ADDR_SWJ_DATA1     = 6'h14;
    localparam ADDR_SWJ_DATA2     = 6'h18;
    localparam ADDR_SWJ_DATA3     = 6'h1C;
    localparam ADDR_SWJ_DATA4     = 6'h20;
    localparam ADDR_SWJ_DATA5     = 6'h24;
    localparam ADDR_SWJ_DATA6     = 6'h28;
    localparam ADDR_SWJ_DATA7     = 6'h2C;
    localparam ADDR_BATCH_CTRL    = 6'h30;
    localparam ADDR_BATCH_STATUS  = 6'h34;
    localparam ADDR_BATCH_ADDR    = 6'h38;
    localparam ADDR_BATCH_DATA    = 6'h3C;
    localparam ADDR_PACKET_CTRL   = 6'h40;
    localparam ADDR_PACKET_LEN    = 6'h44;
    localparam ADDR_PACKET_STATUS = 6'h48;

    // ADDR_CFG (0x08) bit definition:
    //   [3:0]   turnaround_fixed      SWD turnaround cycles (fixed to 1)
    //   [7:4]   cfg_idle_cycles       SWD idle cycles after transfer
    //   [8]     cfg_data_phase        Enable WAIT/FAULT data phase handling
    //   [12:9]  cfg_clock_delay       SWJ sequence half-cycle delay
    //   [16:13] cfg_delay_fast        Transfer half-cycle delay
    //   [17]    cfg_sample_rise       1=held early sample, 0=late FCLK falling
    //   [31:18] Reserved

    //=========================================================================
    // Registers
    //=========================================================================
    reg         ctrl_mode;
    reg         ctrl_timestamp_en;
    reg  [3:0]  cfg_idle_cycles;
    reg         cfg_data_phase;
    reg  [3:0]  cfg_clock_delay;
    reg  [3:0]  cfg_delay_fast;
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
    wire [2:0]  core_ack;
    wire        core_parity_err;
    wire        core_busy;
    wire [15:0] core_timestamp;
    wire [31:0] core_rdata;
    wire        batch_active;
    wire [31:0] batch_host_rdata;
    wire         packet_active, packet_busy, packet_done, packet_error;
    wire [15:0]  packet_response_words;
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

    //=========================================================================
    // Start Pulse Generation
    //=========================================================================
    wire        start_req;
    reg         start_pulse;
    assign start_req = (s_axi_wvalid && s_axi_wready && 
                        ((aw_en && s_axi_awaddr == ADDR_CTRL[C_S_AXI_ADDR_WIDTH-1:0]) || 
                         (!aw_en && aw_addr == ADDR_CTRL[C_S_AXI_ADDR_WIDTH-1:0])) && 
                        s_axi_wdata[0]);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            start_pulse <= 1'b0;
        end
        else begin
            start_pulse <= start_req;
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
            cfg_delay_fast <= 4'd2;
            cfg_sample_rise <= 1'b1;
            packet_len_reg <= 16'd0;
            packet_start_pulse <= 1'b0;
            swj_data <= 256'd0;
            swj_count <= 8'd0;
            xfer_request <= 8'd0;
            xfer_wdata <= 32'd0;
        end
        else begin
            packet_start_pulse <= 1'b0;
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
                    ADDR_CFG: begin
                        cfg_idle_cycles <= s_axi_wdata[7:4];
                        cfg_data_phase <= s_axi_wdata[8];
                        cfg_clock_delay <= s_axi_wdata[12:9];
                        cfg_delay_fast <= s_axi_wdata[16:13];
                        cfg_sample_rise <= s_axi_wdata[17];
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
                    ADDR_PACKET_CTRL: if (s_axi_wdata[0] && !packet_busy && !batch_active && !core_busy)
                        packet_start_pulse <= 1'b1;
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
                        rdata_reg <= {16'd0, xfer_request, 5'd0, ctrl_timestamp_en, ctrl_mode, core_busy};
                    end
                    ADDR_STATUS: begin
                        // 32-bit STATUS layout: [31:16] timestamp, [7] parity_err,
                        // [3:1] ack, [0] busy. Reserved bits read as 0.
                        rdata_reg <= {core_timestamp, 8'd0, core_parity_err, 3'd0, core_ack, core_busy};
                    end
                    ADDR_CFG: begin
                        rdata_reg <= {14'd0, cfg_sample_rise, cfg_delay_fast, cfg_clock_delay, cfg_data_phase, cfg_idle_cycles, 4'd1};
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
                    ADDR_PACKET_STATUS: rdata_reg <= {packet_response_words,11'd0,packet_error,packet_done,packet_busy};
                    default: begin
                        rdata_reg <= 32'd0;
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

    assign batch_wr_en = s_axi_wvalid && s_axi_wready &&
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
    assign packet_active = packet_busy;

    //=========================================================================
    // Batch Engine
    //=========================================================================
    swd_batch_engine u_swd_batch_engine (
        .clk          (clk),
        .rst_n        (rst_n),
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

    dap_transfer_block_engine u_dap_packet_engine (
        .clk(clk), .rst_n(rst_n), .start(packet_start_pulse),
        .packet_len(packet_len_reg), .busy(packet_busy), .done(packet_done),
        .error(packet_error), .response_words(packet_response_words),
        .cmd_en(packet_cmd_en), .cmd_addr(packet_cmd_addr), .cmd_data(packet_cmd_data),
        .rsp_en(packet_rsp_en), .rsp_we(packet_rsp_we), .rsp_addr(packet_rsp_addr),
        .rsp_data(packet_rsp_data), .core_start(packet_core_start),
        .core_mode(packet_core_mode), .core_req(packet_core_req),
        .core_wdata(packet_core_wdata), .core_busy(core_busy),
        .core_ack(core_ack), .core_parity_err(core_parity_err), .core_rdata(core_rdata)
    );

    assign core_start_sel    = packet_active ? packet_core_start : (batch_active ? batch_core_start    : start_pulse);
    assign core_mode_sel     = packet_active ? packet_core_mode  : (batch_active ? batch_core_mode     : ctrl_mode);
    assign core_swj_data_sel = batch_active ? batch_core_swj_data : swj_data;
    assign core_swj_count_sel= batch_active ? batch_core_swj_count: swj_count;
    assign core_req_sel      = packet_active ? packet_core_req   : (batch_active ? batch_core_req      : xfer_request);
    assign core_wdata_sel    = packet_active ? packet_core_wdata : (batch_active ? batch_core_wdata    : xfer_wdata);

    //=========================================================================
    // SWD Core Instance
    //=========================================================================
    swd_core u_swd_core (
        .clk           (clk),
        .rst_n         (rst_n),
        .start         (core_start_sel),
        .mode          (core_mode_sel),
        .timestamp_en  (ctrl_timestamp_en),
        .idle_cycles   (cfg_idle_cycles),
        .data_phase    (cfg_data_phase),
        .clock_delay   (cfg_clock_delay),
        .delay_fast    (cfg_delay_fast),
        .swj_data      (core_swj_data_sel),
        .swj_count     (core_swj_count_sel),
        .xfer_request  (core_req_sel),
        .xfer_wdata    (core_wdata_sel),
        .xfer_rdata    (core_rdata),
        .ack           (core_ack),
        .parity_err    (core_parity_err),
        .busy          (core_busy),
        .timestamp     (core_timestamp),
        .swclk         (core_swclk),
        .swdio_o       (swdio_o),
        .swdio_i       (swdio_i),
        .swdio_i_fall  (swdio_i_fall),
        .swdio_t      (swdio_t)
    );

endmodule
