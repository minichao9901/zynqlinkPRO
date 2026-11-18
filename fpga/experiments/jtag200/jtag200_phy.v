`timescale 1ns/1ps
// Xilinx 7-series DDR 8:1 I/O gearbox. Slot 0 is transmitted first.
module jtag200_phy (
    input wire serial_clk, word_clk, reset,
    input wire delay_clk, delay_ref, delay_reset, delay_load,
    input wire [4:0] delay_value,
    output wire delay_ready,
    input wire [23:0] lane_word,
    output wire [7:0] rx_word,
    output wire tck, tms, tdi,
    input wire tdo
);
    wire [2:0] serial_q;
    genvar lane;
    generate for (lane = 0; lane < 3; lane = lane + 1) begin: transmit
        wire [7:0] d = lane_word[lane*8 +: 8];
        OSERDESE2 #(
            .DATA_RATE_OQ("DDR"), .DATA_WIDTH(8), .SERDES_MODE("MASTER"),
            .DATA_RATE_TQ("BUF"), .TRISTATE_WIDTH(1)
        ) launch (
            .CLK(serial_clk), .CLKDIV(word_clk), .RST(reset), .OCE(1'b1),
            .D1(d[0]), .D2(d[1]), .D3(d[2]), .D4(d[3]),
            .D5(d[4]), .D6(d[5]), .D7(d[6]), .D8(d[7]),
            .OQ(serial_q[lane]), .SHIFTIN1(1'b0), .SHIFTIN2(1'b0),
            .T1(1'b0), .T2(1'b0), .T3(1'b0), .T4(1'b0),
            .TCE(1'b0), .TBYTEIN(1'b0)
        );
    end endgenerate

    OBUF tck_pad (.I(serial_q[0]), .O(tck));
    OBUF tms_pad (.I(serial_q[1]), .O(tms));
    OBUF tdi_pad (.I(serial_q[2]), .O(tdi));

    wire tdo_raw, tdo_delayed;
    IBUF tdo_pad (.I(tdo), .O(tdo_raw));
    (* IODELAY_GROUP = "JTAG200_TDO" *)
    IDELAYCTRL delay_cal (.REFCLK(delay_ref), .RST(delay_reset), .RDY(delay_ready));
    (* IODELAY_GROUP = "JTAG200_TDO" *)
    IDELAYE2 #(
        .DELAY_SRC("IDATAIN"), .IDELAY_TYPE("VAR_LOAD"), .IDELAY_VALUE(0),
        .REFCLK_FREQUENCY(200.0), .HIGH_PERFORMANCE_MODE("TRUE"), .SIGNAL_PATTERN("DATA")
    ) tdo_delay (
        .IDATAIN(tdo_raw), .DATAIN(1'b0), .DATAOUT(tdo_delayed),
        .C(delay_clk), .LD(delay_load), .CNTVALUEIN(delay_value),
        .CE(1'b0), .INC(1'b0), .LDPIPEEN(1'b0), .REGRST(1'b0), .CINVCTRL(1'b0)
    );
    // Q1 contains the newest sampled bit. Reverse to match TX slot order.
    ISERDESE2 #(
        .DATA_RATE("DDR"), .DATA_WIDTH(8), .INTERFACE_TYPE("NETWORKING"),
        .IOBDELAY("IFD"), .NUM_CE(1), .SERDES_MODE("MASTER")
    ) receive (
        .D(1'b0), .DDLY(tdo_delayed), .CLK(serial_clk), .CLKB(~serial_clk),
        .CLKDIV(word_clk), .RST(reset), .CE1(1'b1), .CE2(1'b0),
        .Q1(rx_word[7]), .Q2(rx_word[6]), .Q3(rx_word[5]), .Q4(rx_word[4]),
        .Q5(rx_word[3]), .Q6(rx_word[2]), .Q7(rx_word[1]), .Q8(rx_word[0]),
        .BITSLIP(1'b0), .CLKDIVP(1'b0), .OCLK(1'b0), .OCLKB(1'b0),
        .DYNCLKDIVSEL(1'b0), .DYNCLKSEL(1'b0), .OFB(1'b0), .SHIFTIN1(1'b0), .SHIFTIN2(1'b0)
    );
endmodule
