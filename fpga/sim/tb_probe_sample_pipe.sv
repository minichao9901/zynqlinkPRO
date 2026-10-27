`timescale 1ns/1ps
module tb_probe_sample_pipe;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,wr=0,rd=0,chain=1;reg [2:0] wa=0,ra=0;
    reg [31:0] wd=0;wire [31:0] data,cr;
    wire active,start,nvalid,busy,valid,nready,parity;
    wire [7:0] req,nreq;wire [31:0] cw;wire [2:0] ack;
    probe_sample_engine dut(.clk(clk),.rst_n(rst_n),.wr(wr),.rd(rd),.waddr(wa),.raddr(ra),.wdata(wd),.rdata(data),
        .available(!busy),.stream_pop(1'b0),.active(active),.core_start(start),.core_req(req),.core_wdata(cw),
        .core_next_valid(nvalid),.core_next_req(nreq),.core_busy(busy),.core_result_valid(valid),.core_next_ready(nready),
        .core_ack(ack),.core_parity_err(parity),.core_rdata(cr));
    probe_ap_model ap(.clk(clk),.rst_n(rst_n),.start(start),.next_valid(nvalid),.chain_enable(chain),.req(req),.next_req(nreq),
        .wdata(cw),.busy(busy),.result_valid(valid),.next_ready(nready),.ack(ack),.parity(parity),.rdata(cr));
    task write_reg(input integer a,input [31:0] d);@(negedge clk);wa=a;wd=d;wr=1;@(negedge clk);wr=0;endtask
    task read_reg(input integer a,output [31:0] d);@(negedge clk);ra=a;rd=1;#1;d=data;@(negedge clk);rd=0;endtask
    task reset;@(negedge clk);rst_n=0;repeat(4) @(negedge clk);rst_n=1;ap.reads=0;endtask
    task plan(input integer n,input [31:0] base);
        integer i;begin write_reg(6,48000000);write_reg(4,240);
        for(i=0;i<n;i=i+1) begin write_reg(2,i);write_reg(3,base+i*4);end end
    endtask
    task stop_and_check(input integer n,input integer dynamic_values,input [31:0] base);
        integer t,i,j,total;reg [31:0] v,s;
        begin
            t=0;v=0;while(v[31:16]<6 && t<20000) begin read_reg(1,v);t=t+1;end
            if(t==20000) $fatal(1,"sample pipe stuck state=%d phase=%d",dut.state,dut.phase);
            write_reg(0,0);t=0;while(active && t<2000) begin @(negedge clk);t=t+1;end
            if(active) $fatal(1,"posted tail not flushed");read_reg(1,v);total=v[31:16];
            for(i=0;i<total;i=i+1) begin
                read_reg(5,s);
                for(j=0;j<n;j=j+1) begin
                    read_reg(5,v);
                    if(v!=(dynamic_values ? i : 32'habcd0000+((base&'h7fff)/4)+j))
                        $fatal(1,"sample %d word %d got %x",i,j,v);
                end
            end
            if(dynamic_values && total!=ap.reads) $fatal(1,"lost/stale posted tail samples=%d reads=%d",total,ap.reads);
        end
    endtask
    integer i;
    initial begin
        for(i=0;i<8192;i=i+1) ap.mem[i]=32'habcd0000+i;
        reset();ap.dynamic_data=1;plan(1,32'h20000100);write_reg(0,257);
        wait(dut.state==2 && dut.phase==5);ap.inject_wait=1;stop_and_check(1,1,32'h20000100);
        reset();ap.dynamic_data=0;plan(3,32'h20000100);write_reg(0,769);stop_and_check(3,0,32'h20000100);
        reset();chain=0;plan(3,32'h20000100);write_reg(0,769);
        wait(dut.state==2 && dut.phase==5);ap.inject_wait=1;stop_and_check(3,0,32'h20000100);
        reset();chain=1;plan(3,32'h200003fc);write_reg(0,769);stop_and_check(3,0,32'h200003fc);
        $display("PASS sampler pipe: changing values, one DRW/sample, final posted flush, contiguous gather, next_ready fallback, WAIT and 1KiB split");$finish;
    end
    initial begin #10000000;$fatal(1,"watchdog");end
endmodule
