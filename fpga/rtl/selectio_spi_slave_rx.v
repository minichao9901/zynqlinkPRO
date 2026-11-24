`timescale 1ns/1ps
// The SPI master supplies SCK. All three input words share an oversampling
// clock, with sample 0 earliest. A small frequency offset can place two
// edges of the selected polarity in one word, even at nominal 100 MHz.
module selectio_spi_slave_rx #(parameter WIDTH=4, FILTER=0) (
    input wire clk, reset, enable,
    input wire [1:0] mode,
    input wire [WIDTH-1:0] sck, cs_n, mosi,
    output reg valid, error,
    output reg [7:0] data
);
    reg previous_sck, armed;
    wire rising_sample = !(mode[1] ^ mode[0]);
    wire [WIDTH-1:0] chip_select, raw_edges, eligible, after_first;
    wire [WIDTH-1:0] first_edge, second_edge, last_edge;
    reg [3:0] clock_hold;
    // At 800 MS/s an accepted 100 MHz bit edge is normally eight slots
    // from its predecessor. Ignore repeat edges closer than five slots.
    localparam SPACING = FILTER ? 5 : 1;
    generate if (FILTER) begin: nss_filter
        reg [3:0] history;
        reg inactive;
        wire [WIDTH+3:0] window = {cs_n,history};
        wire [WIDTH:0] inactive_chain;
        assign inactive_chain[0] = inactive;
        for (genvar i=0; i<WIDTH; i=i+1) begin: slot
            // Preserve the first sampling edge on assertion. A high pulse
            // must occupy at least five slots before it can end a frame.
            assign inactive_chain[i+1] = cs_n[i] && (inactive_chain[i] || (&window[i +: 5]));
            assign chip_select[i] = inactive_chain[i+1];
        end
        always @(posedge clk) begin
            if (reset || !enable) begin history<=4'hf; inactive<=1; end
            else begin history<=cs_n[WIDTH-1 -: 4]; inactive<=inactive_chain[WIDTH]; end
        end
    end else begin
        assign chip_select=cs_n;
    end endgenerate
    assign raw_edges = (sck ^ {sck[WIDTH-2:0],previous_sck}) &
                       (rising_sample ? sck : ~sck) & ~chip_select;
    wire [WIDTH-1:0] cs_before, cs_after, cs_between;
    wire [3:0] next_hold [0:WIDTH-1];
    for (genvar i=0; i<WIDTH; i=i+1) begin: edges_per_slot
        localparam [WIDTH-1:0] EARLIER = (1<<i)-1;
        localparam [WIDTH-1:0] LATER = ~((2<<i)-1);
        localparam [WIDTH-1:0] SPACED = i>=SPACING ? (1<<(i-SPACING+1))-1 : 0;
        assign eligible[i]=raw_edges[i] && (!FILTER || i>=clock_hold);
        assign first_edge[i]=eligible[i] && !(|(eligible & EARLIER));
        assign after_first[i]=eligible[i] && (|(first_edge & SPACED));
        assign second_edge[i]=after_first[i] && !(|(after_first & EARLIER));
        assign cs_before[i]=first_edge[i] && (|(chip_select & EARLIER));
        assign cs_after[i]=last_edge[i] && (|(chip_select & LATER));
        assign cs_between[i]=chip_select[i] && (|(first_edge & EARLIER)) && (|(second_edge & LATER));
        assign next_hold[i]=(FILTER && i+SPACING>WIDTH && last_edge[i]) ? i+SPACING-WIDTH : 0;
    end
    assign last_edge = second_edge ? second_edge : first_edge;
    reg [3:0] hold_from_edge;
    always @* begin
        hold_from_edge=0;
        for (integer i=0; i<WIDTH; i=i+1)
            hold_from_edge=hold_from_edge | next_hold[i];
    end
    reg first_valid, second_valid, first_value, second_value;
    reg end_before, end_between, end_after;
    // Register the ordered edges and CS boundaries before assembling bytes.
    always @(posedge clk) begin
        if (reset || !enable) begin
            previous_sck <= FILTER ? mode[1] : 1'b0;
            clock_hold <= 0;
            first_valid <= 0; second_valid <= 0;
            first_value <= 0; second_value <= 0;
            end_before <= 0; end_between <= 0; end_after <= 0;
        end else begin
            previous_sck <= sck[WIDTH-1];
            clock_hold <= hold_from_edge;
            first_valid <= |first_edge;
            second_valid <= |second_edge;
            first_value <= |(first_edge & mosi);
            second_value <= |(second_edge & mosi);
            end_before <= |cs_before;
            end_between <= |cs_between;
            end_after <= (!last_edge && |chip_select) || (|cs_after);
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
