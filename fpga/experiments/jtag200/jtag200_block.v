`timescale 1ns/1ps
// Connect the existing packet and RISC-V SBA logic to a word-clock PHY.
// AXI hands over its BRAMs and configuration until this block asserts done.
module jtag200_block (
    input wire clk, reset, run,
    input wire write_block,
    input wire [31:0] address,
    input wire [8:0] count, idle_cycles,
    input wire [2:0] half_slots,
    input wire [6:0] sample_offset,
    input wire [31:0] tx_word,
    output wire [8:0] tx_addr, rx_addr,
    output wire [31:0] result_word,
    output wire [3:0] result_enable,
    input wire [7:0] rx_word,
    output wire [23:0] lane_word,
    output reg done = 0,
    output reg [7:0] completion = 0,
    output wire [31:0] bits_sent, segments, busy_errors, other_errors
);
    localparam WAIT_RUN=0, INVALIDATE=1, SETUP=2, SETUP_WAIT=3, ARM_BLOCK=4, BLOCK=5, FINISHED=6;
    reg [2:0] state = WAIT_RUN;
    reg [1:0] setup_index = 0;
    // AXI holds the descriptor stable through the request/complete
    // handshake. Register the entire bundle at its word-clock boundary.
    reg active_write = 0;
    reg [31:0] active_address = 0;
    reg [8:0] active_count = 0, active_idle = 0;
    reg [2:0] active_half = 0;
    reg [6:0] active_sample = 0;
    reg cfg_start = 0, block_start = 0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] request_sync = 0;
    wire packet_start, next_valid, next_ready, core_busy, response_valid, packet_done, packet_error;
    wire [7:0] packet_req, next_req;
    wire [31:0] packet_value, next_value, response;
    wire [2:0] ack;
    wire [7:0] setup_req = setup_index == 0 ? 8'h04 : setup_index == 1 ? 8'h01 : 8'h05;
    wire [31:0] setup_data = setup_index == 1 ? 32'h23000052 : active_address;
    wire packet_active = state == BLOCK;
    wire cmd_en, rsp_en;
    wire [3:0] rsp_we;
    assign result_enable = rsp_en ? rsp_we : 4'b0;
    reg header = 0;
    always @(posedge clk)
        header <= tx_addr == 0;

    wire segment_start, variable_tms, tms_value, exit_last, capture, segment_done;
    wire [11:0] segment_count;
    wire [1:0] tdi_mode;
    wire [255:0] tms_data, tdi_data;
    wire [63:0] segment_rx;
    jtag200_segment phy (
        .clk(clk), .reset(reset), .start(segment_start), .count(segment_count),
        .variable_tms(variable_tms), .tms_value(tms_value), .exit_last(exit_last),
        .capture(capture), .tdi_mode(tdi_mode), .tms_data(tms_data), .tdi_data(tdi_data),
        .half_slots(active_half), .sample_offset(active_sample), .rx_word(rx_word),
        .lane_word(lane_word), .done(segment_done), .rx_data(segment_rx)
    );

    jtag_core #(.EXTERNAL_PHY(1)) core (
        .clk(clk), .rst_n(!reset), .start(packet_active ? packet_start : cfg_start),
        .invalidate(state==INVALIDATE), .operation(3'd0),
        .request(packet_active ? packet_req : setup_req), .wdata(packet_active ? packet_value : setup_data),
        .seq_count(9'b0), .seq_data(256'b0), .seq_tms(1'b0),
        .ir_length(8'd5), .ir_before(11'b0), .ir_after(11'b0), .dr_before(8'b0), .dr_after(8'b0),
        .idcode_ir(8'd1), .riscv_mode(1'b1), .half_delay(4'b0), .idle_cycles(8'b0),
        .late_return(1'b0), .tdo(1'b0), .tdo_alternate(1'b0), .tdi_sense(1'b0),
        .next_valid(packet_active && next_valid), .next_request(next_req), .next_wdata(next_value),
        .next_ready(next_ready), .result_valid(response_valid), .busy(core_busy), .ack(ack), .rdata(response),
        .fence_req(1'b0), .stat_bits(bits_sent), .stat_transfers(segments),
        .external_idle_cycles(active_idle), .segment_start(segment_start),
        .segment_variable_tms(variable_tms), .segment_tms(tms_value), .segment_exit(exit_last),
        .segment_capture(capture), .segment_count(segment_count), .segment_tdi_mode(tdi_mode),
        .segment_tms_data(tms_data), .segment_tdi_data(tdi_data), .segment_done(segment_done),
        .segment_rx(segment_rx), .stat_dmi_busy(busy_errors), .stat_dmi_other(other_errors)
    );

    // Use the release block engine's address+posted-read/final-fence
    // contract. Header is synthesized from the trusted block descriptor.
    wire [31:0] cmd_word = header ? {active_write ? 8'h0d : 8'h0f, 7'b0, active_count, 8'h06} : tx_word;
    wire [15:0] packet_size = 16'd4 + (active_write ? {5'b0,active_count,2'b0} : 16'b0);
    dap_transfer_block_engine #(.ADDR_W(9), .ENABLE_CHAIN(1), .RETRY_MAX(0)) packet (
        .clk(clk), .rst_n(!reset && packet_active), .start(block_start), .packet_len(packet_size),
        .done(packet_done), .error(packet_error), .cmd_en(cmd_en), .cmd_addr(tx_addr),
        .cmd_data(cmd_word), .rsp_en(rsp_en), .rsp_we(rsp_we), .rsp_addr(rx_addr), .rsp_data(result_word),
        .core_start(packet_start), .core_req(packet_req), .core_wdata(packet_value),
        .core_busy(core_busy), .core_result_valid(response_valid), .core_next_ready(next_ready),
        .core_next_valid(next_valid), .core_next_request(next_req), .core_next_wdata(next_value),
        .core_ack(ack), .core_parity_err(1'b0), .core_rdata(response)
    );

    always @(posedge clk) begin
        cfg_start <= 0;
        block_start <= 0;
        request_sync <= reset ? 0 : {request_sync[0],run};
        if (reset) begin
            state <= WAIT_RUN;
            done <= 0;
            completion <= 0;
        end else case (state)
            WAIT_RUN: if (request_sync[1]) begin
                active_write <= write_block;
                active_address <= address;
                active_count <= count;
                active_idle <= idle_cycles;
                active_half <= half_slots;
                active_sample <= sample_offset;
                completion <= 0;
                setup_index <= 0;
                state <= INVALIDATE;
            end
            INVALIDATE: state <= SETUP;
            SETUP: if (!core_busy) begin
                cfg_start <= 1;
                state <= SETUP_WAIT;
            end
            SETUP_WAIT: if (response_valid) begin
                if (ack != 1) begin
                    completion <= {5'b0,ack};
                    state <= FINISHED;
                end else if (setup_index == 2)
                    state <= ARM_BLOCK;
                else begin
                    setup_index <= setup_index + 1'b1;
                    state <= SETUP;
                end
            end
            ARM_BLOCK: begin
                block_start <= 1;
                state <= BLOCK;
            end
            BLOCK: if (packet_done) begin
                completion <= packet_error ? 8'd4 : 8'd1;
                state <= FINISHED;
            end
            FINISHED: begin
                done <= 1;
                if (!request_sync[1]) begin
                    done <= 0;
                    state <= WAIT_RUN;
                end
            end
            default: state <= WAIT_RUN;
        endcase
    end
endmodule
