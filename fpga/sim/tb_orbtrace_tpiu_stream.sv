`timescale 1ns/1ps
module tb_orbtrace_tpiu_stream #(parameter PHASE=1);
  reg clk=0;always #2.5 clk=~clk;
  reg rst=1;
  reg [7:0] byte_in=0;
  reg byte_toggle=0;
  wire [127:0] frame;
  wire frame_toggle,synced,malformed;
  orbtrace_tpiu_stream dut(.clk(clk),.rst(rst),.byte_in(byte_in),.byte_toggle(byte_toggle),
    .frame(frame),.frame_toggle(frame_toggle),.synced(synced),.malformed(malformed));
  reg [3:0] previous_high=0;
  reg seen=0;
  integer count=0,n,i;
  reg [127:0] expected[0:4];
  always @(negedge clk)if(!rst && frame_toggle!=seen)begin
    seen=frame_toggle;
    if(count>=5 || frame!==expected[count])$fatal(1,"frame %0d differs: %032x",count,frame);
    count=count+1;
  end
  // Match the physical oversampler's half-nibble phase. A final dummy byte
  // flushes the previous stream byte, rather than fabricating payload.
  task put(input [7:0] value);
    begin
      @(negedge clk);byte_in=PHASE ? {value[3:0],previous_high} : value;byte_toggle=!byte_toggle;
      previous_high=value[7:4];repeat(3)@(negedge clk);
    end
  endtask
  task fsync;begin put('hff);put('hff);put('hff);put('h7f);end endtask
  task hsync;begin put('hff);put('h7f);end endtask
  initial begin
    for(n=0;n<4;n=n+1)begin
      expected[n]=0;
      for(i=0;i<16;i=i+1)expected[n]={expected[n][119:0],8'(16*n+i)};
    end
    repeat(4)@(negedge clk);rst=0;
    fsync();fsync();
    for(n=0;n<4;n=n+1)begin
      if(n==3)fsync();
      for(i=0;i<16;i=i+1)begin
        if(i==4 || i==14)hsync();
        put(16*n+i);
      end
    end
    hsync();put(0);repeat(10)@(negedge clk);
    if(count!=4 || !synced || malformed)$fatal(1,"continuous frames lost: got %0d expected 4",count);
    expected[4]=expected[0];
    put('h12);put('h34);put('h56);put('h78);fsync();
    for(i=0;i<16;i=i+1)put(i);
    hsync();put(0);repeat(10)@(negedge clk);
    if(count!=5 || !synced || !malformed)$fatal(1,"malformed full sync recovery/quality flag");
    $display("PASS TPIU continuous frames, FSYNC, HSYNC, phase, malformed resync/loss");
    $finish;
  end
  initial begin #100000;$fatal(1,"timeout");end
endmodule
