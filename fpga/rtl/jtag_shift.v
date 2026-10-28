`timescale 1ns/1ps
// All pins use FCLK clock enables. TDI/TMS change on the falling TCK edge;
// capture the preceding TDO bit at the END of its high phase, before the
// target launches the next bit. No gated fabric clock or per-bit PS MMIO.
module jtag_shift (
    input wire clk,rst_n,start,
    input wire [11:0] count,
    input wire [3:0] half_delay,
    input wire variable_tms,tms_value,exit_last,capture,
    input wire capture_rise,
    input wire [1:0] tdi_mode, // 0 zero, 1 one, 2 shift
    input wire [255:0] tms_data,tdi_data,
    input wire tdo,tdo_alternate,
    input wire tdi_sense,
    output reg tck,tms,tdi,busy,done,
    output reg [255:0] rx_data,
    output reg [63:0] tx_echo,sense_echo,rx_alternate
);
    reg [11:0] remaining;
    reg [7:0] bit_index;
    reg [3:0] divider;
    reg [255:0] ts,ds;
    reg vm,tv,el,cap,cap_rise;
    reg [1:0] dm;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            tck<=0;tms<=1;tdi<=1;busy<=0;done<=0;rx_data<=0;tx_echo<=0;sense_echo<=0;rx_alternate<=0;
            remaining<=0;bit_index<=0;divider<=0;ts<=0;ds<=0;
            vm<=0;tv<=0;el<=0;cap<=0;cap_rise<=0;dm<=0;
        end else begin
            done<=0;
            if(!busy) begin
                if(start && count!=0) begin
                    remaining<=count;bit_index<=0;divider<=half_delay;
                    vm<=variable_tms;tv<=tms_value;el<=exit_last;cap<=capture;
                    cap_rise<=capture_rise;
                    dm<=tdi_mode;ts<=tms_data;ds<=tdi_data;rx_data<=0;tx_echo<=0;sense_echo<=0;rx_alternate<=0;
                    tms<=variable_tms ? tms_data[0] : tms_value || (exit_last && count==1);
                    tdi<=tdi_mode==2 ? tdi_data[0] : tdi_mode==1;
                    tck<=0;busy<=1;
                end
            end else if(divider!=0) divider<=divider-1'b1;
            else begin
                divider<=half_delay;
                if(!tck) begin
                    tck<=1;
                    // Observe the driven bit and IOBUF pad feedback just before
                    // the rising TCK launch. Diagnostics never gate the PHY.
                    if(bit_index<64)begin tx_echo[bit_index]<=tdi;sense_echo[bit_index]<=tdi_sense;end
                    if(cap && cap_rise) rx_data[bit_index]<=tdo;
                end
                else begin
                    tck<=0;
                    if(cap && !cap_rise && bit_index<64)rx_alternate[bit_index]<=tdo_alternate;
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
