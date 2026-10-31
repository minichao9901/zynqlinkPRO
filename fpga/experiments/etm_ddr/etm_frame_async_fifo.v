`timescale 1ns/1ps
// Registered FWFT bridge for frame payload + valid-byte count + EOF metadata.
// Shared epoch reset must assert in both domains only between captures. The
// caller synchronizes reset release independently. Stopped clocks do not
// fabricate progress/EOF. Ready/valid alone never diagnoses a dropped frame:
// physical non-stallable producers must count refused frame events themselves.
module etm_frame_async_fifo #(parameter WIDTH=134,ADDR_BITS=9)(
  input wire wr_clk,input wire wr_rst,
  input wire [WIDTH-1:0] wr_data,input wire wr_valid,output wire wr_ready,
  output wire [ADDR_BITS:0] wr_level,
  input wire rd_clk,input wire rd_rst,
  output reg [WIDTH-1:0] rd_data,output reg rd_valid,input wire rd_ready
);
  (* ram_style="block" *) reg [WIDTH-1:0] memory[0:(1<<ADDR_BITS)-1];
  reg [ADDR_BITS:0] wp,wg,rp,rg;
  (* ASYNC_REG="TRUE" *) reg [ADDR_BITS:0] rg1,rg2,wg1,wg2;
  reg read_wait;
  reg [WIDTH-1:0] memory_read;
  function [ADDR_BITS:0] binary(input [ADDR_BITS:0] gray);
    integer i;begin binary[ADDR_BITS]=gray[ADDR_BITS];
      for(i=ADDR_BITS-1;i>=0;i=i-1)binary[i]=binary[i+1]^gray[i];end
  endfunction
  wire full=wg=={~rg2[ADDR_BITS:ADDR_BITS-1],rg2[ADDR_BITS-2:0]};
  wire empty=rg==wg2;
  assign wr_ready=!wr_rst && !full;
  assign wr_level=wp-binary(rg2);
  wire push=wr_valid && wr_ready;
  wire pop=rd_valid && rd_ready && !rd_rst;
  wire [ADDR_BITS:0] next_wp=wp+push,next_rp=rp+pop;
  wire fetch=!rd_rst && !rd_valid && !read_wait && !empty;
  always @(posedge wr_clk)if(push)memory[wp[ADDR_BITS-1:0]]<=wr_data;
  always @(posedge rd_clk)if(fetch)memory_read<=memory[rp[ADDR_BITS-1:0]];
  always @(posedge wr_clk or posedge wr_rst)
    if(wr_rst)begin wp<=0;wg<=0;rg1<=0;rg2<=0;end
    else begin rg1<=rg;rg2<=rg1;wp<=next_wp;wg<=(next_wp>>1)^next_wp;end
  always @(posedge rd_clk or posedge rd_rst)
    if(rd_rst)begin rp<=0;rg<=0;wg1<=0;wg2<=0;read_wait<=0;rd_valid<=0;rd_data<=0;end
    else begin
      wg1<=wg;wg2<=wg1;rp<=next_rp;rg<=(next_rp>>1)^next_rp;
      if(pop)rd_valid<=0;
      if(fetch)read_wait<=1;
      if(read_wait)begin rd_data<=memory_read;rd_valid<=1;read_wait<=0;end
    end
endmodule
