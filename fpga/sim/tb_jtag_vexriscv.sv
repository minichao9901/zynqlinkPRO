`timescale 1ns/1ps
// Drive the probe's jtag_core against a real open-source RISC-V TAP (VexRiscv).
// VexRiscv's JtagBridge has a 4-bit IR (IDCODE=0001) and a 32-bit IDCODE of
// 0x10001FFF, i.e. exactly the "bare 32-bit DR, no ADIv5 padding" case.
//
// Dependency: the generated core is vendored in reference/vexriscv/vexriscv.v.
// Source identity and upstream license are recorded in docs/required-dependencies.json.
// Run from any scratch directory:
//   xvlog -sv fpga/rtl/jtag_core.v fpga/rtl/jtag_shift.v \
//          reference/vexriscv/vexriscv.v fpga/sim/tb_jtag_vexriscv.sv
//   xelab tb_jtag_vexriscv -s sim_vex && xsim sim_vex -runall
module tb_jtag_vexriscv;
    reg clk=0;always #4.166667 clk=~clk;
    reg rst_n=0,start=0,invalidate=0,fence=0;
    reg [2:0] op=0;reg [7:0] req=0;reg [31:0] wd=0;
    reg [8:0] seq_count=0;reg [255:0] seq_data=0;reg seq_tms=0;
    reg [7:0] irlen=4,db=0,da=0;reg [10:0] ib=0,ia=0;
    reg [3:0] delay=0;wire busy,valid,tck,tms,tdi,fd,fe;
    reg [7:0] idcode_ir=8'h01;
    reg late_return=0;
    wire [2:0] ack;wire [31:0] data;wire [255:0] seq_result;
    wire jtag_tdo_core;      // from the CPU TAP
    reg  tdo_pad=1;
    always @(jtag_tdo_core) tdo_pad<=#3 jtag_tdo_core;
    jtag_core dut(.clk(clk),.rst_n(rst_n),.start(start),.invalidate(invalidate),.operation(op),
        .request(req),.wdata(wd),.seq_count(seq_count),.seq_data(seq_data),.seq_tms(seq_tms),
        .ir_length(irlen),.ir_before(ib),.ir_after(ia),.dr_before(db),.dr_after(da),
        .idcode_ir(idcode_ir),.riscv_mode(1'b0),
        .half_delay(delay),.idle_cycles(4'd1),.late_return(late_return),.tdo(tdo_pad),
        .next_valid(1'b0),.next_request(8'd0),.next_wdata(32'd0),.next_ready(),
        .result_valid(valid),.busy(busy),.ack(ack),.rdata(data),.tck(tck),.tms(tms),.tdi(tdi),
        .sequence_result(seq_result),.fence_req(fence),.fence_done(fd),.fence_error(fe));
    VexRiscvAxi4 cpu(
        .clk(clk),.reset(!rst_n),.debugReset(1'b0),.debug_resetOut(),
        .timerInterrupt(1'b0),.externalInterrupt(1'b0),.softwareInterrupt(1'b0),
        .jtag_tck(tck),.jtag_tms(tms),.jtag_tdi(tdi),.jtag_tdo(jtag_tdo_core),
        .iBusAxi_ar_ready(1'b0),.iBusAxi_r_valid(1'b0),.iBusAxi_r_payload_data(32'd0),
        .iBusAxi_r_payload_id(1'b0),.iBusAxi_r_payload_resp(2'd0),.iBusAxi_r_payload_last(1'b0),
        .dBusAxi_aw_ready(1'b0),.dBusAxi_w_ready(1'b0),.dBusAxi_b_valid(1'b0),
        .dBusAxi_b_payload_id(1'b0),.dBusAxi_b_payload_resp(2'd0),
        .dBusAxi_ar_ready(1'b0),.dBusAxi_r_valid(1'b0),.dBusAxi_r_payload_data(32'd0),
        .dBusAxi_r_payload_id(1'b0),.dBusAxi_r_payload_resp(2'd0),.dBusAxi_r_payload_last(1'b0));
    integer tck_edges=0, edges_mark=0, edges_last=0, i;
    always @(posedge tck) tck_edges<=tck_edges+1;
    task call(input [2:0] operation,input [7:0] request,input [31:0] value,input [2:0] expected_ack);
        integer budget;
        begin
            @(negedge clk);edges_mark=tck_edges;op=operation;req=request;wd=value;start=1;
            @(negedge clk);start=0;budget=0;
            while(!valid && budget<20000) begin @(negedge clk);budget=budget+1;end
            if(!valid) $fatal(1,"JTAG timeout state=%d",dut.state);
            if(ack!==expected_ack) $fatal(1,"JTAG ack op=%d got=%x expected=%x",operation,ack,expected_ack);
            @(negedge clk);edges_last=tck_edges-edges_mark;
        end
    endtask
    initial begin
        repeat(20) @(negedge clk);rst_n=1;
        repeat(20) @(negedge clk);
        call(3,0,0,1);
        if(data!==32'h10001FFF) $fatal(1,"VexRiscv IDCODE got %x expected 10001FFF",data);
        $display("PASS vexriscv idcode data=%x tck_per_scan=%0d",data,edges_last);
        call(3,0,0,1);
        if(data!==32'h10001FFF) $fatal(1,"VexRiscv IDCODE repeat got %x",data);
        $display("PASS vexriscv idcode repeat data=%x tck_per_scan=%0d",data,edges_last);
        // Steady-state cost of repeated 32-bit DR exchanges (IR stays loaded when
        // the core can reuse its cache), reported as TCK cycles per exchange.
        edges_mark=tck_edges;
        for(i=0;i<100;i=i+1) call(3,0,0,1);
        $display("COST %0d scans in %0d tck (%.2f tck/scan)",100,tck_edges-edges_mark,
                 (tck_edges-edges_mark)/100.0);
        $finish;
    end
    initial begin
        #5000000; $fatal(1,"global timeout");
    end
endmodule
