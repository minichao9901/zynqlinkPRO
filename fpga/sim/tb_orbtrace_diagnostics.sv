`timescale 1ns/1ps
module tb_orbtrace_diagnostics;
  reg clk=0;always #4.166667 clk=~clk;
  reg refclk=0;always #2.5 refclk=~refclk;
  reg rst_n=0,tclk=0;
  reg [3:0] pins=0;
  reg [7:0] aw=0,ar=0;
  reg av=0,wv=0,rv=0,rr=1;
  reg [31:0] wd=0;
  wire awr,wr,bv,arr,rdv;wire [31:0] rd;
  orbtrace_controller #(.FIFO_ADDR_BITS(4),.RAW_DIAGNOSTIC(4)) dut(
    .clk(clk),.rst_n(rst_n),.ref_clk(refclk),.trace_clk(tclk),.trace_data(pins),
    .s_axi_awaddr(aw),.s_axi_awprot(3'd0),.s_axi_awvalid(av),.s_axi_awready(awr),
    .s_axi_wdata(wd),.s_axi_wstrb(4'hf),.s_axi_wvalid(wv),.s_axi_wready(wr),
    .s_axi_bresp(),.s_axi_bvalid(bv),.s_axi_bready(1'b1),
    .s_axi_araddr(ar),.s_axi_arprot(3'd0),.s_axi_arvalid(rv),.s_axi_arready(arr),
    .s_axi_rdata(rd),.s_axi_rresp(),.s_axi_rvalid(rdv),.s_axi_rready(rr));
  task write_reg(input [7:0] a,input [31:0] v);
    begin
      @(negedge clk);aw=a;wd=v;av=1;wv=1;
      do @(posedge clk);while(!awr || !wr);
      @(negedge clk);av=0;wv=0;wait(bv);repeat(2)@(negedge clk);
    end
  endtask
  task read_reg(input [7:0] a,output [31:0] v);
    begin
      @(negedge clk);ar=a;rv=1;
      do @(posedge clk);while(!arr);
      @(negedge clk);rv=0;wait(rdv);v=rd;
      @(posedge clk);@(negedge clk);
    end
  endtask
  task byte_out(input [7:0] v);
    begin pins=v[3:0];#25;tclk=1;#25;pins=v[7:4];#25;tclk=0;#25;end
  endtask
  task frame_out;integer i;reg [127:0] f;
    begin f=128'h05ab1011121307912021222324250908;for(i=15;i>=0;i--)byte_out(f>>(i*8));end
  endtask
  task sync_out;begin byte_out('hff);byte_out('hff);byte_out('hff);byte_out('h7f);end endtask
  task idle;integer n;begin for(n=0;n<20;n++)begin byte_out('hff);byte_out('h7f);end end endtask
  reg [31:0] v,errors;
  integer i;
  initial begin
    #100;rst_n=1;repeat(80)@(negedge clk);
    read_reg(32,v);if(v!==32'h45544431)$fatal(1,"ETD1 diagnostics missing");
    read_reg(68,v);if(v!==4)$fatal(1,"wrong source mode");
    read_reg(72,v);if(v!==15)$fatal(1,"missing implemented capability bits");
    write_reg(4,15);repeat(40)byte_out(0);sync_out();frame_out();idle();
    read_reg(12,v);if(v!=12)$fatal(1,"ordinary frame data changed: level=%d",v);
    read_reg(44,v);if(v!=12)$fatal(1,"record highwater=%d",v);
    read_reg(40,v);if(v<1 || v>8)$fatal(1,"frame highwater=%d",v);
    read_reg(36,v);if(v!=0)$fatal(1,"clean data reported faults=%h",v);
    // A full sync in a partial frame is a parser fault, not FIFO pressure.
    byte_out('h55);byte_out('haa);sync_out();idle();
    read_reg(36,v);if(v!==2)$fatal(1,"parser fault classification=%h",v);
    read_reg(52,errors);if(errors==0)$fatal(1,"parser event not counted");
    read_reg(48,v);if(v!=0)$fatal(1,"parser error confused with frame drop");
    write_reg(4,12);repeat(30)byte_out(0);
    read_reg(36,v);if(v!==2)$fatal(1,"stop erased parser flags");
    read_reg(52,v);if(v!==errors)$fatal(1,"stop erased parser count");
    // Clear with old sticky CDC flags still set must not relatch old loss.
    write_reg(4,14);repeat(40)byte_out(0);
    read_reg(8,v);if(v!==8)$fatal(1,"old loss relatched after clear: %h",v);
    read_reg(36,v);if(v!=0)$fatal(1,"clear flags");
    read_reg(52,v);if(v!=0)$fatal(1,"clear counters");
    write_reg(4,15);repeat(40)byte_out(0);sync_out();
    for(i=0;i<50;i++)frame_out();idle();
    write_reg(4,12);repeat(30)byte_out(0);
    read_reg(36,v);if(v!==1)$fatal(1,"FIFO fault classification=%h",v);
    read_reg(48,v);if(v==0)$fatal(1,"missing dropped-frame count");
    read_reg(52,v);if(v!=0)$fatal(1,"backpressure confused with parser error");
    read_reg(44,v);if(v!=16)$fatal(1,"record highwater should be full: %d",v);
    read_reg(40,v);if(v!=8)$fatal(1,"frame highwater should be full: %d",v);
    read_reg(60,v);if(v==0)$fatal(1,"record backpressure not counted");
    write_reg(4,15);repeat(40)byte_out(0);sync_out();idle();
    force dut.delay_calibrated=0;repeat(12)@(negedge clk);release dut.delay_calibrated;
    repeat(40)byte_out(0);write_reg(4,12);repeat(30)byte_out(0);
    read_reg(56,v);if(v!=1)$fatal(1,"reference-loss event count=%d",v);
    read_reg(36,v);if(!v[2])$fatal(1,"reference loss flag missing");
    $display("PASS ETD1 parser/FIFO/reference separation, highwater, stop persistence and clear CDC");$finish;
  end
  initial begin #2000000;$fatal(1,"timeout");end
endmodule
