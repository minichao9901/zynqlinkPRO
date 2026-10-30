`timescale 1ns/1ps
// Small asynchronous frame FIFO. Reset both domains together between captures;
// release is synchronized separately by orbtrace_parallel. A source cannot stall
// TRACECLK: loss is sticky and invalidates a capture rather than going unnoticed.
module orbtrace_frame_fifo #(parameter ADDR_BITS=3) (
    input wire wr_clk, input wire wr_rst,
    input wire [127:0] wr_data, input wire wr_valid,
    output reg overflow,
    input wire rd_clk, input wire rd_rst,
    output wire [127:0] rd_data, output wire rd_valid,
    input wire rd_ready
);
    reg [127:0] mem [0:(1<<ADDR_BITS)-1];
    reg [ADDR_BITS:0] wp, wg, rp, rg;
    (* ASYNC_REG="TRUE" *) reg [ADDR_BITS:0] rg1,rg2,wg1,wg2;
    wire full = wg == {~rg2[ADDR_BITS:ADDR_BITS-1],rg2[ADDR_BITS-2:0]};
    wire push = wr_valid && !full;
    wire [ADDR_BITS:0] wn = wp + push;
    wire [ADDR_BITS:0] rn = rp + (rd_valid && rd_ready);
    assign rd_valid = rg != wg2;
    assign rd_data = mem[rp[ADDR_BITS-1:0]];
    always @(posedge wr_clk)
      if(push && !wr_rst)mem[wp[ADDR_BITS-1:0]]<=wr_data;
    always @(posedge wr_clk or posedge wr_rst)
      if(wr_rst) begin wp<=0;wg<=0;rg1<=0;rg2<=0;overflow<=0;end
      else begin
        rg1<=rg;rg2<=rg1;
        wp<=wn;wg<=(wn>>1)^wn;
        if(wr_valid && full)overflow<=1;
      end
    always @(posedge rd_clk or posedge rd_rst)
      if(rd_rst)begin rp<=0;rg<=0;wg1<=0;wg2<=0;end
      else begin wg1<=wg;wg2<=wg1;rp<=rn;rg<=(rn>>1)^rn;end
endmodule
