`timescale 1ns/1ps
// ADIv5 single-drop SWD with one turnaround clock and no data phase on WAIT
// or FAULT. One command is in flight. A reported write is never replayed.
module swd200_link (
    input wire clk, reset,
    input wire [1:0] rate,
    input wire [5:0] ack_sample, data_sample,
    input wire [3:0] idle_cycles,
    input wire start, enter_swd,
    input wire [7:0] header,
    input wire [32:0] write_packet,
    output wire done,
    output wire [2:0] ack,
    output wire parity_error,
    output wire [31:0] read_data,
    input wire [3:0] rx_slots,
    output wire [3:0] clk_slots, data_slots, release_slots
);
    localparam IDLE = 0, RESET_FIRST = 1, SELECT_SWD = 2, RESET_LAST = 3,
               HEADER = 4, READ_DATA = 5, WRITE_DATA = 6, ERROR_TURN = 7;
    reg [2:0] state = IDLE;
    reg segment_start;
    reg [2:0] next_state;
    reg [6:0] count;
    reg [63:0] bits_out, drive;
    reg [5:0] capture_count;
    reg [7:0] capture_start;
    reg active_read;
    reg [2:0] active_ack;
    reg [32:0] active_write;
    reg seed_pending = 0, read_seed;
    wire segment_done, captured_parity;
    wire [32:0] captured;
    wire [7:0] header_offset = rate == 2 ? 8'd18 : rate == 1 ? 8'd36 : 8'd72;
    wire [63:0] all_drive = 64'hffffffffffffffff;
    wire [6:0] idle_count = {3'b0, idle_cycles};
    // With these phases the first released clock after ACK can be queued
    // in advance. It is D0 for a successful read and turnaround otherwise.
    // At either phase, that read sample lands in the first RX word after
    // the ACK decision, before the regular sampler starts with D1.
    wire early_clock = rate == 2 && ack_sample[5:1] == 5'd6 && data_sample[5:1] == 5'd6;
    wire [6:0] body_count = (early_clock ? 7'd33 : 7'd34) + idle_count;
    wire [63:0] read_drive = early_clock ? all_drive << 33 : all_drive << 34;
    wire [63:0] write_payload = early_clock ? {31'b0, active_write} : {30'b0, active_write, 1'b0};
    wire [2:0] sampled_ack = captured[32:30];
    wire ack_ok = sampled_ack == 3'b001;
    wire ack_rejected = sampled_ack == 3'b010 || sampled_ack == 3'b100;
    assign done = segment_done && (state == RESET_LAST || state == READ_DATA ||
                  state == WRITE_DATA || state == ERROR_TURN ||
                  (state == HEADER && !ack_ok && !ack_rejected));
    assign ack = state == HEADER ? sampled_ack : active_ack;
    wire [32:0] read_packet = early_clock ? {captured[32:1], read_seed} : captured;
    assign parity_error = state == READ_DATA && (captured_parity ^ (early_clock && read_seed));
    assign read_data = state == READ_DATA ? read_packet[31:0] : 32'b0;

    swd200_segment segment (
        .clk(clk), .reset(reset), .start(segment_start), .rate(rate), .count(count),
        .bits_out(bits_out), .drive(drive), .capture_count(capture_count),
        .capture_start(capture_start), .done(segment_done), .captured(captured),
        .captured_parity(captured_parity),
        .rx_slots(rx_slots), .clk_slots(clk_slots), .data_slots(data_slots),
        .release_slots(release_slots)
    );

    task emit;
        input [6:0] clocks;
        input [63:0] data, owners;
        input [5:0] samples;
        input [7:0] sample_at;
        input [2:0] following_state;
        begin
            segment_start = 1;
            count = clocks;
            bits_out = data;
            drive = owners;
            capture_count = samples;
            capture_start = sample_at;
            next_state = following_state;
        end
    endtask

    always @* begin
        segment_start = 0;
        count = 0;
        bits_out = 0;
        drive = 0;
        capture_count = 0;
        capture_start = 0;
        next_state = state;
        if (start) begin
            if (enter_swd)
                emit(64, all_drive, all_drive, 0, 0, RESET_FIRST);
            else
                emit(early_clock ? 7'd13 : 7'd12, {56'b0, header},
                     64'hff, 3, header_offset + {2'b0, ack_sample}, HEADER);
        end else if (segment_done) begin
            next_state = IDLE;
            case (state)
                RESET_FIRST: emit(64, 64'hffffffffffffe79e, all_drive, 0, 0, SELECT_SWD);
                SELECT_SWD: emit(24, 64'hffff, all_drive, 0, 0, RESET_LAST);
                HEADER: begin
                    if (ack_rejected)
                        emit(early_clock ? idle_count : 7'd1 + idle_count, 0,
                             early_clock ? all_drive : all_drive << 1, 0, 0, ERROR_TURN);
                    else if (ack_ok && active_read)
                        emit(body_count, 0, read_drive, early_clock ? 6'd32 : 6'd33,
                             {2'b0, data_sample}, READ_DATA);
                    else if (ack_ok)
                        emit(body_count, write_payload, early_clock ? all_drive : all_drive << 1, 0, 0, WRITE_DATA);
                    // An invalid ACK leaves the bus released.
                end
                default: begin end
            endcase
        end
    end

    always @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            seed_pending <= 0;
        end else begin
            state <= next_state;
            if (start) begin
                active_read <= header[2];
                active_write <= write_packet;
            end
            seed_pending <= state == HEADER && segment_done && ack_ok && active_read && early_clock;
            if (seed_pending) read_seed <= rx_slots[{1'b0, data_sample[0]}];
            if (state == HEADER && segment_done) active_ack <= sampled_ack;
        end
    end
endmodule
