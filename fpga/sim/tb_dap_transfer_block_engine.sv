`timescale 1ns/1ps
module tb_dap_transfer_block_engine;
 reg clk=0; always #5 clk=~clk;
 reg rst_n=0,start=0; reg [15:0] packet_len=0;
 wire busy,done,error; wire [15:0] response_words;
 wire cmd_en; wire [9:0] cmd_addr; reg [31:0] cmd_mem[0:1023];
 wire [31:0] cmd_data=cmd_mem[cmd_addr];
 wire rsp_en; wire [3:0] rsp_we; wire [9:0] rsp_addr; wire [31:0] rsp_data;
 reg [31:0] rsp_mem[0:1023];
 reg core_busy=0; reg [2:0] core_ack=0; reg core_parity_err=0; reg [31:0] core_rdata=0;
 wire core_start; wire [7:0] core_req; wire [31:0] core_wdata;
 integer i;
 dap_transfer_block_engine dut(.*, .core_mode(), .state_dbg(),
   .core_result_valid(1'b0),.core_next_ready(1'b0),
   .core_next_valid(),.core_next_request(),.core_next_wdata());
 always @(posedge clk) begin
   if(rsp_en) begin
     for(i=0;i<4;i=i+1) if(rsp_we[i]) rsp_mem[rsp_addr][i*8 +: 8] <= rsp_data[i*8 +: 8];
   end
   if(core_start && !core_busy) begin
     core_busy<=1; core_ack<=3'b001;
     if(core_req[1]) core_rdata<=32'hA5000000+core_req;
   end else if(core_busy) core_busy<=0;
 end
 task run; begin
   @(negedge clk);start=1;@(negedge clk);start=0;
   wait(done);@(negedge clk);
 end endtask
 initial begin
   rst_n=1;
   for(i=0;i<1024;i=i+1)begin cmd_mem[i]=0; rsp_mem[i]=0;end
   // DAP TransferBlock AP read, 2 words: 06 02 00 0f.
   cmd_mem[0]=32'h0f000206; packet_len=4; run;
   if(error || rsp_mem[0][15:0]!==2 || rsp_mem[0][23:16]!==1)
     $fatal(1,"read header %h error=%b",rsp_mem[0],error);
   $display("PASS packet AP read response=%h %h",rsp_mem[0],rsp_mem[1]);
   // DAP TransferBlock AP write, one payload word at cmd word1.
   cmd_mem[0]=32'h0d000106; cmd_mem[1]=32'h12345678; packet_len=8; run;
   if(error || rsp_mem[0][15:0]!==1 || rsp_mem[0][23:16]!==1)
     $fatal(1,"write header %h error=%b",rsp_mem[0],error);
   $display("PASS packet AP write response=%h",rsp_mem[0]);
   $display("ALL DAP PACKET ENGINE TESTS PASSED"); $finish;
 end
 initial begin #1000000; $fatal(1,"timeout"); end
endmodule
