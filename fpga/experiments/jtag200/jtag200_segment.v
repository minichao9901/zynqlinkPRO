`timescale 1ns/1ps
// Segment packetizer for the 8-slot SelectIO gearbox, in CLKDIV. The input
// words are consumed once per TCK. Return bits use the measured slot offset,
// including the pad flight time and both serializer pipelines.
module jtag200_segment (
    input wire clk, reset, start,
    input wire [11:0] count,
    input wire variable_tms, tms_value, exit_last, capture,
    input wire [1:0] tdi_mode,
    input wire [255:0] tms_data, tdi_data,
    input wire [2:0] half_slots,
    input wire [6:0] sample_offset,
    input wire [7:0] rx_word,
    output reg [23:0] lane_word,
    output reg done = 0,
    output reg [63:0] rx_data = 0
);
    localparam IDLE = 0, SEND = 1, RETURN = 2;
    reg [1:0] state = IDLE;
    reg [11:0] left = 0;
    reg [255:0] modes = 0, data = 0;
    reg [6:0] sampled = 0, limit = 0;
    reg [7:0] sample_pos = 0;
    wire one_slot = half_slots == 1;
    wire [2:0] consumed = one_slot ? (left >= 4 ? 3'd4 : left[2:0]) : 3'd1;

    // 50 MHz uses one TCK per CLKDIV word. At 160/200 MHz each
    // two-slot pair is one TCK, giving four parallel TCKs per word.
    always @* begin
        lane_word = 24'hffff00;
        if (state == SEND) begin
            if (one_slot) begin
                for (integer bit_no = 0; bit_no < 4; bit_no=bit_no+1) begin
                    if (left > bit_no) begin
                        lane_word[2*bit_no+:2] = 2'b10;
                        lane_word[8+2*bit_no+:2] = {2{variable_tms ? modes[bit_no] :
                                                          tms_value || (exit_last && left == bit_no+1)}};
                        lane_word[16+2*bit_no+:2] = {2{tdi_mode == 2 ? data[bit_no] : tdi_mode == 1}};
                    end
                end
            end else begin
                lane_word[7:0] = 8'hf0;
                lane_word[15:8] = {8{variable_tms ? modes[0] : tms_value || (exit_last && left == 1)}};
                lane_word[23:16] = {8{tdi_mode == 2 ? data[0] : tdi_mode == 1}};
            end
        end
    end

    wire [7:0] input_slots = rx_word >> sample_pos[2:0];
    wire [3:0] input_bits = one_slot ?
        {input_slots[6],input_slots[4],input_slots[2],input_slots[0]} :
        {3'b0,input_slots[0]};
    wire [2:0] taken = one_slot ? 3'd4 - {1'b0,sample_pos[2:1]} : 3'd1;
    wire sample_word = sampled < limit && sample_pos < 8;
    wire return_complete = sampled >= limit ||
                           (sample_word && sampled + {4'b0,taken} >= limit);

    always @(posedge clk) begin
        done <= 0;
        if (reset) begin
            state <= IDLE;
            sample_pos <= 0;
            sampled <= 0;
            limit <= 0;
            rx_data <= 0;
        end else if (state == IDLE) begin
            if (start) begin
                modes <= tms_data;
                data <= tdi_data;
                left <= count;
                limit <= !capture ? 7'd0 : count > 44 ? 7'd44 : count[6:0];
                sampled <= 0;
                // The first emitted word now immediately follows start.
                // The calibrated pad/serializer offset is independent of the
                // removed low-clock preamble.
                sample_pos <= {5'b0,half_slots} + {1'b0,sample_offset};
                rx_data <= 0;
                state <= SEND;
            end
        end else begin
            if (sampled < limit) begin
                if (sample_pos >= 8)
                    sample_pos <= sample_pos - 8;
                else begin
                    if (one_slot) sample_pos <= {7'b0,sample_pos[0]};
                    sampled <= sampled + {4'b0,taken};
                    rx_data <= rx_data | ({60'b0,input_bits} << sampled);
                end
            end
            case (state)
                SEND: begin
                    modes <= modes >> consumed;
                    data <= data >> consumed;
                    left <= left - {9'b0,consumed};
                    if (left <= consumed) begin
                        state <= return_complete ? IDLE : RETURN;
                        done <= return_complete;
                    end
                end
                RETURN: if (return_complete) begin
                    state <= IDLE;
                    done <= 1;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
