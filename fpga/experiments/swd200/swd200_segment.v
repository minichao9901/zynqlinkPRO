`timescale 1ns/1ps
// Convert complete SWCLK cycles to four DDR slots, including SWDIO ownership.
// clk=0 between segments. Keep the last drive state through the falling edge.
module swd200_segment (
    input wire clk, reset, start,
    input wire [1:0] rate, // 0: 50 MHz, 1: 100 MHz, 2: full serial clock
    input wire [6:0] count,
    input wire [63:0] bits_out, drive,
    input wire [5:0] capture_count,
    input wire [7:0] capture_start,
    output reg done = 0,
    output reg [32:0] captured = 0,
    input wire [3:0] rx_slots,
    output reg [3:0] clk_slots, data_slots, release_slots
);
    localparam IDLE = 0, SEND = 1, DRAIN = 2;
    reg [1:0] state = IDLE;
    reg [6:0] remaining;
    reg [63:0] data_shift, drive_shift;
    reg high_half;
    reg park_data = 1, park_release = 1;
    reg [2:0] drain;
    reg [5:0] samples_left;
    reg [7:0] sample_slot;
    wire two_cycles = rate == 2;
    wire half_word = rate == 0;
    wire second_cycle = two_cycles && remaining > 1;
    wire complete_cycle = !half_word || high_half;
    wire [6:0] emitted = second_cycle ? 7'd2 : 7'd1;

    always @* begin
        clk_slots = 0;
        data_slots = {4{park_data}};
        release_slots = {4{park_release}};
        if (state == SEND) begin
            data_slots = {4{data_shift[0]}};
            release_slots = {4{!drive_shift[0]}};
            if (two_cycles) begin
                clk_slots = second_cycle ? 4'b1010 : 4'b0010;
                if (second_cycle) begin
                    data_slots[3:2] = {2{data_shift[1]}};
                    release_slots[3:2] = {2{!drive_shift[1]}};
                end
            end else if (half_word) begin
                clk_slots = {4{high_half}};
            end else begin
                clk_slots = 4'b1100;
            end
        end
    end

    wire [3:0] aligned = rx_slots >> sample_slot[1:0];
    wire sample_now = samples_left != 0 && sample_slot < 4;
    wire sample_twice = two_cycles && sample_slot < 2 && samples_left > 1;
    wire last_sample = samples_left == 0 ||
                       (sample_now && (samples_left == 1 || (sample_twice && samples_left == 2)));

    always @(posedge clk) begin
        done <= 0;
        if (reset) begin
            state <= IDLE;
            park_data <= 1;
            park_release <= 1;
        end else if (state == IDLE) begin
            if (start) begin
                state <= SEND;
                remaining <= count;
                data_shift <= bits_out;
                drive_shift <= drive;
                high_half <= 0;
                sample_slot <= capture_start;
                samples_left <= capture_count;
                captured <= 0;
            end
        end else begin
            if (samples_left != 0) begin
                if (!sample_now) begin
                    sample_slot <= sample_slot - 8'd4;
                end else begin
                    if (half_word) sample_slot <= sample_slot + 8'd4;
                    if (two_cycles) sample_slot <= {7'b0, sample_slot[0]};
                    if (sample_twice) begin
                        captured <= {aligned[2], aligned[0], captured[32:2]};
                        samples_left <= samples_left - 6'd2;
                    end else begin
                        captured <= {aligned[0], captured[32:1]};
                        samples_left <= samples_left - 6'd1;
                    end
                end
            end
            if (state == SEND) begin
                high_half <= !high_half;
                if (complete_cycle) begin
                    data_shift <= data_shift >> emitted[1:0];
                    drive_shift <= drive_shift >> emitted[1:0];
                    remaining <= remaining - emitted;
                    if (remaining <= emitted) begin
                        park_data <= data_shift[second_cycle];
                        park_release <= !drive_shift[second_cycle];
                        state <= DRAIN;
                        drain <= 3'd3;
                    end
                end
            end else if (drain != 0) begin
                drain <= drain - 1'b1;
            end else if (last_sample) begin
                state <= IDLE;
                done <= 1;
            end
        end
    end
endmodule
