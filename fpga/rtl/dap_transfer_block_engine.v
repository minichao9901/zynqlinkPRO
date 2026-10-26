`timescale 1ns/1ps
// Minimal hardware CMSIS-DAP TransferBlock engine.
//
// Command BRAM word layout (little endian bytes):
//   byte0=0x06, byte1/2=count, byte3=raw SWD request,
//   bytes4.. = write payload for a write request.
// Response BRAM is word aligned so the PS can DMA it without a byte-shift:
//   word0[15:0]=completed count, word0[23:16]=DAP status,
//   word1..=read data.  The PS adds the three-byte CMSIS-DAP header.
//
// This first version deliberately accepts only ordinary 32-bit SWD memory
// AP reads/writes. Match/timestamp/JTAG/control commands remain on fallback.
module dap_transfer_block_engine #(
    parameter ADDR_W = 10,
    parameter ENABLE_CHAIN = 0,
    parameter integer RETRY_MAX = 64
)(
    input  wire             clk,
    input  wire             rst_n,
    input  wire             start,
    input  wire [15:0]      packet_len,
    output reg              busy,
    output reg              done,
    output reg              error,
    output reg  [15:0]      response_words,
    output wire [4:0]       state_dbg,

    output reg              cmd_en,
    output reg  [ADDR_W-1:0] cmd_addr,
    input  wire [31:0]      cmd_data,
    output reg              rsp_en,
    output reg  [3:0]       rsp_we,
    output reg  [ADDR_W-1:0] rsp_addr,
    output reg  [31:0]      rsp_data,

    output reg              core_start,
    output reg              core_mode,
    output reg  [7:0]       core_req,
    output reg  [31:0]      core_wdata,
    input  wire              core_busy,
    input  wire              core_result_valid,
    input  wire              core_next_ready,
    output wire              core_next_valid,
    output wire [7:0]        core_next_request,
    output wire [31:0]       core_next_wdata,
    input  wire [2:0]        core_ack,
    input  wire              core_parity_err,
    input  wire [31:0]       core_rdata
);
    localparam [4:0] ST_IDLE=0, ST_FETCH_HDR=1, ST_HDR_WAIT=2,
                     ST_DECODE=3, ST_WRITE_HEADER=4, ST_NEXT=5,
                     ST_FETCH_DATA=6, ST_FETCH_DATA_WAIT=7,
                     ST_START_CORE=8, ST_WAIT_CORE=9, ST_STORE_READ=10,
                     ST_FINAL_RDBUFF=11, ST_WRITE_STATUS=12, ST_DONE=13,
                     ST_FETCH_DATA_SAMPLE=14;
    reg [4:0] state;
    reg [31:0] hdr;
    reg [15:0] count, index, result_index;
    reg [7:0] request;
    reg is_read, is_ap;
    reg seen_core_busy;
    reg [2:0] last_ack;
    reg [31:0] last_data;
    reg [7:0] status_code;
    reg need_final_read;
    reg final_phase;
    reg [23:0] core_wait_cnt;
    reg [7:0] retry_left;
    reg [31:0] prefetched_data;
    reg [1:0] prefetch_wait;
    reg prefetch_valid;

    assign core_next_valid = ENABLE_CHAIN && state == ST_WAIT_CORE &&
                             seen_core_busy && !final_phase &&
                             (is_read || index+1'b1 == count || prefetch_valid);
    assign core_next_request = (index+1'b1 == count) ? 8'h0E : request;
    assign core_next_wdata = prefetched_data;
    wire chain_accept = core_next_valid && core_next_ready;
    initial state = ST_IDLE;

    wire [7:0] dap_cmd = hdr[7:0];
    wire [15:0] dap_count = hdr[23:8];
    wire [7:0] dap_req = hdr[31:24];
    assign state_dbg = state;
    wire supported_req = ((dap_req & 8'hF0) == 8'h00) &&
                         ((dap_req & 8'h0C) == 8'h00 ||
                          (dap_req & 8'h0C) == 8'h04 ||
                          (dap_req & 8'h0C) == 8'h08 ||
                          (dap_req & 8'h0C) == 8'h0C);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= ST_IDLE; busy <= 0; done <= 0; error <= 0;
            response_words <= 0; cmd_en <= 0; cmd_addr <= 0;
            rsp_en <= 0; rsp_we <= 0; rsp_addr <= 0; rsp_data <= 0;
            core_start <= 0; core_mode <= 1; core_req <= 0; core_wdata <= 0;
            hdr <= 0; count <= 0; index <= 0; result_index <= 0;
            request <= 0; is_read <= 0; is_ap <= 0; seen_core_busy <= 0;
            last_ack <= 0; last_data <= 0; status_code <= 0;
            need_final_read <= 0;
            final_phase <= 0;
            core_wait_cnt <= 24'hFFFFFF;
            retry_left <= 0;
            prefetched_data <= 0;
            prefetch_wait <= 0;
            prefetch_valid <= 0;
        end else begin
            cmd_en <= 0;
            rsp_en <= 0;
            rsp_we <= 0;
            core_start <= 0;
            // Fetch the next write while the current serial transfer runs.
            // Two edges cover the registered BRAM enable and its read latency.
            if (prefetch_wait != 0) begin
                prefetch_wait <= prefetch_wait - 1'b1;
                if (prefetch_wait == 1) begin
                    prefetched_data <= cmd_data;
                    prefetch_valid <= 1;
                end
            end
            case (state)
                ST_IDLE: begin
                    busy <= 0;
                    if (start) begin
                        busy <= 1;
                        done <= 0;
                        error <= 0;
                        count <= 0;
                        index <= 0;
                        result_index <= 0;
                        is_read <= 0;
                        is_ap <= 0;
                        final_phase <= 0;
                        response_words <= 0;
                        prefetch_wait <= 0;
                        prefetch_valid <= 0;
                        cmd_addr <= 0;
                        cmd_en <= 1;
                        state <= ST_HDR_WAIT;
                    end
                end
                ST_HDR_WAIT: begin
                    // BRAM read latency is one cycle.
                    state <= ST_DECODE;
                end
                ST_DECODE: begin
                    hdr <= cmd_data;
                    // cmd_data is the first four packet bytes in little endian.
                    if (cmd_data[7:0] != 8'h06 || packet_len < 4 ||
                        cmd_data[23:8] == 0 || cmd_data[23:8] > 1023 ||
                        (cmd_data[31:24] & 8'hF0) != 0 || !cmd_data[24] ||
                        (!cmd_data[25] && packet_len < (4 + {cmd_data[23:8],2'b00}))) begin
                        error <= 1; status_code <= 8'h07; state <= ST_WRITE_HEADER;
                    end else begin
                        count <= cmd_data[23:8];
                        request <= cmd_data[31:24];
                        is_read <= cmd_data[25];
                        is_ap <= cmd_data[24];
                        index <= 0;
                        result_index <= 0;
                        // AP reads have one posted dummy and a final RDBUFF.
                        need_final_read <= cmd_data[25] && cmd_data[24];
                        final_phase <= 0;
                        status_code <= 8'h01;
                        state <= ST_WRITE_HEADER;
                    end
                end
                ST_WRITE_HEADER: begin
                    rsp_en <= 1;
                    rsp_we <= 4'b0111;
                    rsp_addr <= 0;
                    rsp_data <= {8'd0, status_code, count};
                    // Only reads carry data words behind the three-byte header.
                    response_words <= is_read ? (count + 1'b1) : 16'd1;
                    if (error || count == 0) state <= ST_DONE;
                    else state <= ST_NEXT;
                end
                ST_NEXT: begin
                    if (error) state <= ST_WRITE_STATUS;
                    else if (is_ap && index == count) begin
                        // Drain posted reads and check completion of AP writes.
                        core_req <= 8'h0E;
                        final_phase <= 1;
                        retry_left <= RETRY_MAX;
                        core_wait_cnt <= 24'h03FFFF;
                        state <= ST_FINAL_RDBUFF;
                    end else if (index == count) begin
                        state <= ST_WRITE_STATUS;
                    end else if (is_read) begin
                        core_req <= request;
                        retry_left <= RETRY_MAX;
                        core_wait_cnt <= 24'h03FFFF;
                        state <= ST_START_CORE;
                    end else begin
                        cmd_addr <= index + 1'b1;
                        cmd_en <= 1;
                        state <= ST_FETCH_DATA_WAIT;
                    end
                end
                ST_FETCH_DATA_WAIT: begin
                    // BRAM data becomes valid one cycle after cmd_en; sample in
                    // the following state, otherwise the header word is used.
                    state <= ST_FETCH_DATA_SAMPLE;
                end
                ST_FETCH_DATA_SAMPLE: begin
                    core_wdata <= cmd_data;
                    core_req <= request;
                    retry_left <= RETRY_MAX;
                    core_wait_cnt <= 24'h03FFFF;
                    if (index + 1'b1 < count) begin
                        cmd_en <= 1;
                        cmd_addr <= index + 2'd2;
                        prefetch_wait <= 2;
                        prefetch_valid <= 0;
                    end
                    state <= ST_START_CORE;
                end
                ST_START_CORE: begin
                    if (core_busy) begin
                        // Never restart the core in the middle of a frame.
                        core_wait_cnt <= core_wait_cnt - 1'b1;
                        if (core_wait_cnt == 24'd0) begin
                            error <= 1; status_code <= 8'h09;
                            state <= ST_WRITE_STATUS;
                        end
                    end else begin
                        core_mode <= 1;
                        core_start <= 1;
                        seen_core_busy <= 0;
                        core_wait_cnt <= 24'h03FFFF;
                        state <= ST_WAIT_CORE;
                    end
                end
                ST_WAIT_CORE: begin
                    if ((ENABLE_CHAIN && core_result_valid) ||
                        (!core_busy && seen_core_busy)) begin
                        last_ack <= core_ack;
                        last_data <= core_rdata;
                        if (core_ack == 3'b010 && retry_left != 8'd0) begin
                            // Target busy: re-issue the same transfer.
                            retry_left <= retry_left - 1'b1;
                            core_wait_cnt <= 24'h03FFFF;
                            state <= ST_START_CORE;
                        end else if ((core_req[1] && core_parity_err) || core_ack != 3'b001) begin
                            status_code <= (core_req[1] && core_parity_err) ? 8'h08 : {5'd0,core_ack};
                            error <= 1;
                            state <= ST_WRITE_STATUS;
                        end else if (final_phase) begin
                            if (is_read) begin
                                rsp_en <= 1;
                                rsp_we <= 4'hF;
                                rsp_addr <= result_index + 1'b1;
                                rsp_data <= core_rdata;
                                result_index <= result_index + 1'b1;
                            end
                            final_phase <= 0;
                            state <= ST_WRITE_STATUS;
                        end else if (is_read) begin
                            if (!(is_ap && index == 0)) begin
                                rsp_en <= 1;
                                rsp_we <= 4'hF;
                                rsp_addr <= result_index + 1'b1;
                                rsp_data <= core_rdata;
                                result_index <= result_index + 1'b1;
                            end
                            index <= index + 1'b1;
                            // Completion already proves the core is idle. Start
                            // the next read directly, avoiding NEXT/START bubbles.
                            core_req <= (index + 1'b1 == count) ? 8'h0E : request;
                            final_phase <= (index + 1'b1 == count);
                            core_start <= !chain_accept;
                            seen_core_busy <= chain_accept;
                            retry_left <= RETRY_MAX;
                            core_wait_cnt <= 24'h03FFFF;
                        end else begin
                            index <= index + 1'b1;
                            if (index + 1'b1 == count || prefetch_valid) begin
                                core_req <= (index + 1'b1 == count) ? 8'h0E : request;
                                final_phase <= (index + 1'b1 == count);
                                core_wdata <= prefetched_data;
                                core_start <= !chain_accept;
                                seen_core_busy <= chain_accept;
                                retry_left <= RETRY_MAX;
                                core_wait_cnt <= 24'h03FFFF;
                                prefetch_valid <= 0;
                                if (index + 2'd2 < count) begin
                                    cmd_en <= 1;
                                    cmd_addr <= index + 2'd3;
                                    prefetch_wait <= 2;
                                end
                            end else state <= ST_NEXT;
                        end
                    end else if (core_busy) begin
                        seen_core_busy <= 1;
                        core_wait_cnt <= core_wait_cnt-1'b1;
                        if (core_wait_cnt == 0) begin
                            error <= 1; status_code <= 8'h09; state <= ST_WRITE_STATUS;
                        end
                    end else begin
                        core_wait_cnt <= core_wait_cnt-1'b1;
                        if (core_wait_cnt == 0) begin
                            error <= 1; status_code <= 8'h09; state <= ST_WRITE_STATUS;
                        end
                    end
                end
                ST_FINAL_RDBUFF: begin
                    // The request (DP RDBUFF) was presented in ST_NEXT; start it
                    // through the same core-idle guard as ordinary transfers.
                    retry_left <= RETRY_MAX;
                    state <= ST_START_CORE;
                end
                ST_WRITE_STATUS: begin
                    rsp_en <= 1;
                    rsp_we <= 4'b1111;
                    rsp_addr <= 0;
                    // Report only words actually completed, including partial
                    // reads when the posted pipeline fails before RDBUFF.
                    rsp_data <= {8'd0,status_code,(is_read ? result_index : index)};
                    response_words <= is_read ? result_index + 1'b1 : 16'd1;
                    state <= ST_DONE;
                end
                ST_DONE: begin
                    busy <= 0;
                    done <= 1;
                    state <= ST_IDLE;
                end
                default: begin
                    busy <= 0; error <= 1; state <= ST_IDLE;
                end
            endcase
        end
    end
endmodule

