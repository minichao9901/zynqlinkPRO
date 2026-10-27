`timescale 1ns/1ps
// All pins use FCLK clock enables. TDI/TMS change on the falling TCK edge;
// capture the preceding TDO bit at the END of its high phase, before the
// target launches the next bit. No gated fabric clock or per-bit PS MMIO.
//
// The half period comes from swj_clk_gen, programmed as a Q16 number of FCLK
// cycles, so the requested clock is produced exactly instead of being limited
// to integer FCLK divisions. `mult` stretches every half period for segments
// that need a slower clock (TAP/IR navigation, or a rising-edge capture).
module jtag_shift (
    input wire clk,rst_n,start,
    input wire [11:0] count,
    input wire [39:0] half_q,   // base half period, Q16 FCLK cycles
    input wire [1:0] mult,      // 0: x1, 1: x2, 3: x4
    input wire variable_tms,tms_value,exit_last,capture,
    input wire capture_rise,
    input wire [1:0] tdi_mode, // 0 zero, 1 one, 2 shift
    input wire [255:0] tms_data,tdi_data,
    input wire tdo,
    output reg tck,tms,tdi,busy,done,
    output reg [255:0] rx_data
);
    reg [11:0] remaining;
    reg [7:0] bit_index;
    reg [255:0] ts,ds;
    reg vm,tv,el,cap,cap_rise;
    reg [1:0] dm;

    wire [39:0] eff_half_q = (mult == 2'd0) ? half_q :
                             (mult == 2'd1) ? (half_q << 1) : (half_q << 2);
    wire tick;

    // Start the generator on the same cycle the segment starts, not the cycle
    // after: enable is registered inside the generator, and the consumer sees
    // edge_tick one cycle later, so waiting for busy would add two cycles and
    // compress the final half period of every segment.
    wire gen_en = busy || (start && count != 0);

    swj_clk_gen u_clk_gen(.clk(clk),.rst_n(rst_n),.enable(gen_en),
        .half_q(eff_half_q),.sample_off(16'd0),
        .clk_out(),.edge_tick(tick),.sample_tick());

    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            tck<=0;tms<=1;tdi<=1;busy<=0;done<=0;rx_data<=0;
            remaining<=0;bit_index<=0;ts<=0;ds<=0;
            vm<=0;tv<=0;el<=0;cap<=0;cap_rise<=0;dm<=0;
        end else begin
            done<=0;
            if(!busy) begin
                if(start && count!=0) begin
                    remaining<=count;bit_index<=0;
                    vm<=variable_tms;tv<=tms_value;el<=exit_last;cap<=capture;
                    cap_rise<=capture_rise;
                    dm<=tdi_mode;ts<=tms_data;ds<=tdi_data;rx_data<=0;
                    tms<=variable_tms ? tms_data[0] : tms_value || (exit_last && count==1);
                    tdi<=tdi_mode==2 ? tdi_data[0] : tdi_mode==1;
                    tck<=0;busy<=1;
                end
            end else if(tick) begin
                if(!tck) begin
                    tck<=1;
                    if(cap && cap_rise) rx_data[bit_index]<=tdo;
                end
                else begin
                    tck<=0;
                    if(cap && !cap_rise) rx_data[bit_index]<=tdo;
                    if(remaining==1) begin busy<=0;done<=1;end
                    else begin
                        remaining<=remaining-1'b1;bit_index<=bit_index+1'b1;
                        ts<=ts>>1;ds<=ds>>1;
                        tms<=vm ? ts[1] : tv || (el && remaining==2);
                        tdi<=dm==2 ? ds[1] : dm==1;
                    end
                end
            end
        end
    end
endmodule
