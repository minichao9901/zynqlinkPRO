`timescale 1ns/1ps
// The SPI master supplies SCK. All three input words share an oversampling
// clock, with sample 0 earliest. At most one sampling edge per word is legal.
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
    reg bit_valid, bit_value, end_before, end_after, multiple;
    // Register the edge and the CS boundaries before assembling bytes.
    always @(posedge clk) begin
        if (reset || !enable) begin
            previous_sck <= 0;
            bit_valid <= 0; bit_value <= 0;
            end_before <= 0; end_after <= 0; multiple <= 0;
        end else begin
            previous_sck <= sck[3];
            bit_valid <= |edges;
            bit_value <= |(edges & mosi);
            end_before <= (edges[1] && cs_n[0]) ||
                          (edges[2] && |cs_n[1:0]) ||
                          (edges[3] && |cs_n[2:0]);
            end_after <= (!edges && |cs_n) ||
                         (edges[0] && |cs_n[3:1]) ||
                         (edges[1] && |cs_n[3:2]) ||
                         (edges[2] && cs_n[3]);
            multiple <= (edges[0] && |edges[3:1]) ||
                        (edges[1] && |edges[3:2]) ||
                        (edges[2] && edges[3]);
        end
    end

    reg [2:0] bits;
    reg [6:0] shift;
    wire accept_bit = bit_valid && (armed || end_before);
    wire [2:0] next_bits = (end_before ? 3'd0 : bits) + accept_bit;
    always @(posedge clk) begin
        valid <= 0;
        error <= 0;
        if (reset || !enable) begin
            bits <= 0; shift <= 0; data <= 0; armed <= 0;
        end else if (multiple) begin
            bits <= 0; armed <= 0; error <= 1;
        end else begin
            if (end_before || end_after) armed <= 1;
            if (accept_bit) begin
                shift <= {shift[5:0],bit_value};
                if (next_bits == 0) begin
                    data <= {shift,bit_value};
                    valid <= 1;
                end
            end
            if ((end_before && bits != 0) || (end_after && next_bits != 0))
                error <= 1;
            bits <= end_after ? 3'd0 : next_bits;
        end
    end
endmodule
