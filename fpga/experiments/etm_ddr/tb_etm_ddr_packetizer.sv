`timescale 1ns/1ps
module tb_etm_ddr_packetizer;
  reg clk=0;always #4 clk=~clk;
  reg rst=1,start=0,ready=0;
  reg [31:0] byte_limit=8192;
  reg [127:0] frame_data=0;
  reg [4:0] frame_bytes=0;
  reg frame_last=0,frame_valid=0;
  wire frame_ready,busy,done,empty,rejected,error,limited,valid,last;
  wire [63:0] data;wire [7:0] keep;wire [31:0] accepted,delivered;
  etm_ddr_packetizer dut(.clk(clk),.rst(rst),.start(start),.byte_limit(byte_limit),.busy(busy),.done(done),.empty(empty),
    .command_rejected(rejected),.protocol_error(error),.limit_reached(limited),
    .frame_data(frame_data),.frame_bytes(frame_bytes),.frame_last(frame_last),.frame_valid(frame_valid),.frame_ready(frame_ready),
    .m_axis_tdata(data),.m_axis_tkeep(keep),.m_axis_tlast(last),.m_axis_tvalid(valid),.m_axis_tready(ready),
    .input_bytes(accepted),.stream_bytes(delivered));
  integer consumed=0,last_count=0,expected=0,cycles=0,cases=0,i,n;
  reg blocked=0;reg [63:0] held_data;reg [7:0] held_keep;reg held_last;
  reg [31:0] random_state=32'h48da2026;
  reg force_stall=0;
  always @(negedge clk)begin
    random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
    ready=!force_stall && random_state[2:0]!=0;
  end
  always @(posedge clk)begin
    cycles=cycles+1;
    if(!rst)begin
      if(blocked && (!valid || data!==held_data || keep!==held_keep || last!==held_last))
        $fatal(1,"AXIS payload changed under backpressure");
      if(valid && ready)begin
        if(keep==0)$fatal(1,"zero-length DMA beat");
        for(integer b=0;b<8;b=b+1)if(keep[b])begin
          if(data[8*b+:8]!==8'(consumed))$fatal(1,"byte mismatch %d got %h",consumed,data[8*b+:8]);
          consumed=consumed+1;
        end
        if(consumed>expected)$fatal(1,"overwrote allocation");
        if(last)begin last_count=last_count+1;if(consumed!=expected)$fatal(1,"early TLAST");end
      end
    end
    blocked=!rst && valid && !ready;held_data=data;held_keep=keep;held_last=last;
  end
  task reset_case(input integer length,input integer budget);
    begin
      @(negedge clk);rst=1;start=0;frame_valid=0;force_stall=0;
      repeat(3)@(negedge clk);consumed=0;last_count=0;expected=length;rst=0;byte_limit=budget;
      start=1;@(negedge clk);start=0;wait(busy);
    end
  endtask
  task send(input integer offset,input integer length,input bit final_frame);
    begin
      @(negedge clk);for(integer b=0;b<16;b=b+1)frame_data[8*b+:8]=8'(offset+b);
      frame_bytes=length;frame_last=final_frame;frame_valid=1;
      do @(posedge clk);while(!frame_ready);
      @(negedge clk);frame_valid=0;
    end
  endtask
  task finish_case(input bit expected_limit);
    integer wait_cycles;
    begin
      wait_cycles=0;
      while(busy && wait_cycles<20000)begin @(negedge clk);wait_cycles=wait_cycles+1;end
      if(busy || error || consumed!=expected || delivered!=expected || accepted!=expected)
        $fatal(1,"capture length/finish mismatch expected=%d consumed=%d accepted=%d delivered=%d",expected,consumed,accepted,delivered);
      if(last_count!=(expected==0 ? 0:1) || empty!=(expected==0) || limited!=expected_limit)$fatal(1,"termination mismatch");
      cases=cases+1;
    end
  endtask
  initial begin
    for(n=0;n<33;n=n+1)begin
      reset_case(n,8192);
      for(i=0;i+16<=n;i=i+16)send(i,16,0);
      send(i,n-i,1);finish_case(0);
    end
    reset_case(4096,8192);
    for(i=0;i<4096;i=i+16)send(i,16,i==4080);
    finish_case(0);
    // USB is not part of this frontend. A long downstream/DMA stall must
    // preserve the pending last beat and propagate FIFO backpressure.
    reset_case(32,8192);force_stall=1;send(0,16,0);
    fork
      begin repeat(1000)@(negedge clk);force_stall=0;end
      begin send(16,16,1);end
    join
    finish_case(0);
    // A stopped source can leave the final full beat pending until EOF.
    reset_case(16,8192);send(0,16,0);repeat(400)@(negedge clk);
    if(!busy || last_count!=0 || consumed>8)$fatal(1,"fabricated end during source silence");
    send(16,0,1);finish_case(0);
    reset_case(19,19);send(0,16,0);send(16,16,0);finish_case(1);
    reset_case(1,1);send(0,16,0);finish_case(1);
    reset_case(16,8192);send(0,16,1);@(negedge clk);start=1;@(negedge clk);start=0;
    finish_case(0);if(!rejected)$fatal(1,"busy start accepted");
    reset_case(0,8192);send(0,17,1);repeat(5)@(negedge clk);
    if(!error || valid || busy)$fatal(1,"malformed frame was accepted");
    $display("PASS DDR AXIS64 packetizer: %0d lengths/limits/stalls/EOF/busy cases, no empty TLAST or byte loss",cases);$finish;
  end
  initial begin #2000000;$fatal(1,"timeout");end
endmodule
