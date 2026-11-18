`timescale 1ns/1ps
// A 50 or 40 MHz PS FCLK1 reference gives a 200 or 160 MHz I/O clock.
// FCLK0 is independent; the PS changes FCLK1 only with phy_hold asserted.
module jtag200_io (
    input wire fclk1, delay_ref, axi_clk, axi_resetn,
    input wire phy_hold,
    (* X_INTERFACE_PARAMETER = "FREQ_HZ 50000000" *) output wire word_clk,
    output wire word_reset, ready,
    input wire delay_load,
    input wire [4:0] delay_value,
    output wire delay_ready,
    input wire [23:0] lane_word,
    output wire [7:0] rx_word,
    output wire tck, tms, tdi, ntrst, nsrst,
    input wire tdo
);
    // Keep the target and its TAP out of reset on a full J7 cable.
    OBUF trst_release (.I(1'b1), .O(ntrst));
    OBUF srst_release (.I(1'b1), .O(nsrst));
    wire clock_reset = phy_hold || !axi_resetn;
    wire clock_locked, feedback_raw, feedback, serial_raw, serial_clk, word_raw;
    MMCME2_BASE #(
        .CLKIN1_PERIOD(20.0), .DIVCLK_DIVIDE(1), .CLKFBOUT_MULT_F(20.0),
        .CLKOUT0_DIVIDE_F(5.0), .CLKOUT1_DIVIDE(20), .STARTUP_WAIT("FALSE")
    ) io_mmcm (
        .CLKIN1(fclk1), .CLKFBIN(feedback), .CLKFBOUT(feedback_raw),
        .CLKOUT0(serial_raw), .CLKOUT1(word_raw), .LOCKED(clock_locked),
        .PWRDWN(1'b0), .RST(clock_reset)
    );
    BUFG feedback_buffer (.I(feedback_raw), .O(feedback));
    BUFG serial_buffer (.I(serial_raw), .O(serial_clk));
    BUFG word_buffer (.I(word_raw), .O(word_clk));

    wire reset_request = clock_reset || !clock_locked;
    (* ASYNC_REG = "TRUE" *) reg [3:0] release_pipe = 4'hf;
    always @(posedge word_clk or posedge reset_request)
        if (reset_request) release_pipe <= 4'hf;
        else release_pipe <= {release_pipe[2:0], 1'b0};
    assign word_reset = release_pipe[3];
    assign ready = !word_reset;

    // IDELAYCTRL requires at least 50 ns of reset after its reference starts.
    reg [5:0] delay_reset_count = 0;
    always @(posedge axi_clk)
        if (!axi_resetn) delay_reset_count <= 0;
        else if (!delay_reset_count[5]) delay_reset_count <= delay_reset_count + 1'b1;

    jtag200_phy phy (
        .serial_clk(serial_clk), .word_clk(word_clk), .reset(word_reset),
        .delay_clk(axi_clk), .delay_ref(delay_ref), .delay_reset(!delay_reset_count[5]),
        .delay_load(delay_load), .delay_value(delay_value), .delay_ready(delay_ready),
        .lane_word(lane_word), .rx_word(rx_word), .tck(tck), .tms(tms), .tdi(tdi), .tdo(tdo)
    );
endmodule
