// Included in tb_cm3_swd: configure actual CM3 CoreSight via PL SWD/MEM-AP.
// F103ZE recipe reference: superlinkPRO/etm/tools/f103ze_etm.py.
wire [31:0] etm_mmio_data;
wire etm_valid,etm_synced,etm_overflow;
wire [7:0] etm_data=etm_mmio_data[7:0];
wire [6:0] etm_channel=etm_mmio_data[14:8];
wire etm_awready,etm_wready,etm_bvalid;
reg etm_awvalid=0,etm_wvalid=0;
reg [31:0] etm_ctrl_data=0;
reg etm_ready=1;
integer etm_count=0,etm_frames=0,etm_file=0,etm_raw_file=0;
integer etm_ready_cycle=0;
reg etm_record=0;
reg etm_capture_reset=1;
reg etm_refclk=0;always #2.5 etm_refclk=~etm_refclk;
real etm_previous_trace_edge=0,etm_trace_period=0;
always @(negedge clk)begin
  etm_ready_cycle=etm_ready_cycle+1;
  etm_ready=!$test$plusargs("etm_stalls") || (etm_ready_cycle%11>=3);
end
// Exercise exactly the board frontend, including BUFIO/BUFR, pipelined IDDR,
// BRAM records and the PS AXI read aperture. Empty reads return bit31=1.
orbtrace_controller etm_receiver(.trace_clk(cm3_traceclk),.trace_data(cm3_tracedata),.ref_clk(etm_refclk),.clk(clk),.rst_n(rst_n && !etm_capture_reset),
  .s_axi_awaddr(6'd4),.s_axi_awprot(3'd0),.s_axi_awvalid(etm_awvalid),.s_axi_awready(etm_awready),
  .s_axi_wdata(etm_ctrl_data),.s_axi_wstrb(4'hf),.s_axi_wvalid(etm_wvalid),.s_axi_wready(etm_wready),
  .s_axi_bresp(),.s_axi_bvalid(etm_bvalid),.s_axi_bready(1'b1),
  .s_axi_araddr(6'd16),.s_axi_arprot(3'd0),.s_axi_arvalid(etm_record),.s_axi_arready(),
  .s_axi_rdata(etm_mmio_data),.s_axi_rresp(),.s_axi_rvalid(etm_valid),.s_axi_rready(etm_ready));
assign etm_synced=etm_receiver.seen_sync;
assign etm_overflow=etm_receiver.lost;
always @(posedge clk)if(rst_n && etm_record && etm_valid && etm_ready && !etm_mmio_data[31])begin
  if(etm_channel!=2)$fatal(1,"unexpected ETM source ID %0d",etm_channel);
  if($isunknown(etm_data))$fatal(1,"unknown ETM byte");
  $fwrite(etm_file,"%02x\n",etm_data);
  etm_count=etm_count+1;
end
always @(posedge etm_receiver.trace_clock)if(etm_record && etm_receiver.receiver.toggle!=etm_receiver.receiver.previous_toggle)begin
  $fwrite(etm_raw_file,"%032x\n",etm_receiver.receiver.frame);
  etm_frames=etm_frames+1;
end
always @(posedge cm3_traceclk)if(etm_record)begin
  if(etm_previous_trace_edge!=0)etm_trace_period=$realtime-etm_previous_trace_edge;
  etm_previous_trace_edge=$realtime;
end
task etm_arm_receiver;
  begin
    @(negedge clk);etm_ctrl_data=15;etm_awvalid=1;etm_wvalid=1;
    @(posedge clk);if(!etm_awready || !etm_wready)$fatal(1,"ETM AXI control handshake");
    @(negedge clk);etm_awvalid=0;etm_wvalid=0;wait(etm_bvalid);wait(etm_receiver.delay_ready);repeat(4)@(negedge clk);
  end
endtask
task etm_read(input [31:0] addr,output [31:0] result);
  reg [31:0] v;
  begin
    xfer(8'h05,addr,v);xfer(8'h0f,0,v);xfer(8'h0e,0,result);
  end
endtask
task etm_write(input [31:0] addr,input [31:0] d);
  begin memory_write(addr,d);end
endtask
task etm_wait_program(input bit programming);
  integer n;reg [31:0] v;
  begin
    n=0;v=0;
    etm_read(32'he0041010,v);
    while(v[1]!=programming && n<100)begin etm_read(32'he0041010,v);n=n+1;end
    if(v[1]!=programming)$fatal(1,"ETM programming=%0d status=%h",programming,v);
  end
endtask
task run_etm_trace;
  reg [31:0] v,control,supported;
  integer n,width_bits,config_file;
  reg [31:0] idr,ccer;
  begin
    width_bits=4;
    // The CM3 acceptance target is the F103ZE-compatible four-pin DDR port.
    // Other pin counts are covered by tb_orbtrace_parallel, not claimed here.
    etm_read(32'he000ed00,v);$display("ETM CM3 CPUID=%h",v);
    if(v[15:4]!=12'hc23)$fatal(1,"CM3 CPUID %h",v);
    etm_read(32'he000edfc,v);etm_write(32'he000edfc,v|32'h01000000);
    etm_read(32'he000edfc,v);$display("ETM DEMCR=%h TRCENA=%b",v,cm3_trcena);
    etm_read(32'he00411e4,idr);$display("ETM ID=%h",idr);
    etm_read(32'he00411e8,ccer);$display("ETM CCER=%h",ccer);
    etm_read(32'he0040000,supported);$display("ETM TPIU supported width mask=%h",supported);
    if(!(supported & (width_bits*2)))$fatal(1,"model lacks DDR width %0d",width_bits);
    // The model exposes the TPIU directly; STM32 DBGMCU pin routing is absent.
    etm_write(32'he0041fb0,32'hc5acce55);etm_write(32'he0040fb0,32'hc5acce55);
    etm_read(32'he0041000,control);
    control=(control|32'hc00)&~32'h301;
    etm_write(32'he0041000,control);etm_wait_program(1);
    etm_write(32'he0041008,0);
    etm_write(32'he0041020,32'h6f);
    etm_write(32'he0041024,0);
    etm_write(32'he004102c,0);
    etm_write(32'he0041200,2);
    etm_write(32'he0040004,width_bits*2);
    etm_write(32'he00400f0,0);
    etm_write(32'he0040304,2);
    etm_read(32'he0040004,v);if(v!=width_bits*2)$fatal(1,"TPIU width readback %h",v);
    etm_read(32'he0041200,v);if(v!=2)$fatal(1,"ETM source ID readback %h",v);
    config_file=$fopen("cm3_etm_config.json","w");
    $fwrite(config_file,"{\"protocol\":\"ETMv3\",\"idr\":%0d,\"ctrl\":%0d,\"ccer\":%0d,\"traceid\":2}\n",idr,control&~32'h400,ccer);
    $fclose(config_file);
    etm_capture_reset=0;
    etm_file=$fopen("cm3_etm.hex","w");etm_raw_file=$fopen("cm3_tpiu.hex","w");
    if(!etm_file || !etm_raw_file)$fatal(1,"capture file open");
    etm_arm_receiver;
    etm_record=1;
    etm_write(32'he0041000,control&~32'h400);etm_wait_program(0);
    repeat(50000)@(negedge clk);
    if(!etm_synced || etm_overflow || etm_count<100 || etm_frames<10)
      $fatal(1,"ETM capture sync=%b overflow=%b bytes=%0d frames=%0d",etm_synced,etm_overflow,etm_count,etm_frames);
    if(target.lockup)$fatal(1,"CM3 workload locked up");
    // Stop producer and drain the CDC/demux before closing the evidence.
    etm_write(32'he0041000,control);etm_wait_program(1);
    n=0;while(etm_receiver.level!=0 && n<100000)begin @(negedge clk);n=n+1;end
    repeat(1000)@(negedge clk);etm_record=0;
    if(etm_receiver.level!=0)$fatal(1,"ETM PS FIFO did not drain");
    if(etm_overflow)$fatal(1,"ETM overflow while draining");
    $fclose(etm_file);$fclose(etm_raw_file);
    $display("PASS CM3 ORBTrace ETM DDR pins=%0d HCLK_ns=%f FCLK_ns=%f bytes=%0d frames=%0d",width_bits,core_period_ns,2*half_ns,etm_count,etm_frames);
    $display("ETM_PS_AXI_PASS TRACECLK_ns=%f source=BUFIO/BUFR/IDDR/BRAM/AXI",etm_trace_period);
  end
endtask
