`timescale 1ns/1ps
// SWD link against the real Cortex-M3 DesignStart core (XSim only).
// The CM3 RTL is IEEE-1735 encrypted and lives outside this repository.
module tb_cm3_swd #(
  parameter real FCLK_HALF_NS = 4.166667,
  parameter real RETURN_NS = 16.0,
  parameter integer SAMPLE_RISE = 0,
  parameter integer ACK_DELAY = 0,
  parameter integer TURN_EXTRA = 0,
  parameter integer TEST_WORDS = 16
);
  real half_ns=FCLK_HALF_NS, return_ns=RETURN_NS;
  integer phase=SAMPLE_RISE, ack_delay=ACK_DELAY, turn_extra=TURN_EXTRA, words=TEST_WORDS, idle=0;
  integer rx_boundary=0, transfer_delay=0;
  reg clk=0;
  initial begin
    if($value$plusargs("half_ns=%f",half_ns))begin end
    forever #(half_ns) clk=~clk;
  end
  reg target_clk=0; always #5 target_clk=~target_clk;
  reg rst_n=1;
  reg [7:0] awaddr=0,araddr=0;
  reg awvalid=0,wvalid=0,arvalid=0;
  reg [31:0] wdata=0;
  wire awready,wready,bvalid,arready,rvalid;
  wire [31:0] rdata;
  reg cmd_en=0; reg [3:0] cmd_we=0;
  reg [31:0] cmd_addr=0,cmd_data=0;
  reg rsp_en=0; reg [31:0] rsp_addr=0; wire [31:0] rsp_data;
  reg pkt_en=0; reg [3:0] pkt_we=0;
  reg [31:0] pkt_addr=0,pkt_wdata=0; wire [31:0] pkt_rdata;
  wire swclk; tri1 swdio;
  swd_controller dut(.clk(clk),.rst_n(rst_n),
    .s_axi_awaddr(awaddr),.s_axi_awprot(3'd0),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
    .s_axi_wdata(wdata),.s_axi_wstrb(4'hf),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
    .s_axi_bvalid(bvalid),.s_axi_bready(1'b1),
    .s_axi_araddr(araddr),.s_axi_arprot(3'd0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
    .s_axi_rdata(rdata),.s_axi_rvalid(rvalid),.s_axi_rready(1'b1),
    .cmd_bram_clk(clk),.cmd_bram_rst(1'b0),.cmd_bram_en(cmd_en),.cmd_bram_we(cmd_we),
    .cmd_bram_addr(cmd_addr),.cmd_bram_wrdata(cmd_data),
    .rsp_bram_clk(clk),.rsp_bram_rst(1'b0),.rsp_bram_en(rsp_en),.rsp_bram_we(4'd0),
    .rsp_bram_addr(rsp_addr),.rsp_bram_wrdata(32'd0),.rsp_bram_rddata(rsp_data),
    .pkt_bram_clk(clk),.pkt_bram_rst(1'b0),.pkt_bram_en(pkt_en),.pkt_bram_we(pkt_we),
    .pkt_bram_addr(pkt_addr),.pkt_bram_wrdata(pkt_wdata),.pkt_bram_rddata(pkt_rdata),
    .swclk(swclk),.swdio(swdio));

  // Direction-aware return path prevents a delayed inout feedback loop.
  // Delay NBAs are transport delays: short bits are not filtered out.
  // The CM3 core runs on its own 100 MHz HCLK; only the debug port follows
  // the DUT's SWCLK.
  reg core_clk=0; always #5 core_clk=~core_clk;
  tri1 target_pad;
  assign target_pad = dut.swdio_t ? 1'bz : dut.swdio_o;
  wire cm3_swdo, cm3_swdoen, cm3_tdo, cm3_ntdoen, cm3_jtagnsw;
  wire [3:0] cm3_pads;
  assign cm3_pads[1] = cm3_ntdoen ? 1'bz : cm3_tdo;
  cm3_target target(
    .clk(core_clk),.rst_n(rst_n),.dbg_rst_n(rst_n),.trst_n(1'b1),
    .swclktck(swclk),.swditms(target_pad),.tdi(cm3_pads[0]),
    .tdo(cm3_tdo),.ntdoen(cm3_ntdoen),
    .swdo(cm3_swdo),.swdoen(cm3_swdoen),.jtag_nsw(cm3_jtagnsw),
    .sys_dout(),.sys_writes());
  reg return_oe=0,return_data=1;
  always @(cm3_swdoen or cm3_swdo) begin
    return_oe <= #(return_ns) (cm3_swdoen === 1'b1);
    return_data <= #(return_ns) cm3_swdo;
  end
  assign swdio = return_oe ? return_data : 1'bz;
  always @(posedge swclk or negedge swclk) if($test$plusargs("trace"))
    $display("WIRE t=%t clk=%b pad=%b target_o=%b target_oe=%b host_o=%b host_t=%b state=%0d lsm=%0d hdr=%h ack=%b",
       $time,swclk,target_pad,cm3_swdo,cm3_swdoen,dut.swdio_o,dut.swdio_t,
       dut.u_swd_core.state,dut.u_swd_core.lsm_cnt,dut.u_swd_core.req_hdr,dut.u_swd_core.ack_samples);

  always @(posedge clk) if($test$plusargs("coretrace") && dut.core_result_valid)
    $display("CORE t=%0t req=%h ack=%h wd=%h rd=%h committing=%b state=%0d",
      $time,dut.core_req_sel,dut.core_ack,dut.core_wdata_sel,dut.core_rdata,dut.u_probe_stream.u_rtt.committing,dut.u_probe_stream.u_rtt.state);

  task wr(input [6:0] addr,input [31:0] data);
    begin
      @(negedge clk);awaddr=addr;wdata=data;awvalid=1;wvalid=1;
      @(posedge clk);if(!awready||!wready)$fatal(1,"AXI write stalled");
      @(negedge clk);awvalid=0;wvalid=0;
      wait(bvalid);repeat(2)@(negedge clk);
    end
  endtask
  task rd(input [6:0] addr,output [31:0] data);
    begin
      @(negedge clk);araddr=addr;arvalid=1;
      @(posedge clk);if(!arready)$fatal(1,"AXI read stalled");
      @(negedge clk);arvalid=0;
      wait(rvalid);data=rdata;@(negedge clk);
    end
  endtask
  task wait_idle;
    reg [31:0] s; integer timeout;
    begin
      s=1;timeout=0;
      while(s[0] && timeout<3000)begin rd(4,s);timeout=timeout+1;end
      if(timeout==3000)$fatal(1,"core timeout");
    end
  endtask
  task swj(input integer count,input [255:0] bits);
    integer k;
    begin
      for(k=0;k<8;k=k+1)wr(7'h10+k*4,bits[k*32+:32]);
      wr(12,count);wr(0,1);wait_idle;
    end
  endtask
  task raw(input [7:0] req,input [31:0] data,output [2:0] ack,output [31:0] value);
    reg [31:0] s;
    begin
      wr(20,data);wr(0,(req<<8)|3);wait_idle;rd(4,s);rd(24,value);
      ack=s[3:1];
      if(ack==1 && req[1] && s[7])$fatal(1,"read parity req=%h value=%h",req,value);
      $display("XFER req=%h ack=%h data=%h",req,ack,value);
    end
  endtask
  task xfer(input [7:0] req,input [31:0] data,output [31:0] value);
    reg [2:0] a;integer tries;
    begin
      tries=0;a=2;
      while(a==2 && tries<100)begin raw(req,data,a,value);tries=tries+1;end
      if(a!==1)$fatal(1,"transfer req=%h ACK=%h",req,a);
    end
  endtask
  task put(input integer addr,input [31:0] data);
    begin
      @(negedge clk);cmd_en=1;cmd_we=15;cmd_addr=addr*4;cmd_data=data;
      @(negedge clk);cmd_en=0;cmd_we=0;
    end
  endtask
  task get_response(input integer addr,output [31:0] data);
    begin
      @(negedge clk);rsp_en=1;rsp_addr=addr*4;
      repeat(2)@(negedge clk);data=rsp_data;rsp_en=0;
    end
  endtask
  task packet(input integer count,input integer is_read);
    reg [31:0] status,response;
    integer n,timeout;
    begin
      xfer(8'h05,32'h60000000,value);
      put(0,((is_read?32'h0f:32'h0d)<<24)|(count<<8)|6);
      if(!is_read)for(n=0;n<count;n=n+1)put(n+1,32'h87654321^(32'h9e3779b9*(n%256)));
      wr(7'h44,is_read?4:(count+1)*4);wr(7'h40,1);
      status=0;timeout=0;
      while(!status[1] && timeout<100000)begin rd(7'h48,status);timeout=timeout+1;end
      if(!status[1] || status[2] || status[0])$fatal(1,"packet status %h",status);
      get_response(0,response);
      if(response!==((32'h1<<16)|count))$fatal(1,"packet header %h count=%0d",response,count);
      if(status[31:16] !== (is_read?count+1:1))$fatal(1,"response length %h",status);
      if(is_read)for(n=0;n<count;n=n+1)begin
        get_response(n+1,response);
        if(response!==(32'h87654321^(32'h9e3779b9*(n%256))))
          $fatal(1,"packet read count=%0d index=%0d got=%h",count,n,response);
      end
      $display("PACKET_PASS count=%0d read=%0d",count,is_read);
    end
  endtask
  task stream_write(input integer a,input [31:0] d);
    @(negedge clk);pkt_addr=a;pkt_wdata=d;pkt_en=1;pkt_we=15;
    @(negedge clk);pkt_en=0;pkt_we=0;
  endtask
  task stream_read(input integer a,output [31:0] d);
    @(negedge clk);pkt_addr=a;pkt_en=1;pkt_we=0;
    repeat(2)@(negedge clk);d=pkt_rdata;pkt_en=0;
  endtask
  task stream_cfg(input integer i,input [31:0] d);
    stream_write(24,i);stream_write(28,d);
  endtask
  task memory_write(input [31:0] a,input [31:0] d);
    reg [31:0] v;
    xfer(8'h05,a,v);xfer(8'h0d,d,v);xfer(8'h0e,0,v);
  endtask
  task stream_wait(output [31:0] d);
    integer timeout;
    begin d=0;timeout=0;
      while(d==0 && timeout<20000)begin stream_read(8,d);timeout=timeout+1;end
      if(d==0)$fatal(1,"stream packet timeout");
    end
  endtask
  reg [31:0] value,stream_status,stream_header;
  integer stream_count,stream_limit;
  reg [2:0] error_ack;
  integer saw_wait,saw_fault;
  integer k;
  initial begin
    if($value$plusargs("return_ns=%f",return_ns))begin end
    if($value$plusargs("phase=%d",phase))begin end
    if($value$plusargs("ack_delay=%d",ack_delay))begin end
    if($value$plusargs("turn_extra=%d",turn_extra))begin end
    if($value$plusargs("words=%d",words))begin end
    if($value$plusargs("idle=%d",idle))begin end
    if($value$plusargs("rx_boundary=%d",rx_boundary))begin end
    if($value$plusargs("transfer_delay=%d",transfer_delay))begin end
    if($test$plusargs("vcd"))begin $dumpfile("cm3_swd.vcd");$dumpvars(0,dut,cm3_swdo,cm3_swdoen);end
    #1;rst_n=0;#100;rst_n=1;repeat(30)@(negedge clk);
    wr(8,1 | (idle<<4) | (5<<9) | (transfer_delay<<13) | (phase<<17) | (rx_boundary<<18) | (turn_extra<<23) | (ack_delay<<25));
    swj(64,256'hffffffffffffffff);
    swj(16,256'he79e);
    swj(64,256'hffffffffffffffff);
    swj(8,0);
    xfer(8'h02,0,value);
    if(value!==32'h2ba01477)$fatal(1,"DPIDR %h",value);
    xfer(8'h00,32'h1e,value);
    xfer(8'h04,32'h50000000,value);
    repeat(5)xfer(8'h06,0,value);
    if((value & 32'ha0000000)!==32'ha0000000)$fatal(1,"power handshake %h",value);
    xfer(8'h08,0,value);
    xfer(8'h01,32'h23000052,value);
    xfer(8'h05,32'h60000000,value);
    for(k=0;k<words;k=k+1)begin
      xfer(8'h0d,32'h5a89cdef ^ (32'h9e3779b9*k),value);
    end
    xfer(8'h0e,0,value);
    xfer(8'h05,32'h60000000,value);
    xfer(8'h0f,0,value); // posted read: discard previous result
    for(k=0;k<words;k=k+1)begin
      if(k==words-1)xfer(8'h0e,0,value);else xfer(8'h0f,0,value);
      if(value!==(32'h5a89cdef ^ (32'h9e3779b9*k)))$fatal(1,"SRAM index=%0d got=%h",k,value);
    end
    if($test$plusargs("sampler"))begin
      wr(7'h60,2);wr(7'h78,$rtoi(500000000.0/half_ns));wr(7'h70,240);
      wr(7'h68,0);wr(7'h6c,32'h60000000);
      wr(7'h68,1);wr(7'h6c,32'h60000004);
      wr(7'h60,32'h201);
      // Competing packet/single launches must not disturb the sample owner.
      wr(7'h40,1);wr(0,32'h0203);
      repeat(25000)@(negedge clk);
      wr(7'h60,0);repeat(4000)@(negedge clk);
      rd(7'h64,value);
      if(value[4] || value[31:16]!=16)$fatal(1,"sampler occupancy/fault %h",value);
      for(k=0;k<16;k=k+1)begin
        rd(7'h74,value); // 24 MHz timestamp
        rd(7'h74,value);if(value!==32'h5a89cdef)$fatal(1,"sampler word0 %h",value);
        rd(7'h74,value);if(value!==(32'h5a89cdef^32'h9e3779b9))$fatal(1,"sampler word1 %h",value);
      end
      rd(7'h64,value);if(value[31:16]!=0)$fatal(1,"sampler FIFO drain %h",value);
      xfer(8'h08,0,value);xfer(8'h05,32'h60000000,value);
      xfer(8'h0f,0,value);xfer(8'h0e,0,value);
      if(value!==32'h5a89cdef)$fatal(1,"DAP after sampler %h",value);
      $display("SAMPLER_PASS actual CortexM0 MEM-AP, FIFO, competing launches, DAP recovery");
    end
    if($test$plusargs("streams"))begin
      // Exercise the complete sampler -> SWD -> real MEM-AP -> packet BRAM.
      stream_write(0,256);stream_cfg(0,4);stream_cfg(1,2);
      stream_cfg(2,240);stream_cfg(5,1);
      for(k=0;k<4;k=k+1)stream_cfg(16+k,k);
      wr(7'h60,2);wr(7'h78,$rtoi(500000000.0/half_ns));wr(7'h70,240);
      wr(7'h68,0);wr(7'h6c,32'h60000000);
      stream_write(0,1);wr(7'h60,257);
      // Stop at a completed sample, then flush the posted read and packet.
      wait(dut.u_probe_stream.produced>=3);
      wr(7'h60,0);wait(!dut.sampler_active);stream_write(0,0);
      stream_wait(stream_status);
      stream_read(4096,stream_header);
      if(stream_header!==32'h02024a53)$fatal(1,"HSS header %h",stream_header);
      stream_read(4108,stream_header);stream_count=stream_header[15:0];
      if(stream_count==0)$fatal(1,"HSS empty packet");
      for(k=0;k<stream_count;k=k+1)begin
        stream_read(4112+4*k,value);
        if(value!==32'h5a89cdef)$fatal(1,"HSS data %0d %h",k,value);
      end
      stream_write(12,1);stream_write(0,256);
      $display("HSS_PASS real CortexM0 sampler, posted flush, packet BRAM payload");
      // Descriptor crosses a 1 KiB AP boundary; payload is unaligned.
      xfer(8'h01,32'h23000012,value);
      memory_write(32'h600003fc,32'h60000501);
      memory_write(32'h60000400,64);
      memory_write(32'h60000404,13);
      memory_write(32'h60000408,0);
      for(k=0;k<4;k=k+1)memory_write(32'h60000500+4*k,32'h03020100+k*32'h04040404);
      stream_write(32,32'h600003f8);stream_write(36,32'h60000501);
      stream_write(40,64);stream_write(44,0);stream_write(48,13);
      stream_write(0,2);stream_wait(stream_status);
      if(stream_status[11:0]!=13)$fatal(1,"RTT length %h",stream_status);
      for(k=0;k<3;k=k+1)begin
        stream_read(4096+4*k,value);
        if(value!==(32'h04030201+k*32'h04040404))$fatal(1,"RTT payload %d %h",k,value);
      end
      stream_read(4108,value);if(value[7:0]!=13)$fatal(1,"RTT tail byte %h",value);
      if(target.u_sys.mem['h408/4]!=0)$fatal(1,"RTT committed before DMA ACK");
      stream_write(0,0);stream_write(12,1);
      stream_limit=0;
      while(dut.u_probe_stream.tail==0 && stream_limit<10000)begin
        @(negedge clk);stream_limit=stream_limit+1;
      end
      // The CM3 AP write is posted over AXI, so let it land before checking;
      // the property under test is that RdOff is committed only after DMA.
      stream_limit=0;
      while(target.u_sys.mem['h408/4]!=13 && stream_limit<4000)begin
        @(negedge clk);stream_limit=stream_limit+1;
      end
      if(target.u_sys.mem['h408/4]!=13)begin
        $display("DBG writes=%0d dout=%h mem408=%h code408=%h sys0=%h code0=%h tail=%b rtt_active=%b up_addr=%h",
                 target.u_sys.dbg_writes,target.u_sys.dbg_dout,target.u_sys.mem['h408/4],target.u_code.mem['h408/4],target.u_sys.mem[0],target.u_code.mem[0],
                 dut.u_probe_stream.tail,dut.rtt_active,dut.u_probe_stream.up_addr);
        $fatal(1,"RTT RdOff commit %h",target.u_sys.mem['h408/4]);
      end
      wait(!dut.rtt_active);stream_write(0,256);
      xfer(8'h02,0,value);if(value!==32'h2ba01477)$fatal(1,"DPIDR after streams");
      $display("RTT_PASS real CortexM3 descriptor boundary, unaligned payload, DMA-before-RdOff, DAP recovery");
    end
    if($test$plusargs("packets"))begin
      // The real M0 MEM-AP wraps TAR at 1 KiB. Use a modulo-256 pattern so
      // large raw TransferBlock counts verify the actual AP wrap semantics.
      packet(1,0);packet(1,1);
      packet(2,0);packet(2,1);
      packet(127,0);packet(127,1);
      packet(256,0);packet(256,1);
      packet(770,0);packet(770,1);
      packet(1023,0);packet(1023,1);
    end
    $display("PASS CortexM3 DPIDR/power/AP posted SRAM %0d words",words);$finish;
  end
  initial begin #100000000;$fatal(1,"global timeout");end
endmodule