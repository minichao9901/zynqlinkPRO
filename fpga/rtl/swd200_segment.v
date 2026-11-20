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
    output wire done,
    output wire [32:0] captured,
    output wire captured_parity,
    input wire [3:0] rx_slots,
    output reg [3:0] clk_slots, data_slots, release_slots
);
    localparam IDLE = 0, SEND = 1, DRAIN = 2;
    reg [1:0] state = IDLE;
    reg [6:0] remaining;
    reg [63:0] data_shift, drive_shift;
    reg high_half;
    reg park_data = 1, park_release = 1;
    reg [5:0] samples_left;
    reg [7:0] sample_slot;
    reg [32:0] samples;
    reg parity;
    wire two_cycles = rate == 2;
    wire half_word = rate == 0;
    wire second_cycle = two_cycles && remaining > 1;
    wire complete_cycle = !half_word || high_half;
    wire [6:0] emitted = second_cycle ? 7'd2 : 7'd1;
    wire send_tail = state == SEND && complete_cycle && remaining <= emitted;
    // At full rate the first two cycles can go straight to the PHY while
    // the remainder is loaded. A preceding final TX word keeps its slot.
    wire first_word = state != SEND && start && !half_word && count > 2 &&
                      (capture_count == 0 || capture_start >= 4);

    always @* begin
        clk_slots = 0;
        data_slots = {4{park_data}};
        release_slots = {4{park_release}};
        if (first_word) begin
            clk_slots = two_cycles ? 4'b1010 : 4'b1100;
            data_slots = two_cycles ? {{2{bits_out[1]}}, {2{bits_out[0]}}} : {4{bits_out[0]}};
            release_slots = two_cycles ? {{2{!drive[1]}}, {2{!drive[0]}}} : {4{!drive[0]}};
        end else if (state == SEND) begin
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
    wire sample_now = state != IDLE && samples_left != 0 && sample_slot < 4;
    wire sample_twice = two_cycles && sample_slot < 2 && samples_left > 1;
    wire last_sample = samples_left == 0 ||
                       (sample_now && (samples_left == 1 || (sample_twice && samples_left == 2)));
    assign done = (state == DRAIN || send_tail) && last_sample;
    assign captured = !sample_now ? samples :
                      sample_twice ? {aligned[2], aligned[0], samples[32:2]} :
                                     {aligned[0], samples[32:1]};
    assign captured_parity = parity ^ (sample_now && (aligned[0] ^ (sample_twice && aligned[2])));

    always @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            park_data <= 1;
            park_release <= 1;
        end else begin
            if (send_tail) begin
                park_data <= data_shift[second_cycle];
                park_release <= !drive_shift[second_cycle];
            end
            if (start) begin
                state <= SEND;
                remaining <= first_word ? count - (two_cycles ? 7'd2 : 7'd1) : count;
                data_shift <= first_word ? (two_cycles ? bits_out >> 2 : bits_out >> 1) : bits_out;
                drive_shift <= first_word ? (two_cycles ? drive >> 2 : drive >> 1) : drive;
                high_half <= 0;
                sample_slot <= first_word ? capture_start - 8'd4 : capture_start;
                samples_left <= capture_count;
                samples <= 0;
                parity <= 0;
            end else if (state != IDLE) begin
                if (samples_left != 0) begin
                    if (!sample_now) begin
                        sample_slot <= sample_slot - 8'd4;
                    end else begin
                        if (half_word) sample_slot <= sample_slot + 8'd4;
                        if (two_cycles) sample_slot <= {7'b0, sample_slot[0]};
                        samples <= captured;
                        parity <= captured_parity;
                        samples_left <= samples_left - (sample_twice ? 6'd2 : 6'd1);
                    end
                end
                if (done) state <= IDLE;
                else if (send_tail) state <= DRAIN;
                if (state == SEND) high_half <= !high_half;
                if (state == SEND && complete_cycle) begin
                    data_shift <= data_shift >> emitted[1:0];
                    drive_shift <= drive_shift >> emitted[1:0];
                    remaining <= remaining - emitted;
                end
            end
        end
    end
endmodule
