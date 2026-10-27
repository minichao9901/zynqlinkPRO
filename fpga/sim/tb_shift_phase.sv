`timescale 1ns/1ps
// Compare the pre-refactor integer-divider shifter with the swj_clk_gen one.
// Both get the same start pulse and shift the same 43-bit frame with no TMS
// ticking, so any difference is purely the tick phase.
module tb_shift_phase;
    reg clk = 0, rst_n = 0, start = 0;
    wire tck_o, tck_n, done_o, done_n, busy_o, busy_n;
    wire [255:0] rx_o, rx_n;

    always #4.1666665 clk = ~clk;

    reg [39:0] half_q = 40'd65536;   // one FCLK cycle per half period

    jtag_shift_old u_old(.clk(clk),.rst_n(rst_n),.start(start),.count(12'd43),
        .half_delay(4'd0),.variable_tms(0),.tms_value(0),.exit_last(0),.capture(0),
        .capture_rise(0),.tdi_mode(2'd0),.tms_data(256'd0),.tdi_data(256'd0),.tdo(1'b1),
        .tck(tck_o),.tms(),.tdi(),.busy(busy_o),.done(done_o),.rx_data(rx_o));

    jtag_shift u_new(.clk(clk),.rst_n(rst_n),.start(start),.count(12'd43),
        .half_q(half_q),.sample_off(16'hFFFF),.mult(2'd0),.variable_tms(0),.tms_value(0),.exit_last(0),
        .capture(0),.capture_rise(0),.tdi_mode(2'd0),.tms_data(256'd0),
        .tdi_data(256'd0),.tdo(1'b1),
        .tck(tck_n),.tms(),.tdi(),.busy(busy_n),.done(done_n),.rx_data(rx_n));

    integer cyc = 0;
    always @(posedge clk) cyc = cyc + 1;

    reg to_d = 0, tn_d = 0;
    integer rises_o = 0, rises_n = 0, first_o = -1, first_n = -1, last_o = -1, last_n = -1;
    integer done_cycle_o = -1, done_cycle_n = -1;
    reg done_both = 0;
    always @(posedge clk) begin
        to_d <= tck_o; tn_d <= tck_n;
        if (tck_o && !to_d) begin rises_o = rises_o + 1; if (first_o < 0) first_o = cyc; last_o = cyc; end
        if (tck_n && !tn_d) begin rises_n = rises_n + 1; if (first_n < 0) first_n = cyc; last_n = cyc; end
        if (done_o && done_cycle_o < 0) done_cycle_o = cyc;
        if (done_n && done_cycle_n < 0) done_cycle_n = cyc;
        if (done_cycle_o >= 0 && done_cycle_n >= 0) done_both = 1;
    end

    initial begin
        #500000; $fatal(1,"watchdog");
    end

    initial begin
        repeat (5) @(posedge clk);
        rst_n = 1;
        repeat (3) @(posedge clk);
        @(negedge clk); start = 1;
        @(negedge clk); start = 0;
        wait (done_both);
        repeat (4) @(posedge clk);
        $display("old: rises=%0d first=%0d last=%0d done=%0d", rises_o, first_o, last_o, done_cycle_o);
        $display("new: rises=%0d first=%0d last=%0d done=%0d", rises_n, first_n, last_n, done_cycle_n);
        $display("delta: first=%0d last=%0d done=%0d", first_n - first_o, last_n - last_o, done_cycle_n - done_cycle_o);
        if (rises_o != rises_n) $fatal(1,"different number of TCK pulses");
        if (rx_o !== rx_n)    $fatal(1,"different captured data");
        if (first_n - first_o != 0 || done_cycle_n - done_cycle_o != 0)
            $display("NOTE: tick phase differs by %0d cycle(s)", first_n - first_o);
        else
            $display("PASS identical tick phase, %0d TCK pulses, same capture", rises_o);
        $finish;
    end
endmodule
