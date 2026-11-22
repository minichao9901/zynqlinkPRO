`timescale 1ns/1ps
// The SPI master supplies SCK. All three input words share an oversampling
// clock, with sample 0 earliest. A small frequency offset can place two
// edges of the selected polarity in one word, even at nominal 100 MHz.
module selectio_spi_slave_rx (
    input wire clk, reset, enable,
    input wire [1:0] mode,
    input wire [3:0] sck, cs_n, mosi,
    output reg valid, error,
    output reg [7:0] data
);
    reg previous_sck, armed;
    wire rising_sample = !(mode[1] ^ mode[0]);
    wire [3:0] edges = (sck ^ {sck[2:0],previous_sck}) &
                       (rising_sample ? sck : ~sck) & ~cs_n;
    wire [3:0] first_edge = {edges[3] && !edges[2:0],
                             edges[2] && !edges[1:0],
                             edges[1] && !edges[0], edges[0]};
    wire [3:0] second_edge = edges & ~first_edge;
    wire [3:0] last_edge = second_edge ? second_edge : first_edge;
    reg first_valid, second_valid, first_value, second_value;
    reg end_before, end_between, end_after;
    // Register the ordered edges and CS boundaries before assembling bytes.
    always @(posedge clk) begin
        if (reset || !enable) begin
            previous_sck <= 0;
            first_valid <= 0; second_valid <= 0;
            first_value <= 0; second_value <= 0;
            end_before <= 0; end_between <= 0; end_after <= 0;
        end else begin
            previous_sck <= sck[3];
            first_valid <= |first_edge;
            second_valid <= |second_edge;
            first_value <= |(first_edge & mosi);
            second_value <= |(second_edge & mosi);
            end_before <= (first_edge[1] && cs_n[0]) ||
                          (first_edge[2] && |cs_n[1:0]) ||
                          (first_edge[3] && |cs_n[2:0]);
            end_between <= (edges[0] && edges[2] && cs_n[1]) ||
                           (edges[0] && edges[3] && |cs_n[2:1]) ||
                           (edges[1] && edges[3] && cs_n[2]);
            end_after <= (!edges && |cs_n) ||
                         (last_edge[0] && |cs_n[3:1]) ||
                         (last_edge[1] && |cs_n[3:2]) ||
                         (last_edge[2] && cs_n[3]);
        end
    end

    reg [2:0] bits;
    reg [6:0] shift;
    wire first_accept = first_valid && (armed || end_before);
    wire second_accept = second_valid && (armed || end_before || end_between);
    wire [2:0] first_count = (end_before ? 3'd0 : bits) + first_accept;
    wire [2:0] second_count = (end_between ? 3'd0 : first_count) + second_accept;
    wire [7:0] first_shift = {shift,first_value};
    wire [7:0] second_shift = {first_accept ? first_shift[6:0] : shift,second_value};
    wire first_complete = first_accept && first_count == 0;
    wire second_complete = second_accept && second_count == 0;
    always @(posedge clk) begin
        valid <= 0;
        error <= 0;
        if (reset || !enable) begin
            bits <= 0; shift <= 0; data <= 0; armed <= 0;
        end else begin
            if (end_before || end_between || end_after) armed <= 1;
            if (second_accept) shift <= second_shift[6:0];
            else if (first_accept) shift <= first_shift[6:0];
            // Two bits cannot complete two bytes in one word.
            if (second_complete) data <= second_shift;
            else if (first_complete) data <= first_shift;
            valid <= first_complete || second_complete;
            error <= (end_before && bits != 0) ||
                     (end_between && first_count != 0) ||
                     (end_after && second_count != 0);
            bits <= end_after ? 3'd0 : second_count;
        end
    end
endmodule
