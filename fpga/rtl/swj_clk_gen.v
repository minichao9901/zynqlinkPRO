`timescale 1ns/1ps
// FCLK-domain event generator. No fabric clock and no registered-strobe delay.
// A Q16 half period schedules protocol steps; a separate event schedules input
// capture within that half period. The consumer decides whether a step raises,
// lowers or holds SWCLK (ACK holds/turnaround are protocol decisions).
//
// Integer Q16 values reproduce main's delay+1 counter exactly, including the
// first step after enable. Fractional values alternate floor/ceil intervals;
// only their average is exact. Disable clears both interval and fraction phase.
// Sample-at-end preserves main's capture slot; an earlier offset is available
// for independently tested consumers, not enabled by the current SWD wrapper.
module swj_clk_gen (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        enable,
    input  wire [31:0] half_q,
    input  wire        sample_at_end,
    input  wire [15:0] sample_offset,
    output wire        edge_tick,
    output wire        sample_tick
);
    wire [31:0] period_q = half_q < 32'd65536 ? 32'd65536 : half_q;
    reg  [15:0] phase_count;
    reg  [15:0] fraction;
    wire [16:0] fraction_next = {1'b0,fraction} + {1'b0,period_q[15:0]};
    wire [16:0] interval_cycles = {1'b0,period_q[31:16]} + fraction_next[16];
    wire [15:0] last_count = interval_cycles - 17'd1;

    // Combinational strobes are consumed at this FCLK edge, never one edge
    // later. Registering edge_tick would change the highest-speed waveform.
    assign edge_tick = enable && phase_count == last_count;
    assign sample_tick = enable &&
        (sample_at_end ? edge_tick : phase_count == sample_offset);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            phase_count <= 0;
            fraction <= 0;
        end else if (!enable) begin
            phase_count <= 0;
            fraction <= 0;
        end else if (edge_tick) begin
            phase_count <= 0;
            fraction <= fraction_next[15:0];
        end else begin
            phase_count <= phase_count + 1'b1;
        end
    end
endmodule
