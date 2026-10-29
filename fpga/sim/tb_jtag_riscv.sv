`timescale 1ns/1ps
// RISC-V DTM smoke test for the configurable IDCODE instruction.
// Checks that op=3 loads idcode_ir (0x01) and returns the DTM IDCODE, and that
// pointing the same op at a non-IDCODE instruction falls into BYPASS.
module tb_jtag_riscv;
    reg clk=0;always #4.166667 clk=~clk;
    reg rst_n=0,start=0,invalidate=0,fence=0;
    reg [2:0] op=0;reg [7:0] req=0;reg [31:0] wd=0;
    reg [8:0] seq_count=0;reg [255:0] seq_data=0;reg seq_tms=0;
    reg [7:0] irlen=5,db=0,da=0;reg [10:0] ib=0,ia=0;
    reg [3:0] delay=0;wire busy,valid,tck,tms,tdi,fd,fe;
    reg [7:0] idcode_ir=8'h01;
    reg late_return=0;
    wire [2:0] ack;wire [31:0] data;wire [255:0] seq_result;
    wire tap_out;                      // DTM drives this
    reg tdo_pad=1;                     // pad-level TDO seen by the core
    always @(tap_out) tdo_pad<=#3 tap_out;
    jtag_core dut(.clk(clk),.rst_n(rst_n),.start(start),.invalidate(invalidate),.operation(op),
        .request(req),.wdata(wd),.seq_count(seq_count),.seq_data(seq_data),.seq_tms(seq_tms),
        .ir_length(irlen),.ir_before(ib),.ir_after(ia),.dr_before(db),.dr_after(da),
        .idcode_ir(idcode_ir),.riscv_mode(1'b0),
        .half_delay(delay),.idle_cycles(4'd1),.late_return(late_return),.tdo(tdo_pad),
        .next_valid(1'b0),.next_request(8'd0),.next_wdata(32'd0),.next_ready(),
        .result_valid(valid),.busy(busy),.ack(ack),.rdata(data),.tck(tck),.tms(tms),.tdi(tdi),
        .sequence_result(seq_result),.fence_req(fence),.fence_done(fd),.fence_error(fe));
    jtag_dtm_model #(.IRLEN(5),.IDCODE(32'h1000563D),.RETURN_NS(0)) dtm(
        .rst_n(rst_n),.tck(tck),.tms(tms),.tdi(tdi),.tdo(tap_out));
    task call(input [2:0] operation,input [7:0] request,input [31:0] value,input [2:0] expected_ack);
        integer budget;
        begin
            @(negedge clk);op=operation;req=request;wd=value;start=1;
            @(negedge clk);start=0;budget=0;
            while(!valid && budget<20000) begin @(negedge clk);budget=budget+1;end
            if(!valid) $fatal(1,"JTAG timeout state=%d",dut.state);
            if(ack!==expected_ack) $fatal(1,"JTAG ack op=%d got=%x expected=%x",operation,ack,expected_ack);
            @(negedge clk);
        end
    endtask
    initial begin
        repeat(5) @(negedge clk);rst_n=1;
        // 1) RISC-V IDCODE through IR=0x01.
        call(3,0,0,1);
        if(data!==32'h1000563D) $fatal(1,"IDCODE ir=1 got %x expected 1000563D",data);
        if(dtm.ir!==5'h01) $fatal(1,"DTM saw IR %x expected 01",dtm.ir);
        $display("PASS riscv idcode ir=%x data=%x scans=%0d",dtm.ir,data,dtm.scans);
        // 2) Repeat: must be stable and reuse the cached IR.
        call(3,0,0,1);
        if(data!==32'h1000563D) $fatal(1,"IDCODE repeat got %x",data);
        $display("PASS riscv idcode repeat data=%x",data);
        // 3) A non-IDCODE instruction must fall into BYPASS (zeros), not hang.
        idcode_ir=8'h10;
        call(3,0,0,1);
        if(data!==32'd0) $fatal(1,"BYPASS path got %x expected 0",data);
        if(dtm.ir!==5'h10) $fatal(1,"DTM saw IR %x expected 10",dtm.ir);
        $display("PASS riscv bypass ir=%x data=%x",dtm.ir,data);
        // 4) Back to IDCODE.
        idcode_ir=8'h01;
        call(3,0,0,1);
        if(data!==32'h1000563D) $fatal(1,"IDCODE after bypass got %x",data);
        $display("PASS riscv idcode restore data=%x ir_writes=%0d",data,dtm.ir_writes);
        $finish;
    end
    initial begin
        #2000000; $fatal(1,"global timeout");
    end
endmodule
