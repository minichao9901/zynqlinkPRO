`timescale 1ns/1ps
module tb_batch_dma;
reg clk=0; always #5 clk=~clk;
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
reg core_busy=0; reg [2:0] core_ack=1; reg [31:0] core_rdata=0;
reg core_parity_err=0;
integer busy_left=0, ok_count=0, attempts=0, reads=0, writes=0;
reg inject_wait=0, inject_fault=0;
reg [31:0] write_sum=0;
swd_batch_engine dut(.*, .host_wstrb(4'hf), .rsp_bram_we(4'd0), .rsp_bram_wrdata(32'd0));
always @(posedge clk) begin
 if (core_start && !core_busy) begin
   attempts <= attempts+1; core_busy<=1;busy_left<=3;
   if (inject_fault) core_ack<=4;
   else if (inject_wait && attempts==0) core_ack<=2;
   else begin
     core_ack<=1;core_rdata<=32'hA5000000+ok_count;ok_count<=ok_count+1;
     if(core_req[1]) reads<=reads+1;
     else begin writes<=writes+1;write_sum<=write_sum+core_wdata;end
   end
 end else if(core_busy) begin
   busy_left<=busy_left-1;
   if(busy_left==1)core_busy<=0;
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
 $display("ALL BATCH DMA TESTS PASSED");$finish;
end
initial begin #100000000;$fatal(1,"global timeout");end
endmodule
