`timescale 1ns/1ps
module tb_orbtrace_ddr_writer;
  reg clk=0;always #5 clk=!clk;
  reg rst_n=0,start=0,abort=0,finish_empty=0;
  reg [31:0] base_address=32'h10000000,byte_limit=8192;
  wire busy,done,error,command_rejected;wire [3:0] error_code;
  wire [31:0] accepted_bytes,response_bytes;
  reg [63:0] tdata=0;reg [7:0] tkeep=0;reg tlast=0,tvalid=0;wire tready;
  wire [31:0] awaddr;wire [7:0] awlen;wire [2:0] awsize;wire [1:0] awburst;
  wire awvalid,wlast,wvalid,bready;wire [63:0] wdata;wire [7:0] wstrb;
  reg awready=0,wready=0,bvalid=0;reg [1:0] bresp=0,response_code=0;
  orbtrace_ddr_writer #(.REGION_BASE(32'h10000000),.REGION_END(32'h30000000)) dut(.clk(clk),.rst_n(rst_n),.start(start),.abort(abort),.finish_empty(finish_empty),
    .base_address(base_address),.byte_limit(byte_limit),.busy(busy),.done(done),.error(error),.error_code(error_code),
    .command_rejected(command_rejected),.accepted_bytes(accepted_bytes),.response_bytes(response_bytes),
    .s_axis_tdata(tdata),.s_axis_tkeep(tkeep),.s_axis_tlast(tlast),.s_axis_tvalid(tvalid),.s_axis_tready(tready),
    .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
    .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),
    .m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready));
  reg [7:0] memory[0:8191];
  integer cycle=0,aw_count=0,beats=0,expected_beats=0,bdelay=-1,written=0;
  integer tests=0,i,j,offset,pattern_bias=0,previous_written;
  reg [7:0] following_guard;
  reg outstanding=0,force_awstall=0,force_wstall=0,force_bhold=0;
  reg [31:0] transaction_address;
  reg aw_blocked=0,w_blocked=0;
  reg [39:0] held_aw;reg [72:0] held_w;
  reg [31:0] old_response;
  reg acknowledged,new_capture;
  always @(negedge clk)begin
    awready=rst_n && !force_awstall && !outstanding && (cycle%5!=1);
    wready=rst_n && !force_wstall && outstanding && (cycle%3!=1);
  end
  always @(posedge clk)begin
    cycle=cycle+1;
    if(cycle>200000)$fatal(1,"global timeout");
    if(!rst_n)begin
      aw_count=0;beats=0;expected_beats=0;bdelay=-1;written=0;outstanding=0;bvalid<=0;bresp<=0;
      aw_blocked=0;w_blocked=0;old_response=0;
    end else begin
      if(aw_blocked && (!awvalid || {awaddr,awlen}!==held_aw))$fatal(1,"AW changed under backpressure");
      if(w_blocked && (!wvalid || {wdata,wstrb,wlast}!==held_w))$fatal(1,"W changed under backpressure/abort");
      aw_blocked=awvalid&&!awready;held_aw={awaddr,awlen};
      w_blocked=wvalid&&!wready;held_w={wdata,wstrb,wlast};
      if(awvalid&&awready)begin
        if(outstanding || awsize!=3 || awburst!=1 || awlen>15)$fatal(1,"illegal AXI burst");
        if(awaddr[11:0]+(awlen+1)*8>4096)$fatal(1,"4KiB crossing");
        if(awaddr<base_address || awaddr>=base_address+byte_limit)$fatal(1,"AW outside capture");
        transaction_address=awaddr;beats=0;expected_beats=awlen+1;outstanding=1;aw_count=aw_count+1;
      end
      if(wvalid&&wready)begin
        if(!outstanding || beats>=expected_beats)$fatal(1,"unaddressed/extra W");
        if(wlast!==(beats==expected_beats-1))$fatal(1,"WLAST mismatch");
        for(j=0;j<8;j=j+1)if(wstrb[j])begin
          offset=transaction_address-base_address+8*beats+j;
          if(offset<0 || offset>=byte_limit || offset>=8192)$fatal(1,"byte outside capture");
          memory[offset]=wdata[j*8+:8];written=written+1;
        end
        beats=beats+1;
        if(wlast)bdelay=19;
      end
      acknowledged=bvalid&&bready&&bresp==0;
      new_capture=start && !busy;
      if(bvalid&&bready)begin bvalid<=0;outstanding=0;end
      else if(bdelay==0 && !force_bhold)begin bvalid<=1;bresp<=response_code;bdelay=-1;end
      else if(bdelay>0)bdelay=bdelay-1;
      old_response=response_bytes;
      #1;
      if(busy && accepted_bytes+dut.remaining_bytes!=dut.limit)$fatal(1,"budget conservation");
      if(response_bytes>old_response && !acknowledged)$fatal(1,"response count advanced before OKAY B");
      if(response_bytes<old_response && !new_capture)$fatal(1,"response count reset without a new capture");
      if(done && outstanding)$fatal(1,"completion with outstanding AXI write");
    end
  end
  task reset_case;
    begin
      @(negedge clk);rst_n=0;start=0;abort=0;finish_empty=0;tvalid=0;tlast=0;tkeep=0;
      force_awstall=0;force_wstall=0;force_bhold=0;response_code=0;
      repeat(3)@(negedge clk);
      for(i=0;i<8192;i=i+1)memory[i]=8'hcc;
      base_address=32'h10000000;byte_limit=8192;rst_n=1;
    end
  endtask
  task launch;
    begin @(negedge clk);start=1;@(negedge clk);start=0;end
  endtask
  task send_beat(input integer position,input integer n,input reg last);
    integer k;begin
      @(negedge clk);
      for(k=0;k<8;k=k+1)tdata[k*8+:8]=((position+k)*13+7+pattern_bias)&255;
      tkeep=(9'b1<<n)-1;tlast=last;tvalid=1;
      @(posedge clk);while(!tready)@(posedge clk);
      @(negedge clk);tvalid=0;
    end
  endtask
  task await_terminal;
    integer deadline;begin
      deadline=0;
      while(busy && deadline<20000)begin @(negedge clk);deadline=deadline+1;end
      if(busy)$fatal(1,"writer did not terminate");
    end
  endtask
  task verify_bytes(input integer count);
    integer k;begin
      for(k=0;k<count;k=k+1)if(memory[k]!==((k*13+7+pattern_bias)&255))$fatal(1,"memory mismatch at %0d",k);
      if(count<8192 && memory[count]!==8'hcc)$fatal(1,"overwrote byte after payload");
    end
  endtask
  task normal(input integer n,input reg boundary);
    integer p,b;begin
      reset_case();byte_limit=n;if(boundary)base_address=32'h10000f80;
      launch();
      for(p=0;p<n;p=p+8)begin b=(n-p<8)?n-p:8;send_beat(p,b,p+b==n);end
      await_terminal();
      if(error || accepted_bytes!=n || response_bytes!=n || written!=n)$fatal(1,"normal counts n=%0d a=%0d b=%0d err=%0d",n,accepted_bytes,response_bytes,error_code);
      verify_bytes(n);tests=tests+1;$display("PASS length=%0d boundary=%0d bursts=%0d",n,boundary,aw_count);
    end
  endtask
  initial begin
    normal(1,0);normal(2,0);normal(7,0);normal(8,0);normal(9,0);normal(127,0);normal(128,0);normal(129,0);
    normal(255,0);normal(256,0);normal(257,0);normal(4096,1);normal(8192,0);
    reset_case();base_address=32'h2fffff80;byte_limit=128;launch();
    for(integer p=0;p<128;p=p+8)send_beat(p,8,p==120);
    await_terminal();verify_bytes(128);if(error || response_bytes!=128)$fatal(1,"region end");tests=tests+1;
    reset_case();byte_limit=0;launch();if(busy || !error || !command_rejected || aw_count)$fatal(1,"zero limit");tests=tests+1;
    reset_case();base_address=32'h00001000;launch();if(busy || !error || aw_count)$fatal(1,"low address");tests=tests+1;
    reset_case();base_address=32'h10000008;launch();if(busy || !error || aw_count)$fatal(1,"unaligned base");tests=tests+1;
    reset_case();base_address=32'h2fffff80;byte_limit=129;launch();if(busy || !error || aw_count)$fatal(1,"region overflow");tests=tests+1;
    reset_case();launch();@(negedge clk);finish_empty=1;@(negedge clk);finish_empty=0;
    await_terminal();if(error || response_bytes || accepted_bytes || aw_count)$fatal(1,"empty capture");tests=tests+1;
    reset_case();byte_limit=8;force_bhold=1;launch();send_beat(0,8,1);
    repeat(60)@(negedge clk);
    if(!busy || done || response_bytes)$fatal(1,"completed before B");
    force_bhold=0;await_terminal();if(error || response_bytes!=8)$fatal(1,"late B");tests=tests+1;
    reset_case();byte_limit=128;response_code=2;launch();
    for(integer p=0;p<128;p=p+8)send_beat(p,8,p==120);
    await_terminal();if(!error || error_code!=4 || response_bytes || aw_count!=1)$fatal(1,"BRESP error/retry");tests=tests+1;
    reset_case();byte_limit=256;force_awstall=1;launch();
    for(integer p=0;p<128;p=p+8)send_beat(p,8,0);
    wait(awvalid);@(negedge clk);abort=1;@(negedge clk);abort=0;
    repeat(10)@(negedge clk);if(!busy || !awvalid)$fatal(1,"abort withdrew AW");
    force_awstall=0;await_terminal();if(!error || error_code!=5 || response_bytes!=128 || aw_count!=1)$fatal(1,"AW abort drain");tests=tests+1;
    reset_case();byte_limit=256;force_wstall=1;launch();
    for(integer p=0;p<128;p=p+8)send_beat(p,8,0);
    wait(wvalid);@(negedge clk);abort=1;@(negedge clk);abort=0;
    repeat(10)@(negedge clk);if(!busy || !wvalid)$fatal(1,"abort withdrew W");
    force_wstall=0;await_terminal();if(!error || response_bytes!=128 || aw_count!=1)$fatal(1,"W abort drain");tests=tests+1;
    reset_case();launch();send_beat(0,8,0);@(negedge clk);abort=1;@(negedge clk);abort=0;
    await_terminal();if(!error || response_bytes || aw_count)$fatal(1,"partial unissued abort");tests=tests+1;
    reset_case();launch();send_beat(0,3,0);await_terminal();if(!error || error_code!=2 || aw_count)$fatal(1,"short nonlast");tests=tests+1;
    reset_case();launch();@(negedge clk);tvalid=1;tkeep=8'h55;tlast=1;@(negedge clk);tvalid=0;
    await_terminal();if(!error || error_code!=2 || aw_count)$fatal(1,"sparse keep");tests=tests+1;
    // The writer no longer enforces arbitrary byte quotas on every beat.
    // A malformed source still cannot issue a burst beyond the hard region.
    reset_case();base_address=32'h2fffff80;byte_limit=128;launch();
    for(integer p=0;p<256;p=p+8)send_beat(p,8,p==248);
    await_terminal();if(!error || error_code!=3 || aw_count!=1 || response_bytes!=128)$fatal(1,"hard region guard");
    verify_bytes(128);tests=tests+1;
    reset_case();force_awstall=1;byte_limit=128;launch();
    for(integer p=0;p<128;p=p+8)send_beat(p,8,p==120);
    wait(awvalid);launch();if(!command_rejected)$fatal(1,"busy restart accepted");
    force_awstall=0;await_terminal();verify_bytes(128);if(error || response_bytes!=128)$fatal(1,"restart corrupted capture");tests=tests+1;
    // Reuse the complete writer/RAM repeatedly without reset, with changed
    // byte counts and contents. Stale bank flags/counts/data must not survive.
    for(integer round=0;round<64;round=round+1)begin
      byte_limit=(round*37)%1024+1;pattern_bias=round+1;
      following_guard=memory[byte_limit];previous_written=written;
      launch();
      for(integer p=0;p<byte_limit;p=p+8)send_beat(p,(byte_limit-p<8)?byte_limit-p:8,p+8>=byte_limit);
      await_terminal();
      if(error || command_rejected || accepted_bytes!=byte_limit || response_bytes!=byte_limit || written-previous_written!=byte_limit)$fatal(1,"repeat capture counts/flags");
      for(integer k=0;k<byte_limit;k=k+1)if(memory[k]!==((k*13+7+pattern_bias)&255))$fatal(1,"stale capture data round=%0d byte=%0d",round,k);
      if(memory[byte_limit]!==following_guard)$fatal(1,"repeated capture overwrote tail");
      tests=tests+1;
    end
    $display("PASS ALL DDR writer cases=%0d",tests);$finish;
  end
endmodule
