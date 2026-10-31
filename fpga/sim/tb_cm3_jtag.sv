`timescale 1ns/1ps
// Real AXI controller, physical pad mux, sampler, packet BRAM and RTT engine.
// The external debug port is the encrypted Cortex-M3 DesignStart RTL.
module tb_cm3_jtag #(parameter integer ENABLE_DIAGNOSTICS=0);
 real clk_ns=8.333333;
 integer cfg_idle=1;
 reg clk=0;
 real target_clk_ns=8.333333;
 reg target_clk=0;
 initial begin
  if($value$plusargs("clk_ns=%f",target_clk_ns))begin end
  if($value$plusargs("target_clk_ns=%f",target_clk_ns))begin end
  forever #(target_clk_ns/2.0) target_clk=~target_clk;
 end
 initial begin if($value$plusargs("clk_ns=%f",clk_ns))begin end if($value$plusargs("idle=%d",cfg_idle))begin end forever #(clk_ns/2.0) clk=~clk; end
 reg rst_n=0;reg [7:0] aw=0,ar=0;reg av=0,wv=0,rv=0;
 reg [31:0] wd=0;wire awr,wr,bv,arr,rdv;wire [31:0] rd;
 reg pe=0;reg [3:0] pw=0;reg [31:0] pa=0,pd=0;wire [31:0] pq;
 wire tck;tri tms;tri [3:0] pads;wire tdo,target_tdo;reg late_tdo=1;
 wire late_mode=$test$plusargs("late");
 wire q1_mode=$test$plusargs("q1");
 real tdo_ns=16;
 initial begin if($value$plusargs("tdo_ns=%f",tdo_ns))begin end end
 always @(target_tdo) late_tdo<=#(tdo_ns) target_tdo;
 assign tdo=(late_mode || $test$plusargs("delay_tdo")) ? late_tdo : target_tdo;
 reg [3:0] aux_out=4'hc,aux_tri=4'hb;
 assign pads[1]=tdo;
 swd_controller #(.ENABLE_DIAGNOSTICS(ENABLE_DIAGNOSTICS)) dut(.clk(clk),.rst_n(rst_n),
  .s_axi_awaddr(aw),.s_axi_awprot(3'd0),.s_axi_awvalid(av),.s_axi_awready(awr),
  .s_axi_wdata(wd),.s_axi_wstrb(4'hf),.s_axi_wvalid(wv),.s_axi_wready(wr),.s_axi_bvalid(bv),.s_axi_bready(1'b1),
  .s_axi_araddr(ar),.s_axi_arprot(3'd0),.s_axi_arvalid(rv),.s_axi_arready(arr),
  .s_axi_rdata(rd),.s_axi_rvalid(rdv),.s_axi_rready(1'b1),
  .cmd_bram_clk(clk),.cmd_bram_rst(1'b0),.cmd_bram_en(1'b0),.cmd_bram_we(4'd0),.cmd_bram_addr(32'd0),.cmd_bram_wrdata(32'd0),
  .rsp_bram_clk(clk),.rsp_bram_rst(1'b0),.rsp_bram_en(1'b0),.rsp_bram_we(4'd0),.rsp_bram_addr(32'd0),.rsp_bram_wrdata(32'd0),
  .pkt_bram_clk(clk),.pkt_bram_rst(1'b0),.pkt_bram_en(pe),.pkt_bram_we(pw),.pkt_bram_addr(pa),.pkt_bram_wrdata(pd),.pkt_bram_rddata(pq),
  .swclk(tck),.swdio(tms),.gpio_aux(pads),.gpio_out(aux_out),.gpio_tri(aux_tri),.gpio_in());
 wire cm3_tdo,cm3_ntdoen,cm3_swdo,cm3_swdoen,cm3_jtagnsw;
 wire bypass_tdo;
 wire bypass_mode=$test$plusargs("bypass");
 jtag_dp_model #(.IRLEN(5),.DUMMY(1)) boundary_tap(
  .rst_n(rst_n),.tck(tck),.tms(tms),.tdi(pads[0]),.tdo(bypass_tdo));
 wire [31:0] cm3_sysout; wire [15:0] cm3_writes;
 assign target_tdo = cm3_ntdoen ? 1'bz : cm3_tdo;
 cm3_target #(.WORDS(8192),.ADDR_BITS(13)) target(
  .clk(target_clk),.rst_n(rst_n),.dbg_rst_n(rst_n),.trst_n(rst_n),
  .swclktck(tck),.swditms(tms),.tdi(bypass_mode ? bypass_tdo : pads[0]),
  .tdo(cm3_tdo),.ntdoen(cm3_ntdoen),.swdo(cm3_swdo),.swdoen(cm3_swdoen),.jtag_nsw(cm3_jtagnsw),
  .sys_dout(cm3_sysout),.sys_writes(cm3_writes));
 always @(posedge clk) if($test$plusargs("coretrace") && dut.core_result_valid)
   $display("CORE t=%0t req=%h ack=%h wd=%h rd=%h",$time,dut.core_req_sel,dut.core_ack,dut.core_wdata_sel,dut.core_rdata);

 task write_reg(input [7:0] a,input [31:0] d);
  @(negedge clk);aw=a;wd=d;av=1;wv=1;
  @(posedge clk);if(!awr || !wr)$fatal(1,"AXI write stalled");
  @(negedge clk);av=0;wv=0;wait(bv);repeat(2)@(negedge clk);
 endtask
 task read_reg(input [7:0] a,output [31:0] d);
  @(negedge clk);ar=a;rv=1;@(posedge clk);if(!arr)$fatal(1,"AXI read stalled");
  @(negedge clk);rv=0;wait(rdv);d=rd;@(negedge clk);
 endtask
 task put(input integer a,input [31:0] d);
  @(negedge clk);pe=1;pw=15;pa=a;pd=d;@(negedge clk);pe=0;pw=0;
 endtask
 task get(input integer a,output [31:0] d);
  @(negedge clk);pe=1;pw=0;pa=a;@(negedge clk);d=pq;pe=0;
 endtask
 task cfg(input integer a,input [31:0] d);put(24,a);put(28,d);endtask
 task transfer(input [7:0] req,input [31:0] d);
  reg [31:0] s;integer n,retries;
  s=4;retries=0;
  while(s[3:1]==2 && retries<64)begin
   write_reg('h14,d);write_reg(0,(req<<8)|3);n=0;s=1;
   while(s[0] && n<2000)begin read_reg(4,s);n=n+1;end
   retries=retries+1;
  end
  if(s[0] || s[3:1]!=1)$fatal(1,"scalar failed req=%h status=%h",req,s);
 endtask
 task wait_packet;
  reg [31:0] d;integer n;
  n=0;d=0;while(d==0 && n<200000)begin get(8,d);n=n+1;end
  if(d==0)$fatal(1,"packet timeout core=%d sampler=%d packet=%d",dut.u_jtag_core.state,dut.u_probe_sampler.state,dut.u_probe_stream.state);
 endtask
 reg [31:0] d,head_before,expected,safe_at_fault;reg checking_fault=0;
 reg [31:0] dbg_meta,dbg_front,dbg_latched,dbg_tx,dbg_sense;
 integer diag_n,k;
 integer hss_t0,hss_t1,rtt_t0,rtt_t1,hss_total;
 integer i,j,bank_base,samples,packets;
 task perf_write(input [7:0] a,input [31:0] v);write_reg(a,v);endtask
 task perf_read(input [7:0] a,output [31:0] v);read_reg(a,v);endtask
 task perf_put(input integer a,input [31:0] v);put(a,v);endtask
 task perf_get(input integer a,output [31:0] v);get(a,v);endtask
 task perf_scalar(input [7:0] req,input [31:0] v,output [31:0] q);transfer(req,v);read_reg(24,q);endtask
 `include "cm3_perf_tasks.svh"
 always @(posedge clk)if(checking_fault && dut.u_probe_stream.state==6 &&
    $signed(dut.u_probe_stream.produced-safe_at_fault)>0)$fatal(1,"unvalidated HSS bank published");
 initial begin
  for(i=0;i<8192;i=i+1)target.u_sys.mem[i]=32'h12340000+i;
  repeat(6)@(negedge clk);rst_n=1;
  aux_tri=4'ha;aux_out=4'hc;repeat(2)@(negedge clk);
  if(pads[0]!==0)$fatal(1,"GPIO TDI pad cannot drive low");
  aux_out=4'hd;repeat(2)@(negedge clk);
  if(pads[0]!==1)$fatal(1,"GPIO TDI pad cannot drive high");
  write_reg('h80,3);write_reg('h94,'h103);
  if(pads[0]!==0)$fatal(1,"JTAG manual TDI cannot drive low");
  write_reg('h94,'h107);
  if(pads[0]!==1)$fatal(1,"JTAG manual TDI cannot drive high");
  write_reg('h94,0);
  write_reg('h80,3);write_reg('h84,4|(bypass_mode ? (5<<19) : 0));
  write_reg('h88,bypass_mode ? 'h100 : 0);
  write_reg('h08,1|((cfg_idle&15)<<4));write_reg('h8c,0);
  write_reg('h98,(late_mode ? 16 : 0)|(q1_mode ? 1 : 0));
  // Earliest legal status poll: AR is accepted on the very edge where the
  // serial backend consumes the registered start pulse. Busy must include
  // that pulse, or a fast PS can consume the previous command's ACK/data.
  @(negedge clk);aw=0;wd='h603;av=1;wv=1;
  @(posedge clk);if(!awr || !wr)$fatal(1,"launch write stalled");
  @(negedge clk);av=0;wv=0;ar=4;rv=1;
  @(posedge clk);if(!arr)$fatal(1,"launch status stalled");
  @(negedge clk);rv=0;wait(rdv);d=rd;
  if(!d[0])$fatal(1,"AXI launch race: STATUS reports idle before backend accepts start");
  @(negedge clk);wait(!dut.core_busy);repeat(3)@(negedge clk);
  transfer(0,'h1e);transfer(4,'h50000000);transfer(8,0);
  // Multi-word AP write: the board corrupts every fourth word from the third on.
  transfer(1,'h50000032);          // AP CSW: 32-bit, single increment (4 is DP CTRL/STAT)
  transfer(5,'h60004000);
  if($test$plusargs("benchmark"))begin run_transport_benchmark(clk_ns);$finish;end
  for(i=0;i<8;i=i+1)transfer(8'h0d,32'h11110000+i);
  transfer(5,'h60004000);
  transfer(8'h0f,0);                 // posted read, discard the stale result
  for(i=0;i<8;i=i+1)begin
   if(i==7)transfer(8'h0e,0);else transfer(8'h0f,0);
   read_reg(24,d);
   if(d!==(32'h11110000+i))$fatal(1,"JTAG_WR_BAD idx=%0d got=%08h want=%08h",i,d,32'h11110000+i);
  end
  $display("JTAG_WR_DONE");
  // Block engine write over JTAG: the board's Memory.write uses DAP_TransferBlock.
  transfer(5,'h60005000);
  write_reg('h38,0);
  write_reg('h3c,(5<<24)|(8<<8)|8'h0d);
  for(i=0;i<8;i=i+1)write_reg('h3c,32'h22220000+i);
  write_reg('h3c,32'h0300000e);write_reg('h3c,0);
  write_reg('h30,'h1003);
  j=0;d=0;
  while(!d[1] && j<20000)begin read_reg('h34,d);j=j+1;end
  if(!d[1] || d[2] || d[5:3]!=1)$fatal(1,"JTAG_BLK failed status=%h",d);
  for(i=0;i<8;i=i+1)begin
   if(target.u_sys.mem[('h5000+i*4)/4]!==(32'h22220000+i))
     $fatal(1,"JTAG_BLK_BAD idx=%0d got=%08h want=%08h",i,target.u_sys.mem[('h5000+i*4)/4],32'h22220000+i);
  end
  $display("JTAG_BLK_DONE status=%h",d);
  // Firmware fast path: compact TransferBlock packet, shared command BRAM.
  transfer(5,'h60006000);
  write_reg('h38,0);write_reg('h3c,32'h0d000806);
  for(i=0;i<8;i=i+1)write_reg('h3c,32'h91990000+i*'h101);
  write_reg('hcc,3); // arm physical scan history immediately before launch
  write_reg('h44,36);write_reg('h40,1);
  j=0;d=1;
  while(d[0] && j<20000)begin read_reg('h48,d);j=j+1;end
  if(d[0] || !d[1] || d[2])$fatal(1,"JTAG_PKT failed status=%h",d);
  for(i=0;i<8;i=i+1)begin
   if(target.u_sys.mem[('h6000+i*4)/4]!==(32'h91990000+i*'h101))
     $fatal(1,"JTAG_PKT_BAD idx=%0d got=%08h want=%08h",i,target.u_sys.mem[('h6000+i*4)/4],32'h91990000+i*'h101);
  end
  $display("JTAG_PKT_DONE status=%h",d);
  write_reg('hcc,4);read_reg('hcc,d);diag_n=(d>>5)&63;
  if(ENABLE_DIAGNOSTICS)begin
  if(d[31:16]!='h4a54 || diag_n<11)$fatal(1,"JTAG diagnostic history status=%h",d);
  for(k=0;k<diag_n;k=k+1)begin
   write_reg('hd0,k);read_reg('hd4,dbg_meta);read_reg('hd8,dbg_front);
   read_reg('hdc,dbg_latched);read_reg('he0,dbg_tx);read_reg('he4,dbg_sense);
   if(dbg_meta[18:14]==0 && dbg_meta[13:6]==13 &&
      (dbg_front!==dbg_latched || dbg_latched!==dbg_tx || dbg_tx!==dbg_sense))
    $fatal(1,"JTAG diagnostic TX mismatch row=%0d front=%h latched=%h tx=%h pad=%h",k,dbg_front,dbg_latched,dbg_tx,dbg_sense);
  end
  $display("JTAG_DIAG_DONE scans=%0d",diag_n);
  end else if(d!==0)$fatal(1,"compact build exposed diagnostic history %h",d);
  if($test$plusargs("writes_only"))begin $display("PASS JTAG scalar, batch and packet writes");$finish;end
  // No AXI operations per sample: configure once, then PL fills a bank.
  cfg(0,4);cfg(1,2);cfg(2,32);cfg(5,1);
  for(i=0;i<4;i=i+1)cfg(16+i,i);
  write_reg('h78,120000000);write_reg('h68,0);write_reg('h6c,'h60000000);write_reg('h70,32);
  hss_t0=$time;hss_total=0;
  put(0,1);write_reg('h60,'h101);samples=0;packets=0;
  while(samples!=124 && packets<8)begin
   wait_packet();get(8,d);bank_base=4096+((d>>16)&7)*2048;
   get(bank_base,d);if(d!='h02024a53)$fatal(1,"JTAG HSS header %h",d);
   get(bank_base+12,d);samples=d[15:0];if(samples<1 || samples>124)$fatal(1,"HSS count %h",d);hss_total=hss_total+samples;
   for(i=0;i<samples;i=i+1)begin get(bank_base+16+4*i,d);if(d!='h12340000)$fatal(1,"HSS posted data %d %h",i,d);end
   $display("JTAG HSS bank=%d samples=%d skips=%d scans=%d tick=%d",bank_base,samples,dut.u_probe_sampler.skipped,0,dut.u_probe_sampler.tick);
   packets=packets+1;if(samples!=124)put(12,1);
  end
  hss_t1=$time;
  if(samples!=124)$fatal(1,"JTAG cannot sustain requested HSS period");
  // No fault injection on the CM3 target: it has no hook to force an AP error.
  get(bank_base+16,d);if(d!='h12340000)$fatal(1,"validated bank changed");
  write_reg('h60,0);wait(!dut.sampler_active);write_reg('h60,2);
  put(0,0);put(0,256);transfer(0,'h1e);transfer(4,'h50000032);
  // RTT, with unaligned ring and descriptor crossing an AP 1KiB boundary.
  put(32,'h600023f8);put(36,'h600003f1);put(40,4093);put(44,2);put(48,2048);
  target.u_sys.mem['h23fc/4]='h600003f1;target.u_sys.mem['h2400/4]=4093;
  target.u_sys.mem['h2404/4]=2500;target.u_sys.mem['h2408/4]=2;
  rtt_t0=$time;
  put(0,2);wait_packet();rtt_t1=$time;get(8,d);if((d&4095)!=2048)$fatal(1,"RTT length %h",d);
  if(target.u_sys.mem['h2408/4]!=2)$fatal(1,"RTT RdOff advanced before DMA");
  for(i=0;i<512;i=i+1)begin
   for(j=0;j<4;j=j+1)expected[j*8+:8]=target.u_sys.mem[('h3f3+i*4+j)/4][(('h3f3+i*4+j)%4)*8+:8];
   get(4096+4*i,d);if(d!=expected)$fatal(1,"RTT JTAG payload %d %h != %h",i,d,expected);
  end
  put(0,0);put(12,1);wait(target.u_sys.mem['h2408/4]==2050);wait(!dut.rtt_active);
  $display("JTAG_PERF clk_ns=%f hss_samples=%0d hss_cycles=%0d rtt_bytes=%0d rtt_cycles=%0d",clk_ns,hss_total,(hss_t1-hss_t0)/clk_ns,2048,(rtt_t1-rtt_t0)/clk_ns);
  $display("PASS JTAG full pipeline: physical pad mux, AXI setup, autonomous HSS, posted timestamps/data, packet sticky-error fence/drop, immutable banks, RTT unaligned 1KiB split, DDR-before-RdOff");$finish;
 end
 initial begin #(clk_ns*4000000);$fatal(1,"JTAG pipeline watchdog");end
endmodule
