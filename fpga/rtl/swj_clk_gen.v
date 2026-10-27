`timescale 1ns/1ps
// Shared SWJ clock generator: fixed FCLK, arbitrary average SWCLK/TCK.
//
// The half period is programmed as a fixed-point number of FCLK cycles (Q16).
// An integer down-counter times each half period while a small fraction
// accumulator decides whether that half period gets one extra FCLK cycle, so
// the average period is exact without a divider and each half period is
// within one FCLK cycle of the ideal length.
//
// `sample_tick` is emitted a fixed number of FCLK cycles after each rising
// edge. Since FCLK is fixed and the offset counts from the real edge, the
// sampling margin is a constant time and no longer depends on the requested
// frequency, which is what made the old integer divider fragile.
module swj_clk_gen #(
        parameter integer FRAC = 16
    )(
        input  wire        clk,
        input  wire        rst_n,
        input  wire        enable,
        input  wire [39:0] half_q,      // half period in FCLK cycles, Q(FRAC)
        input  wire [15:0] sample_off,  // FCLK cycles after a rising edge
        output reg         clk_out,
        output reg         edge_tick,   // 1 cycle pulse on every clk_out change
        output reg         sample_tick  // 1 cycle pulse at the sample instant
    );

    localparam integer ONE = 1 << FRAC;

    wire [15:0] int_part  = half_q[FRAC+15 : FRAC];
    wire [FRAC-1:0] frac_part = half_q[FRAC-1:0];

    reg  [16:0] cnt;        // FCLK cycles left in this half period
    reg  [FRAC:0] frac_acc;
    reg  [15:0] smp_cnt;
    reg         smp_armed;

    wire [FRAC:0] frac_next = frac_acc + frac_part;
    wire          frac_carry = frac_next[FRAC];
    // cnt holds the extra cycles still to wait, so a half period of N cycles
    // loads N-1 and the boundary lands exactly N cycles after the last one.
    wire [16:0]   next_len = ({1'b0, int_part} + (frac_carry ? 17'd1 : 17'd0));
    wire [16:0]   next_cnt = next_len - 17'd1;
    wire [16:0]   idle_cnt = (int_part == 16'd0) ? 17'd0 : ({1'b0, int_part} - 17'd1);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt         <= 17'd0;
            frac_acc    <= {(FRAC+1){1'b0}};
            smp_cnt     <= 16'd0;
            smp_armed   <= 1'b0;
            clk_out     <= 1'b0;
            edge_tick   <= 1'b0;
            sample_tick <= 1'b0;
        end else begin
            edge_tick   <= 1'b0;
            sample_tick <= 1'b0;
            if (!enable) begin
                cnt       <= idle_cnt;
                frac_acc  <= {(FRAC+1){1'b0}};
                smp_cnt   <= 16'd0;
                smp_armed <= 1'b0;
                clk_out   <= 1'b0;
            end else if (cnt == 17'd0) begin
                // Half period finished: start the next one and toggle the clock.
                clk_out   <= ~clk_out;
                edge_tick <= 1'b1;
                cnt       <= next_cnt;
                frac_acc  <= frac_carry ? (frac_next - (ONE)) : frac_next;
                if (!clk_out) begin                 // 0 -> 1, a rising edge
                    if (sample_off == 16'd0) begin
                        sample_tick <= 1'b1;
                        smp_armed   <= 1'b0;
                    end else begin
                        smp_cnt   <= sample_off - 16'd1;
                        smp_armed <= 1'b1;
                    end
                end
            end else begin
                cnt <= cnt - 17'd1;
            end

            if (smp_armed) begin
                if (smp_cnt == 16'd0) begin
                    sample_tick <= 1'b1;
                    smp_armed   <= 1'b0;
                end else begin
                    smp_cnt <= smp_cnt - 16'd1;
                end
            end
        end
    end

endmodule
