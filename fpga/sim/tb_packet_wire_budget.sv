`timescale 1ns/1ps
// Serial-frame budget with the real packet FSM and SWD core; no USB/PS/DMA.
module tb_packet_wire_budget #(
 parameter integer CLK_HALF_NS=5, IDLE_CYCLES=1, TCO_NS=16
);
reg clk=0;always #(CLK_HALF_NS) clk=~clk;
reg rst_n=0,start=0;reg [15:0] packet_len=0;
wire busy,done,error;wire [15:0] response_words;
wire cmd_en;wire [9:0] cmd_addr;reg [31:0] cmd_mem[0:1023],cmd_data;
always @(posedge clk)if(cmd_en)cmd_data<=cmd_mem[cmd_addr];
wire rsp_en;wire [3:0] rsp_we;wire [9:0] rsp_addr;wire [31:0] rsp_data;
wire core_start,core_mode,core_busy,core_parity_err;
wire [7:0] core_req;wire [31:0] core_wdata,core_rdata;wire [2:0] core_ack;
wire [255:0] core_swj_data=0;wire [7:0] core_swj_count=0;
wire swclk,dio_o,dio_t;tri1 swdio;
reg sample_fall=0;always @(negedge clk)sample_fall<=swdio;
assign swdio=dio_t?1'bz:dio_o;
dap_transfer_block_engine dut(.*, .state_dbg());
swd_core core(.clk(clk),.rst_n(rst_n),.start(core_start),.mode(core_mode),
 .timestamp_en(1'b0),.idle_cycles(4'(IDLE_CYCLES)),.data_phase(1'b0),
 .clock_delay(4'd0),.delay_fast(4'd0),.turn_extra(2'd0),.ack_delay(3'd0),
 .swj_data(core_swj_data),.swj_count(core_swj_count),.xfer_request(core_req),.xfer_wdata(core_wdata),
 .xfer_rdata(core_rdata),.ack(core_ack),.parity_err(core_parity_err),.busy(core_busy),.timestamp(),
 .swclk(swclk),.swdio_o(dio_o),.swdio_i(swdio),.swdio_i_fall(sample_fall),.swdio_t(dio_t));
integer attempts=0,ok_count=0,reads=0,writes=0;reg inject_wait=0,inject_fault=0;
reg [31:0] write_sum=0;
// A host-driven parity bit must remain stable for the rest of its high phase,
// even after busy deasserts. Gating the target on busy would hide this violation.
reg hold_parity=0,held_parity=0;
always @(negedge swclk) hold_parity=0;
always @(posedge clk) begin
 #0.001;
 if(hold_parity && swclk && !dio_t && dio_o!==held_parity)
   $fatal(1,"host changed final write parity while SWCLK remained high");
end
integer cycles=0,wire_rises=0,launches=0;
always @(posedge clk)begin cycles<=cycles+1;if(core_start&&!core_busy)launches<=launches+1;end
always @(posedge swclk)wire_rises=wire_rises+1;
reg target_enable=0,target_data=1;
reg inject_parity=0;
// Delayed NBAs preserve every launch even when TCO exceeds a bit period.
// A delayed continuous assignment would incorrectly filter short data bits.
reg delayed_enable=0,delayed_data=1;
always @(target_enable or target_data) begin
 delayed_enable <= #(TCO_NS) target_enable;
 delayed_data <= #(TCO_NS) target_data;
end
assign swdio = delayed_enable ? delayed_data : 1'bz;
integer bitno;
reg [7:0] hdr;
reg [2:0] tack;
reg [31:0] word;
reg par;
initial forever begin
 @(posedge core_busy);
 if(!core_mode)begin
  for(bitno=0;bitno<core_swj_count;bitno=bitno+1)begin
   @(posedge swclk);
   if(swdio!==core_swj_data[bitno])$fatal(1,"SWJ shift mismatch at bit %d",bitno);
  end
  wait(!core_busy);
 end else begin
 tack=inject_fault ? 4 : ((inject_wait && attempts==0) ? 2 : 1);
 attempts=attempts+1;
 for(bitno=0;bitno<8;bitno=bitno+1)begin @(posedge swclk);hdr[bitno]=swdio;end
 if(hdr[0]!=1 || hdr[6]!=0 || hdr[7]!=1 || (^hdr[4:1])!=hdr[5])$fatal(1,"bad wire request %h",hdr);
 @(negedge swclk);@(posedge swclk); // request turnaround, launch ACK[0]
 target_enable<=1;target_data<=tack[0];
 for(bitno=0;bitno<3;bitno=bitno+1)begin
  @(posedge swclk);
  if(bitno<2)target_data<=tack[bitno+1];
 end
 if(tack==1 && hdr[2])begin
  word=32'hA5000000+ok_count;
  target_data<=word[0];
  for(bitno=0;bitno<33;bitno=bitno+1)begin
   @(posedge swclk);
   if(bitno<31)target_data<=word[bitno+1];
   else if(bitno==31)target_data<=(^word)^inject_parity;
   else target_enable<=0;
  end
  reads=reads+1;ok_count=ok_count+1;
  @(posedge swclk); // target-to-host turnaround
 end else if(tack==1)begin
  target_enable<=0;@(posedge swclk); // write turnaround
  for(bitno=0;bitno<33;bitno=bitno+1)begin
   @(posedge swclk);
   if(bitno<32)word[bitno]=swdio;
   else begin par=swdio;held_parity=swdio;hold_parity=1;end
  end
  if((^word)!=par)$fatal(1,"write parity mismatch %h %b",word,par);
  writes=writes+1;write_sum=write_sum+word;ok_count=ok_count+1;
 end else begin
  target_enable<=0;
 end
 wait(!core_busy);
 end
end

task run(input integer n,input bit reading);
 integer j,c0,r0,l0;
 begin
  @(negedge clk);cmd_mem[0]=((reading?32'h0f:32'h0d)<<24)|(n<<8)|6;
  for(j=0;j<n;j=j+1)cmd_mem[j+1]=32'h13570000+j;
  packet_len=reading?4:4+4*n;
  c0=cycles;r0=wire_rises;l0=launches;start=1;
  @(negedge clk);start=0;
  wait(done);@(negedge clk);
  if(error || core_ack!=1)$fatal(1,"packet/core failure ack=%h parity=%b",core_ack,core_parity_err);
  if(launches-l0!=n+1)$fatal(1,"unexpected retry/launch count");
  $display("BUDGET words=%0d read=%0d idle=%0d half_ns=%0d cycles=%0d rises=%0d launches=%0d",n,reading,IDLE_CYCLES,CLK_HALF_NS,cycles-c0,wire_rises-r0,launches-l0);
 end
endtask
initial begin
 #25;rst_n=1;
 run(256,0);run(256,1);run(1022,0);run(1022,1);
 $display("PASS real packet/core serial budget");$finish;
end
initial begin #10000000;$fatal(1,"wire budget timeout");end
endmodule
