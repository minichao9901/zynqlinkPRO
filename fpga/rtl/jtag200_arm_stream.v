`timescale 1ns/1ps
// ARM APACC DRW stream with two or four TCKs per serializer word. The TAR request
// was already posted by the setup core. Each frame receives the preceding
// AP response; the last response is collected by an ordinary DP fence.
module jtag200_arm_stream (
    input wire clk, reset, start,
    input wire write_block, verify, invert, four_tck, one_tck,
    input wire [8:0] count,
    input wire [7:0] idle_cycles,
    input wire [6:0] sample_offset,
    input wire advance_tms, advance_tdi,
    input wire [7:0] rx_word,
    input wire [31:0] tx_word,
    output wire [8:0] tx_addr,
    output reg [23:0] lane_word,
    output wire data_valid,
    output wire [8:0] data_addr,
    output wire [31:0] data_word,
    output reg done = 0,
    output reg [7:0] status = 0,
    output reg [31:0] bits_sent = 0, frames_sent = 0
);
    // Three navigation clocks, two leading guards, 35 ARM bits, one
    // bypass bit and Update/Idle. Odd idle gives complete two-TCK words.
    wire [8:0] frame_bits = 9'd43 + idle_cycles;
    wire [8:0] frame_words = one_tck ? frame_bits : four_tck ? {1'b0,frame_bits[8:2]} : frame_bits[8:1];
    wire [6:0] lead = sample_offset + (one_tck ? 7'd28 : four_tck ? 7'd7 : 7'd14);
    wire [31:0] pattern = tx_word ^ {32{invert}};
    wire [39:0] frame_tdi = {write_block ? pattern : 32'd0,
                             write_block ? 3'd6 : 3'd7, 5'b0};
    localparam [41:0] FRAME_TMS = 42'h30000000001;

    reg running = 0, sending = 0;
    reg [8:0] words_left;
    reg [8:0] sent, received, write_addr;
    reg [41:0] tms_bits;
    reg [39:0] tdi_bits;
    wire more_frames = sent + 9'd1 < count && status == 0;
    wire next_tms = words_left == 1 ? more_frames : tms_bits[2];
    wire next_tdi = words_left != 1 && tdi_bits[2];
    assign tx_addr = write_block ? (sending ? write_addr : 9'd1) :
                     (received == 0 ? 9'd1 : received);

    always @* begin
        lane_word = 0;
        if (sending && four_tck) begin
            lane_word[7:0] = 8'haa;
            for (integer i=0; i<4; i=i+1) begin
                lane_word[8+2*i+:2] = {2{tms_bits[i]}};
                lane_word[16+2*i+:2] = {2{tdi_bits[i]}};
            end
        end else if (sending && one_tck) begin
            lane_word = {{8{tdi_bits[0]}},{8{tms_bits[0]}},8'hf0};
            if (advance_tms) lane_word[15]=words_left==1 ? more_frames : tms_bits[1];
            if (advance_tdi) lane_word[23]=words_left!=1 && tdi_bits[1];
        end else if (sending) begin
            lane_word[7:0] = 8'hcc;
            lane_word[15:8] = {{4{tms_bits[1]}}, {4{tms_bits[0]}}};
            lane_word[23:16] = {{4{tdi_bits[1]}}, {4{tdi_bits[0]}}};
            if (advance_tms) begin
                lane_word[11] = tms_bits[1];
                lane_word[15] = next_tms;
            end
            if (advance_tdi) begin
                lane_word[19] = tdi_bits[1];
                lane_word[23] = next_tdi;
            end
        end
    end

    // Capture 36 samples as 18 pairs or 40 samples as 10 quads. If ACK starts in the second half
    // of a word, include one preceding bit and drop it after capture.
    // RX runs independently of TX, including across the next DR frame.
    reg [8:0] rx_wait;
    reg [5:0] groups;
    reg [39:0] samples;
    wire [3:0] sample_quad = {rx_word[{2'd3,lead[0]}],rx_word[{2'd2,lead[0]}],
                              rx_word[{2'd1,lead[0]}],rx_word[{2'd0,lead[0]}]};
    wire [1:0] lane = lead[1:0];
    wire [1:0] sample_pair = {rx_word[{1'b1,lane}], rx_word[{1'b0,lane}]};
    wire sample_one=rx_word[lead[2:0]];
    wire [39:0] next_samples = one_tck ? {5'b0,sample_one,samples[34:1]} : four_tck ? {sample_quad,samples[39:4]} :
                                         {4'b0,sample_pair,samples[35:2]};
    wire [7:0] quad_ack_bits = {sample_quad,samples[39:36]};
    wire [2:0] wire_ack = one_tck ? {sample_one,samples[34:33]} : four_tck ? quad_ack_bits[lead[2:1]+:3] : lead[2] ? {sample_pair,samples[35]} :
                                                    {sample_pair[0],samples[35:34]};
    wire receiving = running && status == 0 && received < count && rx_wait == 0;
    wire received_frame = receiving && groups == (one_tck ? 6'd34 : four_tck ? 6'd9 : 6'd17);
    assign data_valid = received_frame && !write_block && received != 0;
    assign data_addr = received;  // word zero is the posted TAR response
    wire [5:0] data_start = 6'd3 + {4'b0,lead[2:1]};
    assign data_word = one_tck ? next_samples[34:3] : four_tck ? next_samples[data_start+:32] : lead[2] ? next_samples[35:4] : next_samples[34:3];

    always @(posedge clk) begin
        done <= 0;
        if (reset) begin
            running <= 0;
            sending <= 0;
            sent <= 0;
            received <= 0;
            status <= 0;
            bits_sent <= 0;
            frames_sent <= 0;
        end else if (start) begin
            running <= 1;
            sending <= 1;
            sent <= 0;
            received <= 0;
            write_addr <= 2;
            status <= 0;
            words_left <= frame_words;
            tms_bits <= FRAME_TMS;
            tdi_bits <= frame_tdi;
            rx_wait <= {4'b0,lead[6:3]};
            groups <= 0;
            samples <= 0;
        end else if (running) begin
            if (sending) begin
                bits_sent <= bits_sent + (one_tck ? 32'd1 : four_tck ? 32'd4 : 32'd2);
                if (words_left == 1) begin
                    sent <= sent + 1'b1;
                    frames_sent <= frames_sent + 1'b1;
                    sending <= more_frames;
                    words_left <= frame_words;
                    tms_bits <= FRAME_TMS;
                    tdi_bits <= frame_tdi;
                    write_addr <= write_addr + 1'b1;
                end else begin
                    words_left <= words_left - 1'b1;
                    tms_bits <= one_tck ? tms_bits >> 1 : four_tck ? tms_bits >> 4 : tms_bits >> 2;
                    tdi_bits <= one_tck ? tdi_bits >> 1 : four_tck ? tdi_bits >> 4 : tdi_bits >> 2;
                end
            end
            if (rx_wait != 0)
                rx_wait <= rx_wait - 1'b1;
            if (receiving) begin
                samples <= next_samples;
                groups <= groups + 1'b1;
                // Detect WAIT before the frame boundary. Finish the
                // already-started frame to return to RTI, then stop.
                // Never restart a block whose writes may have executed.
                if (groups == (one_tck ? 2 : 1) && wire_ack != 3'b010)
                    status <= wire_ack == 3'b001 ? 8'd2 : 8'd4;
                if (received_frame) begin
                    received <= received + 1'b1;
                    groups <= 0;
                    rx_wait <= frame_words - (one_tck ? 9'd35 : four_tck ? 9'd10 : 9'd18);
                    if (data_valid && verify && data_word != pattern)
                        status <= 8'd8;
                end
            end
            if (!sending && (status != 0 || received == count)) begin
                running <= 0;
                done <= 1;
            end
        end
    end
endmodule
