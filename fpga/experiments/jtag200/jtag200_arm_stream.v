`timescale 1ns/1ps
// ARM APACC DRW stream for the two-TCK serializer word. The TAR request
// was already posted by the setup core. Each frame receives the preceding
// AP response; the last response is collected by an ordinary DP fence.
module jtag200_arm_stream (
    input wire clk, reset, start,
    input wire write_block, verify, invert,
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
    wire [7:0] frame_words = frame_bits[8:1];
    wire [6:0] lead = sample_offset + 7'd14;
    wire [31:0] pattern = tx_word ^ {32{invert}};
    wire [39:0] frame_tdi = {write_block ? pattern : 32'd0,
                             write_block ? 3'd6 : 3'd7, 5'b0};
    localparam [41:0] FRAME_TMS = 42'h30000000001;

    reg running = 0, sending = 0;
    reg [7:0] words_left;
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
        if (sending) begin
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

    // Capture 36 samples as 18 pairs. If ACK starts in the second half
    // of a word, include one preceding bit and drop it after capture.
    // RX runs independently of TX, including across the next DR frame.
    reg [7:0] rx_wait;
    reg [4:0] pairs;
    reg [35:0] samples;
    wire [1:0] lane = lead[1:0];
    wire [1:0] sample_pair = {rx_word[{1'b1,lane}], rx_word[{1'b0,lane}]};
    wire [35:0] next_samples = {sample_pair,samples[35:2]};
    wire [2:0] wire_ack = lead[2] ? {sample_pair,samples[35]} :
                                                    {sample_pair[0],samples[35:34]};
    wire receiving = running && status == 0 && received < count && rx_wait == 0;
    wire received_frame = receiving && pairs == 17;
    assign data_valid = received_frame && !write_block && received != 0;
    assign data_addr = received;  // word zero is the posted TAR response
    assign data_word = lead[2] ? next_samples[35:4] : next_samples[34:3];

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
            pairs <= 0;
            samples <= 0;
        end else if (running) begin
            if (sending) begin
                bits_sent <= bits_sent + 32'd2;
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
                    tms_bits <= tms_bits >> 2;
                    tdi_bits <= tdi_bits >> 2;
                end
            end
            if (rx_wait != 0)
                rx_wait <= rx_wait - 1'b1;
            if (receiving) begin
                samples <= next_samples;
                pairs <= pairs + 1'b1;
                // Detect WAIT before the frame boundary. Finish the
                // already-started frame to return to RTI, then stop.
                // Never restart a block whose writes may have executed.
                if (pairs == 1 && wire_ack != 3'b010)
                    status <= wire_ack == 3'b001 ? 8'd2 : 8'd4;
                if (received_frame) begin
                    received <= received + 1'b1;
                    pairs <= 0;
                    rx_wait <= frame_words - 8'd18;
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
