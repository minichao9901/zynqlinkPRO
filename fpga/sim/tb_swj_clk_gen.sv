`timescale 1ns/1ps
// Self-checking sweep for swj_clk_gen.
//
// Runs each rate for a fixed number of FCLK cycles and checks the integral
// property: the cycles spanned by all completed periods must equal
// periods * ideal_period to within two cycles. That catches any systematic
// frequency bias regardless of how the measurement window lands on the
// quantisation pattern.
//
// The sample offset is only programmable when a half period spans at least
// two FCLK cycles; at TCK > FCLK/4 the high phase is one cycle long, so the
// offset check is limited to the slower rates.
module tb_swj_clk_gen;
    localparam integer FRAC = 16;
    localparam real    CLK_HZ = 120.0e6;
    localparam integer ONE = 1 << FRAC;
    localparam integer RUN_CYCLES = 100000;

    reg clk = 0, rst_n = 0, enable = 1;
    reg [39:0] half_q = 0;
    reg [15:0] sample_off = 0;
    wire clk_out, edge_tick, sample_tick;

    swj_clk_gen dut(.clk(clk),.rst_n(rst_n),.enable(enable),.half_q(half_q),
                    .sample_off(sample_off),.clk_out(clk_out),
                    .edge_tick(edge_tick),.sample_tick(sample_tick));

    always #4.1666665 clk = ~clk;          // 120 MHz
    initial begin #40000000; $fatal(1,"watchdog"); end

    integer cyc = 0;
    always @(posedge clk) cyc = cyc + 1;

    reg clk_d = 0;
    reg smp_d = 0;
    always @(posedge clk) begin
        clk_d <= clk_out;
        smp_d <= sample_tick;
    end

    integer rises = 0, periods = 0, min_p = 1 << 30, max_p = -1;
    integer first_rise = 0, last_rise = 0, pend_rise = -1;
    integer off_min = 1 << 30, off_max = -1, off_cnt = 0;

    always @(posedge clk) begin
        if (clk_out && !clk_d) begin
            rises = rises + 1;
            if (rises == 1) first_rise = cyc;
            if (rises > 1) begin
                periods = periods + 1;
                if (cyc - last_rise < min_p) min_p = cyc - last_rise;
                if (cyc - last_rise > max_p) max_p = cyc - last_rise;
            end
            last_rise = cyc;
            pend_rise = cyc;
        end
        if (smp_d && pend_rise >= 0) begin
            off_cnt = off_cnt + 1;
            if (cyc - pend_rise < off_min) off_min = cyc - pend_rise;
            if (cyc - pend_rise > off_max) off_max = cyc - pend_rise;
            pend_rise = -1;
        end
    end

    task run_case(input real f_req, input integer smp_off);
        real f_exp, f_meas, ppm, ideal_period, err_cycles;
        integer lo_p, hi_p, target_cyc;
        begin
            half_q = $rtoi(CLK_HZ / (2.0 * f_req) * ONE + 0.5);
            sample_off = smp_off[15:0];
            f_exp = CLK_HZ * ONE / (2.0 * half_q);
            ideal_period = 2.0 * half_q / ONE;
            lo_p = $rtoi(ideal_period);
            hi_p = lo_p + 2;

            enable = 0;
            repeat (4) @(posedge clk);
            rises = 0; periods = 0; min_p = 1 << 30; max_p = -1;
            off_min = 1 << 30; off_max = -1; off_cnt = 0; pend_rise = -1;
            @(posedge clk);
            target_cyc = cyc + RUN_CYCLES;
            enable = 1;
            wait (cyc >= target_cyc);
            enable = 0;
            @(posedge clk);

            f_meas = CLK_HZ * periods / (1.0 * (last_rise - first_rise));
            err_cycles = (last_rise - first_rise) - periods * ideal_period;
            ppm = err_cycles / (periods * ideal_period) * 1.0e6;

            $display("req %7.3f MHz  half_q=%0d  exp %8.4f  meas %8.4f MHz  err %+5.2f cyc (%+7.2f ppm)  period %0d..%0d (want %0d..%0d)  smp_off %0d..%0d n=%0d",
                     f_req/1e6, half_q, f_exp/1e6, f_meas/1e6, err_cycles, ppm,
                     min_p, max_p, lo_p, hi_p, off_min, off_max, off_cnt);

            if (min_p < lo_p || max_p > hi_p)
                $fatal(1,"period quantisation out of range for %f", f_req);
            if (err_cycles > 2.0 || err_cycles < -2.0)
                $fatal(1,"systematic period bias %f cycles for %f", err_cycles, f_req);
            if (f_req <= 30.0e6) begin
                if (off_cnt < periods / 2)
                    $fatal(1,"too few sample ticks (%0d vs %0d)", off_cnt, periods);
                if (off_min != off_max)
                    $fatal(1,"sample offset not constant (%0d..%0d)", off_min, off_max);
            end
        end
    endtask

    integer i;
    real cases [0:7];
    initial begin
        cases[0]=1.0e6;  cases[1]=10.0e6; cases[2]=30.0e6; cases[3]=45.0e6;
        cases[4]=50.0e6; cases[5]=52.9e6; cases[6]=55.0e6; cases[7]=60.0e6;
        repeat (5) @(posedge clk);
        rst_n = 1;
        repeat (2) @(posedge clk);
        enable = 0;
        repeat (10) @(posedge clk);
        if (clk_out !== 1'b0 || edge_tick !== 1'b0)
            $fatal(1,"disabled generator not idle");

        for (i=0;i<8;i=i+1) run_case(cases[i], 1);
        $display("PASS swj_clk_gen: 1/10/30/45/50/52.9/55/60 MHz exact on average, half period within one FCLK, sample offset constant where programmable");
        $finish;
    end
endmodule
