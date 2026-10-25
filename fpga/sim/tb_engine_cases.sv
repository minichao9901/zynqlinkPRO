module tb_engine_cases;
 reg clk=0; always #5 clk=~clk;
 reg rst_n=0,start=0; reg [15:0] packet_len=0;
 wire busy,done,error; wire [15:0] response_words; wire [4:0] state_dbg;
 wire cmd_en; wire [9:0] cmd_addr; reg [31:0] cmd_mem[0:1023];
 reg [31:0] cmd_data_r; always @(posedge clk) cmd_data_r <= cmd_mem[cmd_addr];
 wire [31:0] cmd_data=cmd_data_r;
 wire rsp_en; wire [3:0] rsp_we; wire [9:0] rsp_addr; wire [31:0] rsp_data;
 reg [31:0] rsp_mem[0:1200];
 reg core_busy=0; reg [2:0] core_ack=0; reg core_parity_err=0; reg [31:0] core_rdata=0;
 wire core_start; wire [7:0] core_req; wire [31:0] core_wdata; wire core_mode;
 integer i; integer wait_left=0; integer fault_mode=0; integer stuck_mode=0;
 integer wr_idx=0; reg [31:0] wr_cap[0:1023];
 dap_transfer_block_engine dut(.clk(clk),.rst_n(rst_n),.start(start),.packet_len(packet_len),
   .busy(busy),.done(done),.error(error),.response_words(response_words),.state_dbg(state_dbg),
   .cmd_en(cmd_en),.cmd_addr(cmd_addr),.cmd_data(cmd_data),
   .rsp_en(rsp_en),.rsp_we(rsp_we),.rsp_addr(rsp_addr),.rsp_data(rsp_data),
   .core_start(core_start),.core_mode(core_mode),.core_req(core_req),.core_wdata(core_wdata),
   .core_busy(core_busy),.core_ack(core_ack),.core_parity_err(core_parity_err),.core_rdata(core_rdata));
 always @(posedge clk) begin
   if(rsp_en) for(i=0;i<4;i=i+1) if(rsp_we[i]) rsp_mem[rsp_addr][i*8 +: 8] <= rsp_data[i*8 +: 8];
   if(core_start && !stuck_mode) begin
     core_busy <= 1;
     core_rdata <= 32'h5A000000 + {24'd0, core_req};
     if (core_req[1]==0 && fault_mode==0 && wait_left==0) begin wr_cap[wr_idx] <= core_wdata; wr_idx <= wr_idx+1; end
     if (fault_mode) core_ack <= 3'b100;
     else if (wait_left > 0) begin core_ack <= 3'b010; wait_left <= wait_left-1; end
     else core_ack <= 3'b001;
   end else if(core_busy) core_busy <= 0;
 end
 task run; begin @(negedge clk);start=1;@(negedge clk);start=0; wait(done); @(negedge clk); end endtask
 initial begin
   rst_n=1;
   for(i=0;i<1200;i=i+1)begin cmd_mem[i]=0; rsp_mem[i]=0; end
   // 1) read 1
   wait_left=0; fault_mode=0; wr_idx=0;
   cmd_mem[0]=32'h0f000106; packet_len=4; run;
   $display("read1: err=%b words=%0d hdr=%h d1=%h",error,response_words,rsp_mem[0],rsp_mem[1]);
   // 2) read 4 with 2 wait each
   wait_left=8;
   cmd_mem[0]=32'h0f000406; packet_len=4; run;
   $display("read4w: err=%b words=%0d hdr=%h d1=%h d4=%h",error,response_words,rsp_mem[0],rsp_mem[1],rsp_mem[4]);
   // 3) write 3 words
   wait_left=6; wr_idx=0;
   cmd_mem[0]=32'h0d000306; cmd_mem[1]=32'h11111111; cmd_mem[2]=32'h22222222; cmd_mem[3]=32'h33333333; packet_len=16; run;
   $display("write3: err=%b words=%0d hdr=%h w0=%h w1=%h w2=%h",error,response_words,rsp_mem[0],wr_cap[0],wr_cap[1],wr_cap[2]);
   // 4) FAULT
   fault_mode=1;
   cmd_mem[0]=32'h0f000206; packet_len=4; run;
   $display("fault: err=%b words=%0d hdr=%h state=%0d",error,response_words,rsp_mem[0],state_dbg);
   // 5) stuck core -> watchdog
   fault_mode=0; stuck_mode=1;
   cmd_mem[0]=32'h0f000106; packet_len=4; run;
   $display("stuck: err=%b words=%0d hdr=%h state=%0d",error,response_words,rsp_mem[0],state_dbg);
   $finish;
 end
 initial begin #4000000; $display("TIMEOUT state=%0d",state_dbg); $finish; end
endmodule

