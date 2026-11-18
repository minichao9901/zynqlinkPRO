`timescale 1ns/1ps
module swd200_phy (
    input wire fclk_ref, axi_aclk, axi_aresetn, hold,
    input wire delay_ref, delay_load,
    input wire [4:0] delay_value,
    output wire delay_ready,
    (* X_INTERFACE_PARAMETER = "FREQ_HZ 100000000" *) output wire word_clk,
    output wire word_reset,
    input wire [3:0] clk_slots, data_slots, release_slots,
    output wire [3:0] rx_slots,
    output wire swclk,
    inout wire swdio,
    output wire nsrst
);
    wire clock_reset = hold || !axi_aresetn;
    wire locked, feedback_raw, feedback, serial_raw, serial_clk, word_raw;
    // 50/40 MHz PS reference selects 200/160 MHz serial CLK and
    // 100/80 MHz CLKDIV. All three output signals use the same word boundary.
    MMCME2_BASE #(
        .CLKIN1_PERIOD(20.0), .DIVCLK_DIVIDE(1), .CLKFBOUT_MULT_F(20.0),
        .CLKOUT0_DIVIDE_F(5.0), .CLKOUT1_DIVIDE(10), .STARTUP_WAIT("FALSE")
    ) mmcm (
        .CLKIN1(fclk_ref), .CLKFBIN(feedback), .CLKFBOUT(feedback_raw),
        .CLKOUT0(serial_raw), .CLKOUT1(word_raw), .LOCKED(locked),
        .PWRDWN(1'b0), .RST(clock_reset)
    );
    BUFG feedback_buffer (.I(feedback_raw), .O(feedback));
    BUFG serial_buffer (.I(serial_raw), .O(serial_clk));
    BUFG word_buffer (.I(word_raw), .O(word_clk));

    wire reset_request = clock_reset || !locked;
    (* ASYNC_REG = "TRUE" *) reg [3:0] reset_pipe = 4'hf;
    always @(posedge word_clk or posedge reset_request)
        if (reset_request) reset_pipe <= 4'hf;
        else reset_pipe <= {reset_pipe[2:0], 1'b0};
    assign word_reset = reset_pipe[3];

    wire serial_clock, serial_data, serial_release, swdio_input, swdio_delayed;
    OSERDESE2 #(
        .DATA_RATE_OQ("DDR"), .DATA_WIDTH(4),
        .DATA_RATE_TQ("BUF"), .TRISTATE_WIDTH(1)
    ) clock_out (
        .CLK(serial_clk), .CLKDIV(word_clk), .OCE(1'b1), .RST(word_reset),
        .D1(clk_slots[0]), .D2(clk_slots[1]), .D3(clk_slots[2]), .D4(clk_slots[3]),
        .D5(1'b0), .D6(1'b0), .D7(1'b0), .D8(1'b0),
        .SHIFTIN1(1'b0), .SHIFTIN2(1'b0), .OQ(serial_clock),
        .T1(1'b0), .T2(1'b0), .T3(1'b0), .T4(1'b0), .TCE(1'b0), .TBYTEIN(1'b0)
    );
    OSERDESE2 #(
        .DATA_RATE_OQ("DDR"), .DATA_WIDTH(4), .INIT_OQ(1'b1), .SRVAL_OQ(1'b1),
        .DATA_RATE_TQ("DDR"), .TRISTATE_WIDTH(4), .INIT_TQ(1'b1), .SRVAL_TQ(1'b1)
    ) data_out (
        .CLK(serial_clk), .CLKDIV(word_clk), .OCE(1'b1), .RST(word_reset),
        .D1(data_slots[0]), .D2(data_slots[1]), .D3(data_slots[2]), .D4(data_slots[3]),
        .D5(1'b0), .D6(1'b0), .D7(1'b0), .D8(1'b0),
        .SHIFTIN1(1'b0), .SHIFTIN2(1'b0), .OQ(serial_data),
        .T1(release_slots[0]), .T2(release_slots[1]), .T3(release_slots[2]),
        .T4(release_slots[3]), .TCE(1'b1), .TBYTEIN(1'b0), .TQ(serial_release)
    );
    OBUF clk_pad (.I(serial_clock), .O(swclk));
    IOBUF data_pad (.I(serial_data), .T(serial_release), .O(swdio_input), .IO(swdio));
    OBUF reset_pad (.I(1'b1), .O(nsrst));

    reg [4:0] delay_reset_count = 0;
    always @(posedge axi_aclk)
        if (!axi_aresetn) delay_reset_count <= 0;
        else if (!delay_reset_count[4]) delay_reset_count <= delay_reset_count + 1'b1;
    (* IODELAY_GROUP = "SWD200" *)
    IDELAYCTRL delay_cal (.REFCLK(delay_ref), .RST(!delay_reset_count[4]), .RDY(delay_ready));
    (* IODELAY_GROUP = "SWD200" *)
    IDELAYE2 #(
        .DELAY_SRC("IDATAIN"), .IDELAY_TYPE("VAR_LOAD"), .IDELAY_VALUE(0),
        .REFCLK_FREQUENCY(200.0), .HIGH_PERFORMANCE_MODE("TRUE"), .SIGNAL_PATTERN("DATA")
    ) data_delay (
        .IDATAIN(swdio_input), .DATAIN(1'b0), .DATAOUT(swdio_delayed),
        .C(axi_aclk), .LD(delay_load), .CNTVALUEIN(delay_value),
        .CE(1'b0), .INC(1'b0), .LDPIPEEN(1'b0), .REGRST(1'b0), .CINVCTRL(1'b0)
    );
    ISERDESE2 #(
        .DATA_RATE("DDR"), .DATA_WIDTH(4), .INTERFACE_TYPE("NETWORKING"),
        .IOBDELAY("IFD"), .NUM_CE(1)
    ) data_in (
        .D(1'b0), .DDLY(swdio_delayed), .CLK(serial_clk), .CLKB(~serial_clk),
        .CLKDIV(word_clk), .RST(word_reset), .CE1(1'b1),
        .Q1(rx_slots[3]), .Q2(rx_slots[2]), .Q3(rx_slots[1]), .Q4(rx_slots[0]),
        .BITSLIP(1'b0), .CLKDIVP(1'b0), .OCLK(1'b0), .OCLKB(1'b0),
        .DYNCLKDIVSEL(1'b0), .DYNCLKSEL(1'b0), .OFB(1'b0),
        .SHIFTIN1(1'b0), .SHIFTIN2(1'b0)
    );
endmodule
