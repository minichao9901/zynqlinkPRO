`timescale 1ns/1ps
// ADIv5 single-drop SWD with one turnaround clock and no data phase on WAIT
// or FAULT. One command is in flight. A reported write is never replayed.
module swd200_link (
    input wire clk, reset,
    input wire [1:0] rate,
    input wire [5:0] ack_sample, data_sample,
    input wire [3:0] idle_cycles,
    input wire start, enter_swd,
    input wire [3:0] request,
    input wire [31:0] write_data,
    output wire busy,
    output reg done = 0,
    output reg [2:0] ack = 0,
    output reg parity_error = 0,
    output reg [31:0] read_data = 0,
    input wire [3:0] rx_slots,
    output wire [3:0] clk_slots, data_slots, release_slots
);
    localparam IDLE = 0, RESET_FIRST = 1, SELECT_SWD = 2, RESET_LAST = 3,
               HEADER = 4, READ_DATA = 5, WRITE_DATA = 6, ERROR_TURN = 7, FINISH = 8;
    reg [3:0] state = IDLE;
    reg segment_start = 0;
    reg [6:0] count;
    reg [63:0] bits_out, drive;
    reg [5:0] capture_count;
    reg [7:0] capture_start;
    reg [3:0] active_request;
    reg [32:0] active_write;
    wire segment_done;
    wire [32:0] captured;
    wire [7:0] header_offset = rate == 2 ? 8'd18 : rate == 1 ? 8'd36 : 8'd72;
    wire [7:0] header = {1'b1, 1'b0, ^request, request, 1'b1};
    wire [63:0] all_drive = 64'hffffffffffffffff;
    wire [6:0] idle_count = {3'b0, idle_cycles};
    assign busy = state != IDLE;

    swd200_segment segment (
        .clk(clk), .reset(reset), .start(segment_start), .rate(rate), .count(count),
        .bits_out(bits_out), .drive(drive), .capture_count(capture_count),
        .capture_start(capture_start), .done(segment_done), .captured(captured),
        .rx_slots(rx_slots), .clk_slots(clk_slots), .data_slots(data_slots),
        .release_slots(release_slots)
    );

    task emit;
        input [6:0] clocks;
        input [63:0] data, owners;
        input [5:0] samples;
        input [7:0] sample_at;
        begin
            segment_start <= 1;
            count <= clocks;
            bits_out <= data;
            drive <= owners;
            capture_count <= samples;
            capture_start <= sample_at;
        end
    endtask

    always @(posedge clk) begin
        segment_start <= 0;
        done <= 0;
        if (reset) begin
            state <= IDLE;
            ack <= 0;
            parity_error <= 0;
            read_data <= 0;
        end else if (state == IDLE && start) begin
            ack <= 0;
            parity_error <= 0;
            read_data <= 0;
            active_request <= request;
            active_write <= {^write_data, write_data};
            if (enter_swd) begin
                emit(64, all_drive, all_drive, 0, 0);
                state <= RESET_FIRST;
            end else begin
                emit(12, {56'b0, header}, 64'hff, 3, header_offset + {2'b0, ack_sample});
                state <= HEADER;
            end
        end else if (segment_done) begin
            case (state)
                RESET_FIRST: begin
                    emit(64, 64'hffffffffffffe79e, all_drive, 0, 0);
                    state <= SELECT_SWD;
                end
                SELECT_SWD: begin
                    emit(24, 64'hffff, all_drive, 0, 0);
                    state <= RESET_LAST;
                end
                HEADER: begin
                    ack <= captured[32:30];
                    if (captured[32:30] == 3'b010 || captured[32:30] == 3'b100) begin
                        emit(7'd1 + idle_count, 0, all_drive << 1, 0, 0);
                        state <= ERROR_TURN;
                    end else if (captured[32:30] != 3'b001) begin
                        // Ownership is unknown. Keep the pin released until
                        // the caller explicitly starts a new line reset.
                        state <= FINISH;
                    end else if (active_request[1]) begin
                        // Data and parity are followed by a target-to-host
                        // turnaround. The idle clocks belong to the host.
                        emit(7'd34 + idle_count, 0, all_drive << 34, 33, {2'b0, data_sample});
                        state <= READ_DATA;
                    end else begin
                        emit(7'd34 + idle_count, {30'b0, active_write, 1'b0}, all_drive << 1, 0, 0);
                        state <= WRITE_DATA;
                    end
                end
                READ_DATA: begin
                    parity_error <= ^captured;
                    read_data <= captured[31:0];
                    state <= FINISH;
                end
                RESET_LAST, WRITE_DATA, ERROR_TURN: state <= FINISH;
                default: state <= IDLE;
            endcase
        end else if (state == FINISH) begin
            done <= 1;
            state <= IDLE;
        end
    end
endmodule
