`timescale 1ns/1ps
module tb_jtag_core;
    reg clk=0;always #4.166667 clk=~clk;
    reg rst_n=0,start=0,invalidate=0,fence=0;
    reg [2:0] op=0;reg [7:0] req=0;reg [31:0] wd=0;
    reg [8:0] seq_count=0;reg [255:0] seq_data=0;reg seq_tms=0;
    reg [7:0] irlen=4,db=0,da=0;reg [10:0] ib=0,ia=0;
    reg [3:0] delay=0;wire busy,valid,nready,tck,tms,tdi,tdo,fd,fe;
    reg late_return=0;
    wire [2:0] ack;wire [31:0] data;reg chain=0;
    wire [255:0] seq_result;
    jtag_core dut(.idcode_ir(8'h0e),.riscv_mode(1'b0),.clk(clk),.rst_n(rst_n),.start(start),.invalidate(invalidate),.operation(op),.request(req),.wdata(wd),
        .seq_count(seq_count),.seq_data(seq_data),.seq_tms(seq_tms),.ir_length(irlen),.ir_before(ib),.ir_after(ia),
        .dr_before(db),.dr_after(da),.half_delay(delay),.idle_cycles(4'd1),.late_return(late_return),.tdo(tdo),.next_valid(1'b0),
        .next_request(8'd0),.next_wdata(32'd0),.next_ready(nready),.result_valid(valid),.busy(busy),
        .ack(ack),.rdata(data),.tck(tck),.tms(tms),.tdi(tdi),.sequence_result(seq_result),
        .fence_req(fence),.fence_done(fd),.fence_error(fe));
    wire tdummy,tdap;reg tdo_fast=1,tdo_slow=1;reg dummy_first=0;
    wire dap_in=chain && !dummy_first ? tdummy : tdi;
    wire dummy_in=dummy_first ? tdap : tdi;
    wire tap_output=chain && dummy_first ? tdummy : tdap;
    always @(tap_output) begin tdo_fast<=#12 tap_output;tdo_slow<=#28 tap_output;end
    reg fast_disable=0;
    assign tdo=fast_disable && ap.state!=4 && ap.state!=11 ? 1'b1 : late_return ? tdo_slow : tdo_fast;
    jtag_dp_model #(.RETURN_NS(0)) ap(.rst_n(rst_n),.tck(tck),.tms(tms),.tdi(dap_in),.tdo(tdap));
    jtag_dp_model #(.IRLEN(5),.DUMMY(1),.RETURN_NS(0)) dummy(.rst_n(rst_n),.tck(tck),.tms(tms),.tdi(dummy_in),.tdo(tdummy));
    task call(input [2:0] operation,input [7:0] request,input [31:0] value,input [2:0] expected_ack);
        integer budget;
        begin
            @(negedge clk);op=operation;req=request;wd=value;start=1;
            @(negedge clk);start=0;budget=0;
            while(!valid && budget<20000) begin @(negedge clk);budget=budget+1;end
            if(!valid) $fatal(1,"JTAG timeout state=%d",dut.state);
            if(ack!==expected_ack) $fatal(1,"JTAG ack op=%d req=%x got=%x expected=%x",operation,request,ack,expected_ack);
            @(negedge clk);
        end
    endtask
    task configure_mem;
        call(0,8'h08,0,1);call(0,8'h01,32'h23000012,1);call(0,8'h05,32'h20000000,1);
    endtask
    task read_pattern;
        integer i,before_scans;
        begin configure_mem();call(0,8'h0f,0,1);before_scans=ap.scans;
        for(i=0;i<16;i=i+1) begin
            call(0,i==15 ? 8'h0e : 8'h0f,0,1);
            if(data!==32'h12340000+i) $fatal(1,"posted word %d data=%x",i,data);
        end
        if(ap.scans-before_scans!=18) $fatal(1,"steady path does extra scans %d",ap.scans-before_scans);
        end
    endtask
    integer i;reg [31:0] saved;
    initial begin
        for(i=0;i<8192;i=i+1) ap.mem[i]=32'h12340000+i;
        repeat(5) @(negedge clk);rst_n=1;
        call(3,0,0,1);if(data!==32'h4ba00477) $fatal(1,"IDCODE %x",data);
        call(0,4,32'h50000000,1);call(0,6,0,1);if(data!==32'hf0000000) $fatal(1,"DP read is stale %x",data);
        read_pattern();
        configure_mem();call(0,13,32'habcdef01,1);call(0,14,0,1);
        if(ap.mem[0]!==32'habcdef01) $fatal(1,"write not completed");ap.mem[0]=32'h12340000;
        configure_mem();ap.wait_scans=2;call(0,15,0,2);call(0,15,0,2);call(0,15,0,1);call(0,14,0,1);
        if(data!==32'h12340000) $fatal(1,"WAIT consumed a request %x",data);
        configure_mem();ap.fault_next=1;call(0,15,0,1);call(0,14,0,4);
        call(0,0,32'h1e,1);call(0,6,0,1);if(!(data & 32'h20)) $fatal(1,"DPv0 JTAG ABORT incorrectly clears sticky status");
        call(0,4,32'h50000032,1);call(0,6,0,1);if(data & 32'ha2) $fatal(1,"CTRLSTAT W1C failed");
        // A packet fence preserves the outstanding AP result for the next DRW.
        configure_mem();call(0,15,0,1);fence=1;wait(fd);if(fe) $fatal(1,"fence failed");
        @(negedge clk);fence=0;wait(!busy);call(0,15,0,1);if(data!==32'h12340000) $fatal(1,"fence shifted posted data");
        // CMSIS raw scans may exit SHIFT on their captured final bit. A TAP
        // that disables TDO immediately after that rising edge must still
        // return the final zero, rather than the pull-up value.
        call(3,0,0,1);fast_disable=1;seq_data=~256'd0;
        seq_tms=1;seq_count=1;call(5,2,0,1);
        seq_tms=0;seq_count=2;call(5,2,0,1);
        seq_count=31;call(5,2,0,1);
        if(seq_result[30:0]!==31'h4ba00477)$fatal(1,"raw IDCODE prefix %h",seq_result[30:0]);
        seq_tms=1;seq_count=1;call(5,2,0,1);
        if(seq_result[0]!==0)$fatal(1,"raw final TDO bit lost at EXIT1");
        fast_disable=0;
        // Both sides of a multi-device chain need correctly placed IR/DR bypass.
        delay=1;chain=1;ib=5;db=1;ia=0;da=0;dummy_first=1;
        @(negedge clk);invalidate=1;@(negedge clk);invalidate=0;read_pattern();
        ib=0;db=0;ia=5;da=1;dummy_first=0;
        @(negedge clk);invalidate=1;@(negedge clk);invalidate=0;read_pattern();
        // 28 ns round trip exceeds a 60 MHz TCK period. Cover both bypass
        // positions and verify that padded scans do not corrupt AP writes.
        late_return=1;delay=0;ib=5;db=1;ia=0;da=0;dummy_first=1;
        @(negedge clk);invalidate=1;@(negedge clk);invalidate=0;read_pattern();
        call(3,0,0,1);if(data!==32'h4ba00477)$fatal(1,"late IDCODE %x",data);
        configure_mem();call(0,13,32'habcdef01,1);call(0,14,0,1);
        if(ap.mem[0]!==32'habcdef01)$fatal(1,"late write padding corrupts data");ap.mem[0]=32'h12340000;
        ib=0;db=0;ia=5;da=1;dummy_first=0;
        @(negedge clk);invalidate=1;@(negedge clk);invalidate=0;read_pattern();
        $display("PASS JTAG core: delayed TDO, IDCODE, current DP reads, one scan/AP word, posted tail, WAIT, sticky FAULT/ABORT, fence, chain bypass");$finish;
    end
    initial begin #50000000;$fatal(1,"JTAG test watchdog");end
endmodule
