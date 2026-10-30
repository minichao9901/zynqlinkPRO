`timescale 1ns/1ps
module tb_orbtrace_controller;
  reg clk=0;always #4.166667 clk=~clk;
  reg refclk=0;always #2.5 refclk=~refclk;
  reg rst_n=0,tclk=0;
  reg [3:0] pins=0;
  reg [5:0] aw=0,ar=0;
  reg av=0,wv=0,rv=0,rr=1;
  reg [31:0] wd=0;
  reg [3:0] ws=15;
  wire awr,wr,bv,arr,rdv;wire [31:0] rd;
  orbtrace_controller #(.FIFO_ADDR_BITS(4)) dut(.clk(clk),.rst_n(rst_n),.ref_clk(refclk),.trace_clk(tclk),.trace_data(pins),
    .s_axi_awaddr(aw),.s_axi_awprot(3'd0),.s_axi_awvalid(av),.s_axi_awready(awr),
    .s_axi_wdata(wd),.s_axi_wstrb(ws),.s_axi_wvalid(wv),.s_axi_wready(wr),
    .s_axi_bresp(),.s_axi_bvalid(bv),.s_axi_bready(1'b1),
    .s_axi_araddr(ar),.s_axi_arprot(3'd0),.s_axi_arvalid(rv),.s_axi_arready(arr),
    .s_axi_rdata(rd),.s_axi_rresp(),.s_axi_rvalid(rdv),.s_axi_rready(rr));
  task write_reg(input [5:0] a,input [31:0] v,input bit data_first);
    begin
      @(negedge clk);aw=a;wd=v;
      if(data_first)begin wv=1;do @(posedge clk);while(!wr);@(negedge clk);wv=0;repeat(3)@(negedge clk);av=1;do @(posedge clk);while(!awr);@(negedge clk);av=0;end
      else begin av=1;do @(posedge clk);while(!awr);@(negedge clk);av=0;repeat(2)@(negedge clk);wv=1;do @(posedge clk);while(!wr);@(negedge clk);wv=0;end
      wait(bv);repeat(2)@(negedge clk);
    end
  endtask
  task read_reg(input [5:0] a,output [31:0] v,input integer stall);
    reg [31:0] held;
    begin
      @(negedge clk);ar=a;rv=1;rr=0;
      do @(posedge clk);while(!arr);
      @(negedge clk);rv=0;wait(rdv);held=rd;
      repeat(stall)begin @(negedge clk);if(!rdv || rd!==held)$fatal(1,"AXI R payload changed while stalled");end
      v=held;@(negedge clk);rr=1;@(posedge clk);@(negedge clk);
    end
  endtask
  task byte_out(input [7:0] v);
    begin pins=v[3:0];#5;tclk=1;#5;pins=v[7:4];#5;tclk=0;#5;end
  endtask
  task frame_out(input [127:0] v);
    integer i;begin for(i=15;i>=0;i--)byte_out(v>>(i*8));end
  endtask
  task sync_out;begin byte_out('hff);byte_out('hff);byte_out('hff);byte_out('h7f);end endtask
  integer i;reg [31:0] value;reg [7:0] expect_data[0:11];
  initial begin
    #100;rst_n=1;repeat(40)@(negedge clk);
    read_reg(0,value,0);if(value!==32'h45544d31)$fatal(1,"signature");
    write_reg(4,15,1);repeat(40)byte_out(0);sync_out;
    frame_out(128'h05ab1011121307912021222324250908);
    repeat(20)begin byte_out('hff);byte_out('h7f);end
    read_reg(12,value,2);if(value!=12)$fatal(1,"FIFO level %d",value);
    expect_data[0]='hab;expect_data[1]='h10;expect_data[2]='h11;expect_data[3]='h12;
    expect_data[4]='h13;expect_data[5]='h91;
    for(i=6;i<12;i++)expect_data[i]='h20+i-6;
    for(i=0;i<12;i++)begin
      read_reg(16,value,i%5);
      if(value!=={16'd0,1'b0,(i<6 ? 7'd2:7'd3),expect_data[i]})$fatal(1,"FIFO byte index=%d value=%h",i,value);
    end
    read_reg(16,value,0);if(value!==32'h80000000)$fatal(1,"empty FIFO should return marker");
    read_reg(12,value,0);if(value!=0)$fatal(1,"read popped more than once");
    repeat(24)frame_out(128'h05ab1011121307912021222324250908);
    repeat(40)byte_out(0);read_reg(8,value,0);if(!value[2])$fatal(1,"overflow not exposed to PS");
    write_reg(4,12,0);read_reg(8,value,0);if(value[0] || !value[2])$fatal(1,"stop must retain loss status");
    write_reg(4,14,1);repeat(40)byte_out(0);read_reg(8,value,0);if(value!=8)$fatal(1,"reset status / delay reference readiness");
    read_reg(12,value,0);if(value!=0)$fatal(1,"reset FIFO");
    $display("PASS ORBTrace PS AXI-Lite split AW/W, BRAM data, R stalls, counts, overflow, stop/reset");$finish;
  end
  initial begin #10000000;$fatal(1,"timeout");end
endmodule
