`timescale 1ns/1ps
// Minimal AXI3 slave memory for simulation.
// Single outstanding transaction, INCR bursts, 32-bit data. Reads are
// asynchronous from the array so the core sees data in the same cycle.
module axi3_sram #(
    parameter integer WORDS = 4096,
    parameter integer ADDR_BITS = 12,
    parameter         NAME = "SYS"
) (
    input  wire        clk,
    input  wire        rst_n,
    // write address
    input  wire [31:0] awaddr,
    input  wire [3:0]  awlen,
    input  wire [2:0]  awsize,
    input  wire [1:0]  awburst,
    input  wire        awvalid,
    output reg         awready,
    // write data
    input  wire [31:0] wdata,
    input  wire [3:0]  wstrb,
    input  wire        wlast,
    input  wire        wvalid,
    output reg         wready,
    // write response
    output reg  [1:0]  bresp,
    output reg         bvalid,
    input  wire        bready,
    // read address
    input  wire [31:0] araddr,
    input  wire [3:0]  arlen,
    input  wire [2:0]  arsize,
    input  wire [1:0]  arburst,
    input  wire        arvalid,
    output reg         arready,
    // read data
    output wire [31:0] rdata,
    output reg  [1:0]  rresp,
    output reg         rlast,
    output reg         rvalid,
    input  wire        rready,

    output reg  [31:0] dbg_dout,   // last write/read word, for testbenches
    output reg  [15:0] dbg_writes
);
    wire dbg_trace = $test$plusargs("axitrace");
    reg [31:0] mem [0:WORDS-1];
    integer i;
    initial begin
        for (i = 0; i < WORDS; i = i + 1) mem[i] = 32'd0;
        dbg_dout = 32'd0;
        dbg_writes = 16'd0;
    end

    reg [31:0] aw_addr_r;
    reg [ADDR_BITS-1:0] wr_ptr;
    reg [ADDR_BITS-1:0] rd_ptr;
    reg [3:0]           rd_left;     // beats still to return after the current one
    reg                 wr_open;

    wire [ADDR_BITS-1:0] aw_word = awaddr[ADDR_BITS+1:2];
    wire [ADDR_BITS-1:0] ar_word = araddr[ADDR_BITS+1:2];

    assign rdata = mem[rd_ptr];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            awready   <= 1'b1;
            wready    <= 1'b0;
            bvalid    <= 1'b0;
            bresp     <= 2'b00;
            arready   <= 1'b1;
            rvalid    <= 1'b0;
            rlast     <= 1'b0;
            rresp     <= 2'b00;
            wr_ptr    <= {ADDR_BITS{1'b0}};
            rd_ptr    <= {ADDR_BITS{1'b0}};
            rd_left   <= 4'd0;
            wr_open   <= 1'b0;
        end else begin
            // ---- write path ----
            if (awready && awvalid) begin
                awready <= 1'b0;
                wready  <= 1'b1;
                aw_addr_r <= awaddr;
                wr_ptr  <= aw_word;
                wr_open <= 1'b1;
            end
            if (wready && wvalid) begin
                if (wstrb[0]) mem[wr_ptr][7:0]   <= wdata[7:0];
                if (wstrb[1]) mem[wr_ptr][15:8]  <= wdata[15:8];
                if (wstrb[2]) mem[wr_ptr][23:16] <= wdata[23:16];
                if (wstrb[3]) mem[wr_ptr][31:24] <= wdata[31:24];
                if (dbg_trace) $display("AXIWR %s addr=%08h idx=%0h data=%08h strb=%b", NAME, aw_addr_r, wr_ptr, wdata, wstrb);
                dbg_writes <= dbg_writes + 16'd1;
                wr_ptr     <= wr_ptr + 1'b1;
                if (wlast) begin
                    wready  <= 1'b0;
                    bvalid  <= 1'b1;
                    wr_open <= 1'b0;
                end
            end
            if (bvalid && bready) begin
                bvalid  <= 1'b0;
                awready <= 1'b1;
            end

            // ---- read path ----
            if (arready && arvalid) begin
                arready <= 1'b0;
                rvalid  <= 1'b1;
                rd_ptr  <= ar_word;
                rd_left <= arlen;
                rlast   <= (arlen == 4'd0);
                if (dbg_trace) $display("AXIRD %s addr=%08h len=%0d idx=%0h", NAME, araddr, arlen, ar_word);
            end
            if (rvalid && rready) begin
                if (rlast) begin
                    rvalid  <= 1'b0;
                    rlast   <= 1'b0;
                    arready <= 1'b1;
                end else begin
                    rd_ptr  <= rd_ptr + 1'b1;
                    rd_left <= rd_left - 4'd1;
                    rlast   <= (rd_left == 4'd1);
                end
            end
        end
    end
endmodule
