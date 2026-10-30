// Shared performance workload. All payloads are checked; no USB is modeled.
integer perf_waits=0;
real perf_fclk_ns=10.0;
always @(posedge clk)if(dut.core_result_valid && dut.core_ack==2)perf_waits=perf_waits+1;

task perf_cfg(input integer a,input [31:0] v);
  perf_put(24,a);perf_put(28,v);
endtask
task perf_wait_bank(output [31:0] v);
  integer n;real started,limit_ns;begin
    v=0;n=0;started=$realtime;
    limit_ns=40000.0*2.0*(dut.cfg_delay_fast+1)*perf_fclk_ns;
    while(v==0 && n<2000000)begin
      perf_get(8,v);n=n+1;
      if(dut.u_probe_stream.hss_transport_fault || dut.u_probe_sampler.fault || dut.u_probe_stream.rtt_fault)
        $fatal(1,"benchmark stream fault hss=%0d sampler=%0d rtt=%0d fence=%0d",dut.u_probe_stream.hss_transport_fault,dut.u_probe_sampler.fault,dut.u_probe_stream.rtt_fault,dut.jtag_fence_error);
      if($realtime-started>limit_ns)
        $fatal(1,"benchmark bank timeout stream=%0d sampler=%0d active=%0d pending=%0d jtag=%0d busy=%0d fence_req=%0d done=%0d consumed=%0d validated=%0d produced=%0d samples=%0d fifo_head=%0d fifo_tail=%0d",dut.u_probe_stream.state,dut.u_probe_sampler.state,dut.sampler_active,dut.u_probe_sampler.pending,dut.u_jtag_core.state,dut.core_busy,dut.jtag_fence_req,dut.jtag_fence_done,dut.u_jtag_core.fence_consumed,dut.u_probe_stream.validated_count,dut.u_probe_stream.produced,dut.u_probe_stream.samples,dut.u_probe_sampler.head,dut.u_probe_sampler.tail);
    end
    if(v==0)$fatal(1,"benchmark stream bank timeout");
  end
