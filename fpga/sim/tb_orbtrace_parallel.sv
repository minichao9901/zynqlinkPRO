`timescale 1ns/1ps
module tb_orbtrace_parallel;
  reg clk=0;always #4.166667 clk=~clk;
  reg traceclk=0,rst=0,ready=1;
  reg [3:0] pins=0;
  reg [1:0] width=3;
  integer pin_count=4,phase=0,received=0,expected_count=0,n,j;
  reg checking=0;
  reg [7:0] expected_data[0:1023];reg [6:0] expected_channel[0:1023];
  wire [7:0] data;wire [6:0] channel;wire valid,synced,overflow;
  orbtrace_parallel dut(.trace_clk(traceclk),.trace_data(pins),.width(width),.clk(clk),.rst(rst),
    .data(data),.channel(channel),.valid(valid),.ready(ready),.synced(synced),.overflow(overflow));
  always @(posedge clk)if(checking && valid && ready)begin
    if(received>=expected_count || data!==expected_data[received] || channel!==expected_channel[received])
      $fatal(1,"scoreboard byte=%0d got=%h ID=%0d expected=%h ID=%0d",received,data,channel,expected_data[received],expected_channel[received]);
    received=received+1;
  end
  // Physical pins are stable before each sampling edge, LSB groups first.
  task group(input [3:0] value);
    begin pins=value;#5;traceclk=~traceclk;#5;end
  endtask
  task byte_out(input [7:0] value);
    integer b;begin for(b=0;b<8;b=b+pin_count)group(value>>b);end
  endtask
  task frame_out(input [127:0] value);
    integer b;begin for(b=15;b>=0;b=b-1)byte_out(value>>(b*8));end
  endtask
  task expect_byte(input [7:0] value,input [6:0] id);
    begin expected_data[expected_count]=value;expected_channel[expected_count]=id;expected_count=expected_count+1;end
  endtask
  task reset_capture;
    begin
      checking=0;rst=1;repeat(6)byte_out(0);rst=0;repeat(6)byte_out(0);
      received=0;expected_count=0;ready=1;
      if(valid || synced || overflow)$fatal(1,"reset did not clear receiver");
    end
  endtask
  task long_sync;
    begin byte_out(8'hff);byte_out(8'hff);byte_out(8'hff);byte_out(8'h7f);end
  endtask
  initial begin
    if($value$plusargs("pins=%d",pin_count))begin end
    if($value$plusargs("phase=%d",phase))begin end
    case(pin_count)1:width=1;2:width=2;4:width=3;default:$fatal(1,"width");endcase
    reset_capture;
    // No output before full sync; acquire on either DDR edge.
    repeat(16)byte_out(8'h12);
    if(valid || synced)$fatal(1,"accepted unsynchronized noise");
    if(phase)group(0);
    long_sync;
    expect_byte('hab,2);for(n='h10;n<='h13;n=n+1)expect_byte(n,2);
    expect_byte('h91,2);for(n='h20;n<='h25;n=n+1)expect_byte(n,3);
    for(n='h30;n<='h3e;n=n+1)expect_byte(n,4);
    checking=1;
    byte_out('h05);byte_out('hab);byte_out('h10);byte_out('h11);
    // Short sync inside a frame is discarded without altering its position.
    byte_out(8'hff);byte_out(8'h7f);
    byte_out('h12);byte_out('h13);byte_out('h07);byte_out('h91);
    byte_out('h20);byte_out('h21);byte_out('h22);byte_out('h23);
    byte_out('h24);byte_out('h25);byte_out('h09);byte_out('h08);
    frame_out(128'h303132333435363738393a3b3c3d3e00);
    // Keep the port idle while output drains.
    repeat(30)begin byte_out(8'hff);byte_out(8'h7f);end
    repeat(100)@(negedge clk);
    if(received!=expected_count || !synced || overflow)$fatal(1,"missing bytes=%0d/%0d sync=%b loss=%b",received,expected_count,synced,overflow);
    // Full sync discards a partial frame. All even data bytes below have their
    // LSB restored from 0xff in the auxiliary byte; they are NOT stream IDs.
    repeat(6)byte_out('h22);long_sync;
    for(n=1;n<=15;n=n+1)expect_byte(n,4);
    frame_out(128'h0002020404060608080a0a0c0c0e0eff);
    repeat(30)begin byte_out(8'hff);byte_out(8'h7f);end
    repeat(100)@(negedge clk);
    if(received!=expected_count || overflow)$fatal(1,"LSB restore/resync failed");
    // Backpressure must hold the visible payload while the FIFO queues frames.
    ready=0;
    for(n=0;n<15;n=n+1)expect_byte('h30+n,4);
    frame_out(128'h303132333435363738393a3b3c3d3e00);
    repeat(10)begin byte_out(8'hff);byte_out(8'h7f);end
    begin reg [14:0] held;held={channel,data};
      repeat(20)begin @(negedge clk);if(!valid || {channel,data}!==held)$fatal(1,"unstable stalled output");end
    end
    ready=1;repeat(100)@(negedge clk);
    if(received!=expected_count || overflow)$fatal(1,"backpressure lost bytes");
    checking=0;ready=0;
    // Deliberate unbounded stall must be reported as loss, then reset cleanly.
    repeat(24)frame_out(128'h303132333435363738393a3b3c3d3e00);
    repeat(20)byte_out(0);
    if(!overflow)$fatal(1,"overflow was silent");
    reset_capture;
    long_sync;
    // Channel 0 must not leak, then a later ID reacquires a useful stream.
    checking=1;expect_byte('hab,2);for(n='h10;n<='h13;n=n+1)expect_byte(n,2);
    expect_byte('h91,2);for(n='h20;n<='h25;n=n+1)expect_byte(n,3);
    frame_out(128'h00000000000000000000000000000000);
    frame_out(128'h05ab1011121307912021222324250908);
    repeat(30)begin byte_out(8'hff);byte_out(8'h7f);end
    repeat(100)@(negedge clk);
    if(received!=expected_count || overflow)$fatal(1,"recovery failed");
    $display("PASS ORBTrace DDR pins=%0d phase=%0d reset/sync/ID/LSB/stall/overflow/recovery",pin_count,phase);$finish;
  end
  initial begin #10000000;$fatal(1,"timeout");end
endmodule
