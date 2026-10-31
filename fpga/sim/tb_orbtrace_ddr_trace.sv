`timescale 1ns/1ps
module tb_orbtrace_ddr_trace;
  reg clk=0;always #4.166 clk=!clk;
  reg rst_n=0;reg [7:0] ax_awaddr=0,ax_araddr=0;reg [31:0] ax_wdata=0;
  reg [3:0] ax_wstrb=15;reg ax_awvalid=0,ax_wvalid=0,ax_bready=0,ax_arvalid=0,ax_rready=0;
  wire ax_awready,ax_wready,ax_bvalid,ax_arready,ax_rvalid;wire [1:0] ax_bresp,ax_rresp;wire [31:0] ax_rdata;
  wire [31:0] awaddr;wire [7:0] awlen;wire [2:0] awsize;wire [1:0] awburst;
  wire awvalid,wlast,wvalid,bready;wire [63:0] wdata;wire [7:0] wstrb;
  wire [3:0] awcache,awqos;wire [2:0] awprot;wire awlock;
  reg awready=1,wready=1,bvalid=0,bhold=0,b_pending=0;reg [1:0] bresp=0;
  reg ref_input=0;always #2.5 ref_input=!ref_input;
  reg trace_clk=0;reg [3:0] trace_data=0;
  reg allow_ready=1;
  wire ref_clock,trace_hold,trace_prepare,trace_ready,trace_idle,receiver_ready;
  wire sampler_gate,parser_enable,parser_clear;
  wire [127:0] source_frame,source_tail;wire [4:0] source_tail_bytes;
  wire source_frame_event,source_error,source_sync,source_ambiguous;
  reg [7:0] l_awaddr=0;reg [31:0] l_wdata=0;reg l_awvalid=0,l_wvalid=0,l_bready=1;
  wire l_awready,l_wready,l_bvalid;wire [1:0] l_bresp;
  reg l_arvalid=0;wire l_arready,l_rvalid;wire [31:0] l_rdata;
  orbtrace_controller #(.RAW_DIAGNOSTIC(4),.ENABLE_DDR(1)) receiver(
    .clk(clk),.rst_n(rst_n),.ref_clk(ref_input),.trace_clk(trace_clk),.trace_data(trace_data),
    .ddr_hold(trace_hold),.ddr_prepare(trace_prepare),.ddr_sampler_gate(sampler_gate),.ddr_parser_enable(parser_enable),.ddr_parser_clear(parser_clear),
    .ddr_ready(trace_ready),.ddr_idle(trace_idle),.ddr_receiver_ready_ref(receiver_ready),.ddr_ref_clk(ref_clock),
    .ddr_frame(source_frame),.ddr_tail(source_tail),.ddr_tail_bytes(source_tail_bytes),.ddr_frame_event(source_frame_event),
    .ddr_parser_error(source_error),.ddr_sync_event(source_sync),.ddr_tail_ambiguous(source_ambiguous),
    .s_axi_awaddr(l_awaddr),.s_axi_awprot(3'd0),.s_axi_awvalid(l_awvalid),.s_axi_awready(l_awready),
    .s_axi_wdata(l_wdata),.s_axi_wstrb(4'hf),.s_axi_wvalid(l_wvalid),.s_axi_wready(l_wready),
    .s_axi_bresp(l_bresp),.s_axi_bvalid(l_bvalid),.s_axi_bready(l_bready),
    .s_axi_araddr(8'd72),.s_axi_arprot(3'd0),.s_axi_arvalid(l_arvalid),.s_axi_arready(l_arready),
    .s_axi_rdata(l_rdata),.s_axi_rvalid(l_rvalid),.s_axi_rready(1'b1));
  orbtrace_ddr_controller #(.ENABLE_TRACE_SOURCE(1),.PREPARE_TIMEOUT(1000)) dut(.clk(clk),.rst_n(rst_n),
    .ref_clk(ref_clock),.trace_ready(trace_ready && allow_ready),.trace_idle(trace_idle),.trace_receiver_ready_ref(receiver_ready),
    .trace_frame(source_frame),.trace_tail(source_tail),.trace_tail_bytes(source_tail_bytes),.trace_frame_event(source_frame_event),
    .trace_parser_error(source_error),.trace_sync_event(source_sync),.trace_tail_ambiguous(source_ambiguous),
    .trace_hold(trace_hold),.trace_prepare(trace_prepare),.trace_sampler_gate(sampler_gate),.trace_parser_enable(parser_enable),.trace_parser_clear(parser_clear),
    .s_axi_awaddr(ax_awaddr),.s_axi_awprot(3'd0),.s_axi_awvalid(ax_awvalid),.s_axi_awready(ax_awready),
    .s_axi_wdata(ax_wdata),.s_axi_wstrb(ax_wstrb),.s_axi_wvalid(ax_wvalid),.s_axi_wready(ax_wready),
    .s_axi_bresp(ax_bresp),.s_axi_bvalid(ax_bvalid),.s_axi_bready(ax_bready),
    .s_axi_araddr(ax_araddr),.s_axi_arprot(3'd0),.s_axi_arvalid(ax_arvalid),.s_axi_arready(ax_arready),
    .s_axi_rdata(ax_rdata),.s_axi_rresp(ax_rresp),.s_axi_rvalid(ax_rvalid),.s_axi_rready(ax_rready),
    .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awcache(awcache),
    .m_axi_awprot(awprot),.m_axi_awlock(awlock),.m_axi_awqos(awqos),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
    .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),
    .m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready));
  integer cycle=0,beat=0,beats=0,bytes_written=0;
  reg [31:0] address,relative,expected,seed=32'h12345678;
  reg [7:0] memory[0:65535];
  always @(posedge clk)begin
    cycle=cycle+1;if(cycle>3000000)$fatal(1,"timeout");
    if(!rst_n)begin bvalid<=0;b_pending<=0;bytes_written=0;beat=0;end
    else begin
      if(awvalid&&awready)begin
        if(awsize!=3 || awburst!=1 || awlen>15 || awcache!=3 || awprot || awlock || awqos)$fatal(1,"master attributes");
        address=awaddr;beat=0;beats=awlen+1;
      end
      if(wvalid&&wready)begin
        if(wlast!==(beat==beats-1))$fatal(1,"last mismatch");
        for(integer j=0;j<8;j=j+1)if(wstrb[j])begin
          relative=address-32'h10000000+8*beat+j;
          if(relative>=65536)$fatal(1,"range");
          memory[relative]=wdata[8*j+:8];bytes_written=bytes_written+1;
        end
        beat=beat+1;if(wlast)begin if(bhold)b_pending<=1;else bvalid<=1;end
      end
      if(b_pending && !bhold)begin bvalid<=1;b_pending<=0;end
      if(bvalid&&bready)bvalid<=0;
    end
  end
  task write_reg(input [7:0] a,input [31:0] value,input reg wfirst,input [1:0] expect_resp);
    begin
      @(negedge clk);ax_awaddr=a;ax_wdata=value;
      if(wfirst)begin
        ax_wvalid=1;@(posedge clk);while(!ax_wready)@(posedge clk);@(negedge clk);ax_wvalid=0;
        repeat(2)@(negedge clk);ax_awvalid=1;@(posedge clk);while(!ax_awready)@(posedge clk);@(negedge clk);ax_awvalid=0;
      end else begin
        ax_awvalid=1;@(posedge clk);while(!ax_awready)@(posedge clk);@(negedge clk);ax_awvalid=0;
        repeat(2)@(negedge clk);ax_wvalid=1;@(posedge clk);while(!ax_wready)@(posedge clk);@(negedge clk);ax_wvalid=0;
      end
      while(!ax_bvalid)@(negedge clk);
      if(ax_bresp!==expect_resp)$fatal(1,"write response at %0h got %0d wanted %0d",a,ax_bresp,expect_resp);
      repeat(3)begin @(negedge clk);if(!ax_bvalid || ax_bresp!==expect_resp)$fatal(1,"B response not held");end
      ax_bready=1;@(negedge clk);ax_bready=0;
    end
  endtask
  task read_reg(input [7:0] a,output [31:0] value);
    begin
      @(negedge clk);ax_araddr=a;ax_arvalid=1;
      @(posedge clk);while(!ax_arready)@(posedge clk);@(negedge clk);ax_arvalid=0;
      while(!ax_rvalid)@(negedge clk);value=ax_rdata;
      repeat(3)begin @(negedge clk);if(!ax_rvalid || ax_rdata!==value)$fatal(1,"R response not held");end
      ax_rready=1;@(negedge clk);ax_rready=0;
    end
  endtask

  task put_byte(input [7:0] value);
    begin trace_data=value[3:0];#25;trace_clk=1;#25;trace_data=value[7:4];#25;trace_clk=0;#25;end
  endtask
  task synchronize_source;
    begin wait(sampler_gate);#50;repeat(2)begin put_byte(8'hff);put_byte(8'hff);put_byte(8'hff);put_byte(8'h7f);end end
  endtask
  task legacy_reset;
    begin
      @(negedge clk);l_awaddr=4;l_wdata=15;l_awvalid=1;l_wvalid=1;
      @(posedge clk);while(!(l_awready&&l_wready))@(posedge clk);
      @(negedge clk);l_awvalid=0;l_wvalid=0;
      while(!l_bvalid)@(negedge clk);@(negedge clk);
    end
  endtask
  reg [31:0] value,count,actual_ticks,flags;
  integer checks=0;
  task wait_done;
    begin value=1;while(value&1)read_reg(8,value);if(!(value&2))$fatal(1,"missing done");end
  endtask
  task verify_payload(input integer n);
    begin for(integer k=0;k<n;k=k+1)if(memory[k]!==8'(16+k))$fatal(1,"trace byte %0d actual=%02x expected=%02x",k,memory[k],8'(16+k));end
  endtask
  initial begin
    repeat(4)@(negedge clk);rst_n=1;
    @(negedge clk);l_arvalid=1;
    do @(posedge clk);while(!l_arready);
    @(negedge clk);l_arvalid=0;wait(l_rvalid);
    if(l_rdata!==32'h10f)$fatal(1,"DDR CSR presence was not advertised safely: %h",l_rdata);
    read_reg(44,value);if(value!=7)$fatal(1,"trace capability");
    write_reg(12,32'h10000000,0,0);write_reg(16,4096,1,0);write_reg(60,2,0,0);write_reg(64,8000,1,0);
    write_reg(124,32'habcd1234,0,0);write_reg(128,32'hdead5678,1,0);
    write_reg(4,1,0,0);synchronize_source();
    for(integer k=0;k<165;k=k+1)put_byte(8'(16+k));
    legacy_reset(); // Emulate old USB ETM cleanup while DDR owns the source.
    wait_done();
    if(value&4)$fatal(1,"normal trace marked failed status=%0h",value);
    read_reg(28,count);if(count!=165)$fatal(1,"trace bytes %0d expected 165",count);
    verify_payload(165);read_reg(68,actual_ticks);if(actual_ticks!=8000)$fatal(1,"hardware window %0d",actual_ticks);
    read_reg(72,flags);if(flags)$fatal(1,"trace quality flags %0h",flags);
    read_reg(84,value);if(value!=10)$fatal(1,"formatter frames %0d",value);
    read_reg(88,value);if(value!=5)$fatal(1,"partial tail %0d",value);
    read_reg(92,value);if(value)$fatal(1,"normal stop reason");
    read_reg(124,value);if(value!=32'habcd1234)$fatal(1,"nonce binding");
    write_reg(124,32'h11112222,0,0);read_reg(124,value);if(value!=32'habcd1234)$fatal(1,"config relabeled old capture");
    checks=checks+1;
    // Capacity stop: retain exact prefix and wait for source EOF despite discarding overflow prefix.
    write_reg(16,32,0,0);write_reg(4,1,0,0);synchronize_source();
    for(integer k=0;k<512 && sampler_gate;k=k+1)put_byte(8'(16+k));
    wait_done();if(!(value&4))$fatal(1,"capacity not reported");
    read_reg(28,count);if(count!=32)$fatal(1,"capacity bytes");verify_payload(32);
    read_reg(92,value);if(value!=2)$fatal(1,"capacity reason %0d",value);
    read_reg(68,actual_ticks);if(actual_ticks==0 || actual_ticks>=8000)$fatal(1,"capacity timing");
    checks=checks+1;
    // Manual stop: stopped target clock cannot prevent EOF/drain on the independent ref clock.
    write_reg(16,4096,0,0);write_reg(4,1,0,0);synchronize_source();
    for(integer k=0;k<165;k=k+1)put_byte(8'(16+k));
    #100;write_reg(4,2,0,0);wait_done();if(value&4)$fatal(1,"manual stop data quality");
    read_reg(28,count);if(count!=165)$fatal(1,"manual stop bytes");verify_payload(165);
    read_reg(92,value);if(value!=1)$fatal(1,"manual stop reason %0d",value);
    read_reg(68,actual_ticks);if(actual_ticks==0 || actual_ticks>=8000)$fatal(1,"manual stop timing");
    checks=checks+1;
    // No source clocks/data: window must close, no fake AXI data and no stale capture.
    write_reg(64,100,0,0);write_reg(4,1,0,0);wait_done();if(!(value&4))$fatal(1,"empty capture accepted");
    read_reg(28,count);if(count)$fatal(1,"empty capture reused data");
    read_reg(68,actual_ticks);if(actual_ticks!=100)$fatal(1,"empty window duration");
    checks=checks+1;
    // Hardware window can end while DDR still owes a response: no early publication.
    write_reg(64,8000,0,0);bhold=1;write_reg(4,1,0,0);synchronize_source();
    for(integer k=0;k<165;k=k+1)put_byte(8'(16+k));
    wait(!sampler_gate);#1000;read_reg(8,value);
    if(!(value&1) || (value&2))$fatal(1,"published before DDR B response");
    bhold=0;wait_done();if(value&4)$fatal(1,"delayed B quality");read_reg(28,count);if(count!=165)$fatal(1,"delayed B length");verify_payload(165);
    checks=checks+1;
    // Physical source cannot stall: deliberately fill 512-frame FIFO, count loss,
    // and eventually deliver EOF after the stalled writer is released.
    write_reg(16,65536,0,0);write_reg(64,200000,0,0);wready=0;write_reg(4,1,0,0);synchronize_source();
    for(integer k=0;k<600*16;k=k+1)put_byte(8'(16+k));
    wait(!sampler_gate);#100;wready=1;wait_done();
    if(!(value&4))$fatal(1,"frame overflow falsely passed");
    read_reg(76,value);if(value==0)$fatal(1,"no dropped frame count");
    read_reg(100,value);if(value!=512)$fatal(1,"FIFO highwater %0d",value);
    read_reg(68,actual_ticks);if(actual_ticks!=200000)$fatal(1,"overflow window changed");
    checks=checks+1;
    // A failed B response stops the source, discards pending frames through EOF,
    // and never promotes bus-accepted bytes into successful DDR bytes.
    bresp=2;write_reg(16,65536,0,0);write_reg(64,8000,0,0);write_reg(4,1,0,0);synchronize_source();
    for(integer k=0;k<512 && sampler_gate;k=k+1)put_byte(8'(16+k));
    wait_done();if(!(value&4))$fatal(1,"failed DDR response falsely passed");
    read_reg(28,count);if(count!=0)$fatal(1,"failed B counted as successful");
    read_reg(92,value);if(value!=3)$fatal(1,"failed B source reason %0d",value);
    bresp=0;checks=checks+1;
    // Failure before source arming must be finite and expose zero counters,
    // rather than previous capture data, even though the writer was not started.
    allow_ready=0;write_reg(4,1,0,0);wait_done();if(!(value&4))$fatal(1,"prepare timeout not failed");
    read_reg(36,value);if(value!=6)$fatal(1,"prepare timeout code");
    read_reg(24,count);if(count)$fatal(1,"stale accepted bytes before arm");
    read_reg(28,count);if(count)$fatal(1,"stale response bytes before arm");
    checks=checks+1;
    write_reg(4,1,0,0);write_reg(4,2,0,0);wait_done();
    read_reg(92,value);if(value!=1)$fatal(1,"early cancel reason");
    read_reg(24,count);if(count)$fatal(1,"early cancel reused accepted bytes");
    read_reg(28,count);if(count)$fatal(1,"early cancel reused response bytes");
    allow_ready=1;checks=checks+1;
    $display("PASS DDR trace integration cases=%0d: RAW4 pins, exact ref window, full/partial formatter frames, nonce, legacy reset isolation, capacity, stop and empty source",checks);
    $finish;
  end
endmodule