endtask
task perf_sram(input integer is_read);
  integer n,tries,w0;real t0,t1;reg [31:0] s,v;
  begin
    perf_scalar(1,32'h23000052,v);perf_scalar(5,32'h60000000,v);
    perf_write('h38,0);perf_write('h3c,((is_read?32'h0f:32'h0d)<<24)|(256<<8)|6);
    if(!is_read)for(n=0;n<256;n=n+1)perf_write('h3c,32'h87654321^(32'h9e3779b9*n));
    perf_write('h44,is_read?4:1028);w0=perf_waits;t0=$realtime;
    perf_write('h40,1);s=1;tries=0;
    while(s[0] && tries<20000000)begin perf_read('h48,s);tries=tries+1;end
    t1=$realtime;
    if(s[0] || !s[1] || s[2])$fatal(1,"benchmark SRAM status %h",s);
    perf_write('h38,32'h10000);perf_read('h3c,v);
    if(v!==32'h00010100)$fatal(1,"benchmark SRAM header %h",v);
    for(n=0;n<256;n=n+1)begin
      if(is_read)perf_read('h3c,v);else v=target.u_sys.mem[n];
      if(v!==(32'h87654321^(32'h9e3779b9*n)))$fatal(1,"benchmark SRAM data index=%0d got=%h",n,v);
    end
    $display("SIM_SRAM read=%0d bytes=1024 elapsed_ns=%f MBps=%f waits=%0d",is_read,t1-t0,1024.0*1000.0/(t1-t0),perf_waits-w0);
  end
endtask
task perf_rtt;
  reg [31:0] s,v;integer n,w0;real t0,t1;
  begin
    perf_put(0,256);
    target.u_sys.mem['h23fc/4]=32'h60001000;
    target.u_sys.mem['h2400/4]=4096;target.u_sys.mem['h2404/4]=1024;target.u_sys.mem['h2408/4]=0;
    perf_put(32,32'h600023f8);perf_put(36,32'h60001000);perf_put(40,4096);perf_put(44,0);perf_put(48,1024);
    w0=perf_waits;t0=$realtime;perf_put(0,2);perf_wait_bank(s);t1=$realtime;
    if(s[11:0]!=1024)$fatal(1,"benchmark RTT length %h",s);
    for(n=0;n<256;n=n+1)begin
      perf_get(4096+4*n,v);
      if(v!==target.u_sys.mem['h1000/4+n])$fatal(1,"benchmark RTT data index=%0d",n);
    end
    perf_put(0,0);perf_put(12,1);
    // ACK schedules a posted AP write. rtt_active can still be low on the
    // ACK edge, so first wait for its architectural memory effect.
    wait(target.u_sys.mem['h2408/4]==1024);wait(!dut.rtt_active);
    $display("SIM_RTT bytes=1024 elapsed_ns=%f MBps=%f waits=%0d",t1-t0,1024.0*1000.0/(t1-t0),perf_waits-w0);
  end
endtask
task perf_hss(input integer period_ticks,input real fclk_ns,output real measured_rate);
  reg [31:0] s,v,base,n,expected,h0,k0,tick0;
  integer j,total,started,loops;real t0,t1,loss;
  begin
    perf_put(0,256);perf_write('h60,2);
    perf_cfg(0,4);perf_cfg(1,2);perf_cfg(2,period_ticks);perf_cfg(5,1);
    for(j=0;j<4;j=j+1)perf_cfg(16+j,j);
    perf_write('h78,$rtoi(1e9/fclk_ns));perf_write('h68,0);perf_write('h6c,32'h60000000);perf_write('h70,period_ticks);
    expected=target.u_sys.mem[0];total=0;started=0;loops=0;
    // A stopped JTAG sampler can leave a partial-bank CTRL/STAT fence in
    // flight. Start is accepted only when the shared backend is available.
    wait(!dut.core_busy);
    perf_put(0,1);perf_write('h60,257);
    if(!dut.u_probe_sampler.enabled)$fatal(1,"benchmark HSS start was not accepted");
    while(!started || dut.u_probe_sampler.head-h0<64)begin
      perf_wait_bank(s);base=4096+((s>>16)&7)*2048;
      perf_get(base,v);if(v!==32'h02024a53)$fatal(1,"benchmark HSS header %h",v);
      perf_get(base+12,v);n=v[15:0];if(n==0 || n>124)$fatal(1,"benchmark HSS count %h",v);
      for(j=0;j<n;j=j+1)begin perf_get(base+16+4*j,v);if(v!==expected)$fatal(1,"benchmark HSS payload");end
      perf_put(12,1);total=total+n;loops=loops+1;
      if(!started && total>=16)begin
        started=1;h0=dut.u_probe_sampler.head;k0=dut.u_probe_sampler.skipped;tick0=dut.u_probe_sampler.tick;t0=$realtime;
      end
      if(loops>1000)$fatal(1,"benchmark HSS progress timeout");
    end
    t1=$realtime;measured_rate=(dut.u_probe_sampler.head-h0)*1e9/(t1-t0);
    loss=100.0*(dut.u_probe_sampler.skipped-k0)/((dut.u_probe_sampler.head-h0)+(dut.u_probe_sampler.skipped-k0));
    $display("SIM_HSS period=%0d produced=%0d skipped=%0d elapsed_ns=%f Hz=%f skip_percent=%f",period_ticks,dut.u_probe_sampler.head-h0,dut.u_probe_sampler.skipped-k0,t1-t0,measured_rate,loss);
    if(dut.u_probe_sampler.errors || dut.u_probe_sampler.fault)$fatal(1,"benchmark HSS target error");
    perf_write('h60,0);wait(!dut.sampler_active);perf_put(0,0);perf_put(0,256);
  end
endtask
task run_transport_benchmark(input real fclk_ns);
  integer n,period;real peak,zero,clock_rate;
  begin
    perf_fclk_ns=fclk_ns;
    for(n=0;n<4096;n=n+1)target.u_sys.mem[n]=32'h12340000+n;
    if(!$test$plusargs("skip_sram"))begin perf_sram(0);perf_sram(1);end
    perf_rtt;
    perf_hss(24,fclk_ns,peak);
    clock_rate=(1e9/fclk_ns<24e6)?1e9/fclk_ns:24e6;
    period=$rtoi($ceil(clock_rate/peak*1.10));if(period<24)period=24;
    perf_hss(period,fclk_ns,zero);
    $display("PASS SIM_TRANSPORT_BENCH payloads and counters verified");
  end
endtask
