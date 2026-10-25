`timescale 1ns/1ps
// Integrate real AXI decode, shared BRAM mux and packet/core mux. Only the
// serial target response is mocked; controller and both engines are unchanged.
module tb_packet_axi;
 reg clk=0;always #5 clk=~clk;
 reg rst_n=0;
 reg [6:0] awaddr=0,araddr=0;
 reg awvalid=0,wvalid=0,arvalid=0;
 reg [31:0] wdata=0;wire awready,wready,bvalid,arready,rvalid;
 wire [31:0] rdata;
 reg cmd_en=0;reg [3:0] cmd_we=0;
 reg [31:0] cmd_addr=0,cmd_data=0;
 reg rsp_en=0;reg [31:0] rsp_addr=0;wire [31:0] rsp_data;
 wire swclk;tri swdio;
 swd_controller dut(.clk(clk),.rst_n(rst_n),
   .s_axi_awaddr(awaddr),.s_axi_awprot(3'd0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
   .s_axi_wdata(wdata),.s_axi_wstrb(4'hf),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
   .s_axi_bvalid(bvalid),.s_axi_bready(1'b1),
   .s_axi_araddr(araddr),.s_axi_arprot(3'd0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
   .s_axi_rdata(rdata),.s_axi_rvalid(rvalid),.s_axi_rready(1'b1),
   .cmd_bram_clk(clk),.cmd_bram_rst(1'b0),.cmd_bram_en(cmd_en),.cmd_bram_we(cmd_we),
   .cmd_bram_addr(cmd_addr),.cmd_bram_wrdata(cmd_data),
   .rsp_bram_clk(clk),.rsp_bram_rst(1'b0),.rsp_bram_en(rsp_en),.rsp_bram_we(4'd0),
   .rsp_bram_addr(rsp_addr),.rsp_bram_wrdata(32'd0),.rsp_bram_rddata(rsp_data),
   .swclk(swclk),.swdio(swdio));
 reg mock_busy=0;reg [31:0] mock_data=0;integer remaining=0,accepted=0;
 initial begin
   force dut.core_busy=mock_busy;force dut.core_ack=3'd1;
   force dut.core_parity_err=1'b0;force dut.core_rdata=mock_data;
 end
 always @(posedge clk)begin
   if(dut.core_start_sel && !mock_busy)begin
     if(!dut.packet_active)$fatal(1,"packet register alias started legacy core");
     mock_busy<=1;remaining<=3;mock_data<=32'ha5000000+accepted;
     if(!dut.core_req_sel[1] && dut.core_wdata_sel!==32'h12340000+accepted)
       $fatal(1,"BRAM data/mux mismatch %h",dut.core_wdata_sel);
     accepted<=accepted+1;
   end else if(mock_busy)begin
     if(remaining==0)mock_busy<=0;else remaining<=remaining-1;
   end
 end
 task wr(input [6:0] addr,input [31:0] data);
   begin
     @(negedge clk);awaddr=addr;wdata=data;awvalid=1;wvalid=1;
     @(posedge clk);if(!awready||!wready)$fatal(1,"AXI stalled unexpectedly");
     @(negedge clk);awvalid=0;wvalid=0;
     wait(bvalid);repeat(2)@(negedge clk);
   end
 endtask
 task rd(input [6:0] addr,output [31:0] data);
   begin
     @(negedge clk);araddr=addr;arvalid=1;
     @(posedge clk);if(!arready)$fatal(1,"AXI read stalled");
     @(negedge clk);arvalid=0;
     wait(rvalid);data=rdata;@(negedge clk);
   end
 endtask
 task put(input integer addr,input [31:0] data);
   begin
     @(negedge clk);cmd_en=1;cmd_we=15;cmd_addr=addr*4;cmd_data=data;
     @(negedge clk);cmd_en=0;cmd_we=0;
   end
 endtask
 reg [31:0] status,old_cfg,check_cfg;
 integer n;
 initial begin
   #1;rst_n=0;#20;rst_n=1;
   rd(8,old_cfg);wr(7'h44,16);rd(7'h44,status);
   if(status!=16)$fatal(1,"PACKET_LEN alias %h",status);
   rd(8,check_cfg);if(old_cfg!==check_cfg)$fatal(1,"PACKET_LEN altered CFG");
   put(0,32'h0d000306);
   for(n=0;n<3;n=n+1)put(n+1,32'h12340000+n);
   wr(7'h40,1);status=1;
   while(!status[1])rd(7'h48,status);
   if(status[2:0]!=2 || status[31:16]!=1 || accepted!=4)
     $fatal(1,"status=%h core calls=%d",status,accepted);
   @(negedge clk);rsp_en=1;rsp_addr=0;@(negedge clk);
   if(rsp_data!==32'h00010003)$fatal(1,"response BRAM %h",rsp_data);
   $display("PASS AXI 0x40/44/48 decode, no legacy alias, shared synchronous BRAM and core mux");
   $finish;
 end
 initial begin #1000000;$fatal(1,"AXI packet timeout");end
endmodule

module IOBUF(input I,T,inout IO,output O);
 assign IO=T?1'bz:I;assign O=IO;
endmodule
module IDDR #(parameter DDR_CLK_EDGE="OPPOSITE_EDGE",INIT_Q1=0,INIT_Q2=0,SRTYPE="SYNC")
 (input C,CE,D,R,S,output reg Q1,Q2);
 always @(posedge C)if(CE)Q1<=D;
 always @(negedge C)if(CE)Q2<=D;
endmodule
