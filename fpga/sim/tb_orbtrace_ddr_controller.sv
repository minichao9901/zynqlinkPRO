`timescale 1ns/1ps
module tb_orbtrace_ddr_controller;
  reg clk=0;always #5 clk=!clk;
  reg rst_n=0;reg [7:0] ax_awaddr=0,ax_araddr=0;reg [31:0] ax_wdata=0;
  reg [3:0] ax_wstrb=15;reg ax_awvalid=0,ax_wvalid=0,ax_bready=0,ax_arvalid=0,ax_rready=0;
  wire ax_awready,ax_wready,ax_bvalid,ax_arready,ax_rvalid;wire [1:0] ax_bresp,ax_rresp;wire [31:0] ax_rdata;
  wire [31:0] awaddr;wire [7:0] awlen;wire [2:0] awsize;wire [1:0] awburst;
  wire awvalid,wlast,wvalid,bready;wire [63:0] wdata;wire [7:0] wstrb;
  wire [3:0] awcache,awqos;wire [2:0] awprot;wire awlock;
  reg awready=1,wready=1,bvalid=0;reg [1:0] bresp=0;
  orbtrace_ddr_controller dut(.clk(clk),.rst_n(rst_n),
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
  reg [7:0] memory[0:8191];
  always @(posedge clk)begin
    cycle=cycle+1;if(cycle>30000)$fatal(1,"timeout");
    if(!rst_n)begin bvalid<=0;bytes_written=0;beat=0;end
    else begin
      if(awvalid&&awready)begin
        if(awsize!=3 || awburst!=1 || awlen>15 || awcache!=3 || awprot || awlock || awqos)$fatal(1,"master attributes");
        address=awaddr;beat=0;beats=awlen+1;
      end
      if(wvalid&&wready)begin
        if(wlast!==(beat==beats-1))$fatal(1,"last mismatch");
        for(integer j=0;j<8;j=j+1)if(wstrb[j])begin
          relative=address-32'h10000000+8*beat+j;
          if(relative>=8192)$fatal(1,"range");
          memory[relative]=wdata[8*j+:8];bytes_written=bytes_written+1;
        end
        beat=beat+1;if(wlast)bvalid<=1;
      end
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
  reg [31:0] value;
  initial begin
    repeat(3)@(negedge clk);rst_n=1;
    read_reg(0,value);if(value!=32'h45444d31)$fatal(1,"signature");
    read_reg(44,value);if(value!=3)$fatal(1,"capabilities must not advertise ETM source");
    write_reg(12,32'h10000000,0,0);write_reg(16,257,1,0);write_reg(20,seed,0,0);
    write_reg(4,1,1,0);value=1;
    while(value&1)read_reg(8,value);
    if(value&4 || !(value&2))$fatal(1,"normal status");
    read_reg(24,value);if(value!=257)$fatal(1,"accepted bytes");
    read_reg(28,value);if(value!=257 || bytes_written!=257)$fatal(1,"response bytes");
    for(integer k=0;k<257;k=k+1)begin
      expected=32'hddaa0000 ^ seed ^ (k/4);
      if(memory[k]!==((expected>>((k%4)*8))&255))$fatal(1,"pattern byte %0d",k);
    end
    awready=0;write_reg(16,8192,0,0);write_reg(4,1,0,0);wait(awvalid);
    write_reg(20,0,1,2);read_reg(20,value);if(value!=seed)$fatal(1,"busy configuration changed");
    write_reg(4,1,0,2);write_reg(4,2,1,0);
    repeat(5)@(negedge clk);read_reg(8,value);if(!(value&1))$fatal(1,"abort completed before AW drained");
    awready=1;value=1;while(value&1)read_reg(8,value);
    if(!(value&4) || !(value&2))$fatal(1,"aborted status");
    read_reg(36,value);if(value!=5)$fatal(1,"abort code");
    write_reg(16,0,1,0);write_reg(4,1,0,0);value=1;while(value&1)read_reg(8,value);
    if(!(value&4))$fatal(1,"invalid configuration not failed");
    read_reg(24,value);if(value)$fatal(1,"invalid attempt reused previous accepted count");
    read_reg(28,value);if(value)$fatal(1,"invalid attempt reused previous response count");
    write_reg(16,8,1,0);write_reg(4,1,0,0);value=1;while(value&1)read_reg(8,value);
    if(value&12 || !(value&2))$fatal(1,"successful restart retained rejected/error flags");
    read_reg(28,value);if(value!=8)$fatal(1,"valid restart response bytes");
    write_reg(0,32'hffffffff,0,2);
    $display("PASS DDR controller: independent AW/W, held responses, pattern/readback, B completion, busy config/restart, abort drain, zero-length and read-only guard");
    $finish;
  end
endmodule
