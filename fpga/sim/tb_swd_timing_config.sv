`timescale 1ns/1ps
module tb_swd_timing_config;
  reg clk=0;always #5 clk=~clk;reg rst_n=0;
  reg [7:0] awaddr=0,araddr=0;
  reg awvalid=0,wvalid=0,arvalid=0;
  reg [31:0] wdata=0;
  reg [3:0] wstrb=15;
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
    .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
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

  task wr(input [7:0] addr,input [31:0] data);
    begin
      @(negedge clk);awaddr=addr;wdata=data;awvalid=1;wvalid=1;
      @(posedge clk);if(!awready||!wready)$fatal(1,"AXI write stalled");
      @(negedge clk);awvalid=0;wvalid=0;
      wait(bvalid);repeat(2)@(negedge clk);
    end
  endtask
  task rd(input [7:0] addr,output [31:0] data);
    begin
      @(negedge clk);araddr=addr;arvalid=1;
      @(posedge clk);if(!arready)$fatal(1,"AXI read stalled");
      @(negedge clk);arvalid=0;
      wait(rvalid);data=rdata;@(negedge clk);
    end
  endtask
  task expect_reg(input [7:0] a,input [31:0] wanted);
    reg [31:0] v;begin rd(a,v);if(v!==wanted)$fatal(1,"CSR %h got=%h expected=%h",a,v,wanted);end
  endtask
  task split_partial(input [7:0] a,input [31:0] data,input [3:0] mask);
    @(negedge clk);awaddr=a;awvalid=1;
    @(posedge clk);if(!awready)$fatal(1,"split AW stalled");
    @(negedge clk);awvalid=0;awaddr=0;
    repeat(2)@(negedge clk);wdata=data;wstrb=mask;wvalid=1;
    @(posedge clk);if(!wready)$fatal(1,"split W stalled");
    @(negedge clk);wvalid=0;wstrb=15;wait(bvalid);repeat(2)@(negedge clk);
  endtask
  task stage_defaults;
    wr(8'hd0,1);wr(8'hd4,65536);wr(8'hd8,393216);
    wr(8'hdc,65536);wr(8'he0,65536);wr(8'he4,0);wr(8'he8,0);wr(8'hec,32'h20a21);
  endtask
  reg [31:0] v,epoch_before,status,old_cfg;integer i;
  reg block_core=0,block_packet=0,block_batch=0,block_sampler=0,block_rtt=0;
  initial begin
    force dut.core_busy=block_core;force dut.packet_busy=block_packet;
    force dut.batch_active=block_batch;force dut.sampler_active=block_sampler;
    force dut.rtt_active=block_rtt;
    repeat(4)@(negedge clk);rst_n=1;repeat(4)@(negedge clk);
    expect_reg(8'hf8,32'h53575431);expect_reg(8'hd0,0);rd(8,old_cfg);
    // Extended addresses must not alias reset/trace/sampler registers.
    wr(8'h68,0);wr(8'h6c,32'h200003fc);stage_defaults();
    expect_reg(8'hd0,0);expect_reg(8'hd4,65536);expect_reg(8'h50,0);
    expect_reg(8'h6c,32'h200003fc);expect_reg(8,old_cfg);
    wr(8'hf0,1);expect_reg(8'hd0,1);expect_reg(8,32'h20a21);
    rd(8'hf4,epoch_before);
    // Each live owner independently rejects an atomic commit.
    for(i=0;i<5;i=i+1)begin
      block_core=i==0;block_packet=i==1;block_batch=i==2;block_sampler=i==3;block_rtt=i==4;
      wr(8'hd4,131072);wr(8'hf0,1);rd(8'hf4,status);
      if(status[15:8]!=1 || status[31:16]!=epoch_before[31:16])$fatal(1,"busy commit accepted owner %d",i);
      expect_reg(8'hd4,65536);wr(8'hf0,4);expect_reg(8'hd0,1);
    end
    block_core=0;block_packet=0;block_batch=0;block_sampler=0;block_rtt=0;
    wr(8'hf0,1);expect_reg(8'hd4,131072);
    // ACK and data offsets, source selection, and per-stage periods are live.
    wr(8'hdc,32'h20000);wr(8'he0,32'h40001);wr(8'he4,196608);wr(8'he8,262144);
    wr(8'hf0,1);expect_reg(8'hdc,32'h20000);expect_reg(8'he0,32'h40001);
    expect_reg(8'he4,196608);expect_reg(8'he8,262144);
    rd(8'hf4,epoch_before);
    wr(8'hd4,65535);wr(8'hf0,1);rd(8'hf4,status);
    if(status[15:8]!=3 || status[31:16]!=epoch_before[31:16])$fatal(1,"invalid half period");
    expect_reg(8'hd4,131072);wr(8'hf0,2); // discard invalid staged write
    wr(8'he0,2);wr(8'hf0,1);rd(8'hf4,status);
    if(status[15:8]!=5)$fatal(1,"missing sample event accepted");
    wr(8'hf0,2);wr(8'hd0,2);wr(8'hf0,1);rd(8'hf4,status);
    if(status[15:8]!=2)$fatal(1,"reserved control bit accepted");
    wr(8'hf0,2);wr(8'hf0,4);expect_reg(8'hd0,0);
    split_partial(8'hd4,64,1);expect_reg(8'hd4,131072);
    wr(8'hf0,1);expect_reg(8'hd4,131136);
    // Core/stream execution reset must preserve the user's configuration.
    wr(8'h50,1);expect_reg(8'hd4,131136);expect_reg(8'hf8,32'h53575431);
    $display("PASS timing CSR: staged/atomic, every busy owner, alias isolation, independent samples/periods, invalid reject, disable/reset persistence");
    $finish;
  end
  initial begin #1000000;$fatal(1,"CSR watchdog");end
endmodule
