`timescale 1ns/1ps
module tb_swd_stream #(
 parameter SAMPLE_RISE=1,
 parameter TCO_NS=1,
 parameter CLK_HALF_NS=5.0,
 parameter IDLE_CYCLES=0,
 parameter ACK_DELAY=0,
 parameter TURN_EXTRA=0
);
reg clk=0; always #(CLK_HALF_NS) clk=~clk;
reg rst_n=0, host_wr_en=0, host_rd_en=0;
reg [1:0] host_addr=0;
reg [31:0] host_wdata=0;
wire [31:0] host_rdata;
reg cmd_bram_en=0, rsp_bram_en=0;
reg [3:0] cmd_bram_we=0;
reg [31:0] cmd_bram_addr=0, cmd_bram_wrdata=0, rsp_bram_addr=0;
wire [31:0] cmd_bram_rddata,rsp_bram_rddata;
wire active,core_start,core_mode;
wire [255:0] core_swj_data;
wire [7:0] core_swj_count,core_req;
wire [31:0] core_wdata;
wire core_busy; wire [2:0] core_ack; wire [31:0] core_rdata;
wire core_parity_err;
reg packet_active=0, packet_cmd_en=0, packet_rsp_en=0;
reg [9:0] packet_cmd_addr=0, packet_rsp_addr=0;
wire [31:0] packet_cmd_data;
reg [3:0] packet_rsp_we=0;
reg [31:0] packet_rsp_data=0;
integer busy_left=0, ok_count=0, attempts=0, reads=0, writes=0;
reg inject_wait=0, inject_fault=0;
reg [31:0] write_sum=0;
swd_batch_engine dut(.*, .host_wstrb(4'hf), .rsp_bram_we(4'd0), .rsp_bram_wrdata(32'd0));
wire swclk, dio_o, dio_t;
tri1 swdio;
reg sample_fall=0;
reg sample_rise=0;
assign swdio = dio_t ? 1'bz : dio_o;
always @(negedge clk) sample_fall <= swdio;
always @(posedge clk) sample_rise <= swdio;
// Early samples are held between SWCLK rising phases.
integer fclk_cycle=0, last_rise_cycle=-100;
always @(posedge swclk) last_rise_cycle=fclk_cycle;
always @(posedge clk) begin
 fclk_cycle=fclk_cycle+1;
 if(rst_n && SAMPLE_RISE && core.step_tick &&
    ((core.state==4 && (core.lsm_cnt==3 || core.lsm_cnt==5 || core.lsm_cnt==7)) ||
     (core.state==6 && core.lsm_cnt>=3 && core.lsm_cnt<=67 && core.lsm_cnt[0])))
  if(fclk_cycle-last_rise_cycle<2)$fatal(1,"early sample consumed before two FCLK beats");
end
swd_core core(.next_valid(1'b0),.next_request(8'd0),.next_wdata(32'd0),.next_ready(),.result_valid(),
 .clk(clk),.rst_n(rst_n),.start(core_start),.mode(core_mode),
 .timestamp_en(1'b0),.idle_cycles(4'(IDLE_CYCLES)),.data_phase(1'b0),.clock_delay(4'd5),.delay_fast(4'd0),
 .turn_extra(2'(TURN_EXTRA)),.ack_delay(3'(ACK_DELAY)),
 .swj_data(core_swj_data),.swj_count(core_swj_count),.xfer_request(core_req),.xfer_wdata(core_wdata),
 .xfer_rdata(core_rdata),.ack(core_ack),.parity_err(core_parity_err),.busy(core_busy),.timestamp(),
 .swclk(swclk),.swdio_o(dio_o),.swdio_i(swdio),.swdio_i_fall(SAMPLE_RISE ? sample_rise : sample_fall),.swdio_t(dio_t));
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
   if(bitno<32)word[bitno]=swdio;else par=swdio;
  end
  if((^word)!=par)$fatal(1,"write parity mismatch %h %b",word,par);
  writes=writes+1;write_sum=write_sum+word;ok_count=ok_count+1;
 end else begin
  target_enable<=0;
 end
 wait(!core_busy);
 end
end
task put(input integer a,input [31:0] d);
begin @(negedge clk);cmd_bram_en=1;cmd_bram_we=15;cmd_bram_addr=a*4;cmd_bram_wrdata=d;
@(negedge clk);cmd_bram_en=0;cmd_bram_we=0;end endtask
task run_batch;
integer timeout;
begin
 @(negedge clk);host_wr_en=1;host_addr=0;host_wdata=32'h1003;
 @(negedge clk);host_wr_en=0;host_addr=1;
 timeout=0;
 while(!host_rdata[1] && timeout<200000)begin @(negedge clk);timeout=timeout+1;end
 if(timeout>=200000)$fatal(1,"batch timeout");
end endtask
task check_read(input integer n,input integer wait_en);
integer j;
begin
 ok_count=0;attempts=0;reads=0;writes=0;inject_wait=wait_en;inject_fault=0;
 put(0,(32'h04<<24)|(n<<8)|15);put(1,0);run_batch;
 if(host_rdata[2] || reads!=n || writes!=0 || attempts!=n+wait_en)
    $fatal(1,"read count n=%d reads=%d attempts=%d status=%h",n,reads,attempts,host_rdata);
 for(j=0;j<n;j=j+1)begin
   @(negedge clk);rsp_bram_en=1;rsp_bram_addr=j*4;
   @(negedge clk);
   if(rsp_bram_rddata !== (32'hA5000000+j))$fatal(1,"read payload index=%d got=%h",j,rsp_bram_rddata);
 end
 rsp_bram_en=0;
 $display("PASS repeat read %d words wait=%d",n,wait_en);
end endtask
integer j;
initial begin
 #25;rst_n=1;
 put(0,32'h01000040);put(1,32'he79e1234);put(2,32'habcdef56);put(3,0);run_batch;
 if(host_rdata[2])$fatal(1,"SWJ 64 failed");
 put(0,32'h010000ff);
 for(j=0;j<8;j=j+1)put(j+1,32'h9e3779b9^j);
 put(9,0);run_batch;
 if(host_rdata[2])$fatal(1,"SWJ 255 failed");
 $display("PASS SWJ 64/255 serial shift");
 check_read(1,0);check_read(2,1);check_read(770,0);check_read(1000,1);
 ok_count=0;attempts=0;reads=0;writes=0;write_sum=0;inject_wait=0;
 put(0,(32'h05<<24)|(1000<<8)|13);
 for(j=0;j<1000;j=j+1)put(j+1,j);
 put(1001,32'h0300000e);put(1002,0);run_batch;
 if(writes!=1000 || reads!=1 || write_sum!=499500)$fatal(1,"write mismatch %d %d %d",writes,reads,write_sum);
 $display("PASS repeat write 1000 words plus RDBUFF");
 inject_fault=1;put(0,32'h0400020f);put(1,0);run_batch;
 if(!host_rdata[2] || host_rdata[5:3]!=4)$fatal(1,"FAULT not propagated");
 $display("PASS FAULT propagation");
 inject_fault=0;check_read(2,0);
 ok_count=0;attempts=0;reads=0;writes=0;write_sum=0;
 put(0,32'h0200000d);put(1,32'h12345678);put(2,32'h0300000e);put(3,0);run_batch;
 if(writes!=1 || reads!=1 || write_sum!=32'h12345678)$fatal(1,"legacy format regression");
 $display("PASS legacy command compatibility after repeat");
 inject_parity=1;ok_count=0;attempts=0;reads=0;
 put(0,32'h0400020f);put(1,0);run_batch;
 if(!host_rdata[2] || attempts!=1)$fatal(1,"parity must stop prearmed stream, status=%h attempts=%d",host_rdata,attempts);
 $display("PASS wire parity error cancels prearmed read");
 $display("ALL SWD WIRE STREAM TESTS PASSED");$finish;
end
initial begin #100000000;$fatal(1,"global timeout");end
endmodule
