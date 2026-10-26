`timescale 1ns/1ps
// Check CMSIS-DAP results with synchronous BRAM and a posted AP pipeline.
module tb_packet_contract;
 reg clk=0; always #5 clk=~clk;
 reg rst_n=0,start=0; reg [15:0] packet_len=0;
 wire busy,done,error; wire [15:0] response_words;
 wire cmd_en; wire [9:0] cmd_addr; reg [31:0] cmd_mem[0:1023];
 reg [31:0] cmd_data;
 always @(posedge clk) if(cmd_en) cmd_data <= cmd_mem[cmd_addr];
 wire rsp_en; wire [3:0] rsp_we; wire [9:0] rsp_addr; wire [31:0] rsp_data;
 reg [31:0] rsp_mem[0:1023];
 reg core_busy=0; reg [2:0] core_ack=0;
 reg core_parity_err=0; reg [31:0] core_rdata=0;
 wire core_start,core_mode; wire [7:0] core_req; wire [31:0] core_wdata;
 integer i,b,cycles=0,accepted=0,attempts=0,rdbuffs=0,waits=0;
 integer fault_after=-1; reg parity_final=0;
 integer wait_at=-1,wait_injected=0,wall_cycles=0,started;
 reg [31:0] posted;
 reg [31:0] writes[0:1023];
 dap_transfer_block_engine dut(.*, .state_dbg(),
   .core_result_valid(1'b0),.core_next_ready(1'b0),
   .core_next_valid(),.core_next_request(),.core_next_wdata());
 always @(posedge clk) begin
   wall_cycles <= wall_cycles+1;
   if(rsp_en) for(b=0;b<4;b=b+1)
     if(rsp_we[b]) rsp_mem[rsp_addr][b*8 +: 8] <= rsp_data[b*8 +: 8];
   if(core_start && !core_busy) begin
     core_busy <= 1; cycles <= 4; attempts <= attempts+1;
     core_parity_err <= 0;
     if(accepted==wait_at && !wait_injected) begin
       core_ack <= 2;wait_injected <= 1;
     end else if(waits>0) begin
       core_ack <= 2; waits <= waits-1;
     end else if(fault_after>=0 && accepted>=fault_after) core_ack<=4;
     else begin
       core_ack<=1;
       if(core_req==8'h0e) begin
         rdbuffs<=rdbuffs+1; core_rdata<=posted;
         core_parity_err<=parity_final;
       end else begin
         if(core_req[1]) begin
           core_rdata<=posted; posted<=32'ha5000000+accepted;
         end else writes[accepted]<=core_wdata;
         accepted<=accepted+1;
       end
     end
   end else if(core_busy) begin
     if(cycles==0) core_busy<=0;
     else cycles<=cycles-1;
   end
 end
 task prepare(input integer n,input bit reading);
   begin
     accepted=0; attempts=0; rdbuffs=0; waits=0; fault_after=-1;
     wait_at=-1;wait_injected=0;
     posted=32'hdeadbeef; parity_final=0;
     cmd_mem[0]=((reading?32'h0f:32'h0d)<<24)|(n<<8)|6;
     packet_len=reading?4:4+4*n;
     for(i=0;i<n;i=i+1)cmd_mem[i+1]=32'h13570000+i;
   end
 endtask
 task run;
   begin
     @(negedge clk);started=wall_cycles;start=1;@(negedge clk);start=0;
     wait(done);repeat(3)@(negedge clk);
     if(!done || busy)$fatal(1,"done is not sticky");
     $display("CYCLES count=%0d read=%0d cycles=%0d",cmd_mem[0][23:8],cmd_mem[0][25],wall_cycles-started);
   end
 endtask
 task header(input integer n,input integer status,input integer words);
   begin
     if(rsp_mem[0]!==((status<<16)|n) || response_words!==words)
       $fatal(1,"header=%h words=%d expected count=%d status=%d words=%d",
              rsp_mem[0],response_words,n,status,words);
   end
 endtask
 initial begin
   #1;rst_n=0;#20;rst_n=1;
   for(i=0;i<1024;i=i+1)rsp_mem[i]=0;
   prepare(1,0);run;header(1,1,1);
   if(writes[0]!==32'h13570000 || rdbuffs!=1)$fatal(1,"write completion");
   prepare(3,1);waits=2;run;header(3,1,4);
   for(i=0;i<3;i=i+1)if(rsp_mem[i+1]!==32'ha5000000+i)$fatal(1,"posted map %d",i);
   if(rdbuffs!=1 || attempts!=6)$fatal(1,"posted/retry sequence");
   prepare(32,0);wait_at=5;run;header(32,1,1);
   if(!wait_injected || attempts!=34)$fatal(1,"write WAIT/retry not exercised");
   for(i=0;i<32;i=i+1)if(writes[i]!==32'h13570000+i)$fatal(1,"prefetched retry data %d",i);
   prepare(1022,0);run;header(1022,1,1);
   for(i=0;i<1022;i=i+1)if(writes[i]!==32'h13570000+i)$fatal(1,"write data %d",i);
   prepare(1023,1);run;header(1023,1,1024);
   for(i=0;i<1023;i=i+1)if(rsp_mem[i+1]!==32'ha5000000+i)$fatal(1,"read data %d",i);
   prepare(4,1);fault_after=2;run;header(1,4,2);
   if(!error)$fatal(1,"FAULT not signaled");
   prepare(3,0);fault_after=2;run;header(2,4,1);
   prepare(3,0);parity_final=1;run;header(3,8,1);
   if(!error)$fatal(1,"RDBUFF parity ignored");
   prepare(1,0);waits=100;run;header(0,2,1);
   prepare(3,0);packet_len=8;run;header(0,7,1);
   if(attempts!=0)$fatal(1,"truncated write executed");
   $display("PASS packet status/count, posted reads, RDBUFF write drain, WAIT, partial FAULT, parity, 1023-word boundary");
   $finish;
 end
 initial begin #20000000;$fatal(1,"packet engine timeout");end
endmodule
