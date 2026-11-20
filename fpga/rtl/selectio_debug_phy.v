`timescale 1ns/1ps
// One physical quartet per 100 MHz parallel clock. The 50 MHz JTAG
// producer launches eight slots on the same MMCM; neither clock is gated.
module selectio_debug_phy (
    input wire serial_clk, quad_clk, octet_clk, reset,
    input wire [1:0] owner, // 0 park, 1 compatibility, 2 JTAG, 3 SWD
    input wire legacy_clock, legacy_data, legacy_release, legacy_tdi, legacy_tdi_release,
    input wire [23:0] jtag_lanes,
    output reg [7:0] jtag_samples,
    input wire [3:0] swd_clock, swd_data, swd_release,
    output wire [3:0] swd_samples,
    input wire tap_clk, tdo_load, swdio_load,
    input wire [4:0] tdo_tap, swdio_tap,
    inout wire clock_pin, data_pin, tdi_pin, input wire tdo_pin,
    output wire clock_level, data_level, tdi_level, tdo_level
);
    // Aligned rising edges: observe the toggle on the intervening quartet
    // edge. At the next shared edge the serializer consumes the upper half.
    reg word_tag = 0, previous_tag = 0;
    always @(posedge octet_clk) word_tag <= ~word_tag;
    always @(posedge quad_clk) previous_tag <= word_tag;
    wire first_half = word_tag != previous_tag;
    wire [3:0] jclock = first_half ? jtag_lanes[3:0] : jtag_lanes[7:4];
    wire [3:0] jdata = first_half ? jtag_lanes[11:8] : jtag_lanes[15:12];
    wire [3:0] jtdi = first_half ? jtag_lanes[19:16] : jtag_lanes[23:20];
    wire [3:0] tdo_samples;
    reg [3:0] previous_samples;
    always @(posedge quad_clk) previous_samples <= tdo_samples;
    always @(posedge octet_clk) jtag_samples <= {tdo_samples, previous_samples};

    // The compatibility controller has a programmable FCLK. Its low-rate
    // pin levels cross into the fixed quartet clock while each SWJ half bit
    // is held for at least five quartet cycles (10 MHz maximum).
    (* ASYNC_REG="TRUE" *) reg [4:0] legacy_meta = 5'b00101, legacy_sync = 5'b00101;
    always @(posedge quad_clk) begin
        legacy_meta <= {legacy_clock,legacy_data,legacy_release,legacy_tdi,legacy_tdi_release};
        legacy_sync <= legacy_meta;
    end
    wire legacy = owner == 1;
    wire jtag = owner == 2;
    wire swd = owner == 3;
    wire [3:0] clock_word = legacy ? {4{legacy_sync[4]}} : jtag ? jclock : swd ? swd_clock : 4'b0;
    wire [3:0] data_word = legacy ? {4{legacy_sync[3]}} : jtag ? jdata : swd_data;
    wire [3:0] release_word = legacy ? {4{legacy_sync[2]}} : jtag ? 4'b0 : swd ? swd_release : 4'hf;
    wire [3:0] tdi_word = jtag ? jtdi : {4{legacy_sync[1]}};

    wire swdio_input, tdo_input;
    wire clock_out, data_out, tdi_out, clock_tri, data_tri, tdi_tri;
    selectio_tx clock_tx(serial_clk, quad_clk, reset, clock_word, {4{owner==0}}, clock_out, clock_tri);
    selectio_tx data_tx(serial_clk, quad_clk, reset, data_word, release_word, data_out, data_tri);
    selectio_tx tdi_tx(serial_clk, quad_clk, reset, tdi_word,
                      {4{!jtag && !(legacy && !legacy_sync[0])}}, tdi_out, tdi_tri);
    IOBUF clock_pad(.I(clock_out),.T(clock_tri),.IO(clock_pin),.O(clock_level));
    IOBUF data_pad(.I(data_out),.T(data_tri),.IO(data_pin),.O(swdio_input));
    IOBUF tdi_pad(.I(tdi_out),.T(tdi_tri),.IO(tdi_pin),.O(tdi_level));
    IBUF tdo_pad(.I(tdo_pin),.O(tdo_input));
    selectio_rx data_rx(serial_clk, quad_clk, reset, swdio_input, tap_clk, swdio_load, swdio_tap, swd_samples, data_level);
    selectio_rx tdo_rx(serial_clk, quad_clk, reset, tdo_input, tap_clk, tdo_load, tdo_tap, tdo_samples, tdo_level);
endmodule

module selectio_tx(input wire serial_clk, quad_clk, reset, input wire [3:0] data, release_bits,
                   output wire serial_data, serial_tri);
    OSERDESE2 #(.DATA_RATE_OQ("DDR"), .DATA_WIDTH(4), .DATA_RATE_TQ("DDR"),
                .TRISTATE_WIDTH(4), .INIT_TQ(1'b1), .SRVAL_TQ(1'b1)) shift (
        .CLK(serial_clk), .CLKDIV(quad_clk), .RST(reset), .OCE(1'b1), .TCE(1'b1),
        .D1(data[0]), .D2(data[1]), .D3(data[2]), .D4(data[3]),
        .D5(1'b0), .D6(1'b0), .D7(1'b0), .D8(1'b0),
        .T1(release_bits[0]), .T2(release_bits[1]), .T3(release_bits[2]), .T4(release_bits[3]),
        .SHIFTIN1(1'b0), .SHIFTIN2(1'b0), .TBYTEIN(1'b0), .OQ(serial_data), .TQ(serial_tri)
    );
endmodule

module selectio_rx(input wire serial_clk, quad_clk, reset, pad, tap_clk, load,
                   input wire [4:0] tap, output wire [3:0] samples, output wire pad_level);
    wire delayed;
    (* IODELAY_GROUP="ORBTRACE_INPUTS" *)
    IDELAYE2 #(.DELAY_SRC("IDATAIN"), .IDELAY_TYPE("VAR_LOAD"), .IDELAY_VALUE(0),
               .REFCLK_FREQUENCY(200.0), .HIGH_PERFORMANCE_MODE("TRUE"), .SIGNAL_PATTERN("DATA")) delay_line (
        .IDATAIN(pad), .DATAIN(1'b0), .DATAOUT(delayed), .C(tap_clk), .LD(load), .CNTVALUEIN(tap),
        .CE(1'b0), .INC(1'b0), .LDPIPEEN(1'b0), .REGRST(1'b0), .CINVCTRL(1'b0)
    );
    ISERDESE2 #(.DATA_RATE("DDR"), .DATA_WIDTH(4), .INTERFACE_TYPE("NETWORKING"),
                .IOBDELAY("IFD"), .NUM_CE(1)) shift (
        .D(pad), .O(pad_level), .DDLY(delayed), .CLK(serial_clk), .CLKB(~serial_clk), .CLKDIV(quad_clk),
        .RST(reset), .CE1(1'b1), .CE2(1'b0), .BITSLIP(1'b0), .CLKDIVP(1'b0),
        .OCLK(1'b0), .OCLKB(1'b0), .DYNCLKDIVSEL(1'b0), .DYNCLKSEL(1'b0),
        .OFB(1'b0), .SHIFTIN1(1'b0), .SHIFTIN2(1'b0),
        .Q1(samples[3]), .Q2(samples[2]), .Q3(samples[1]), .Q4(samples[0])
    );
endmodule
