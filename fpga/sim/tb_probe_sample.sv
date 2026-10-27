`timescale 1ns/1ps
module tb_probe_sample;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,wr=0,rd=0,available=1;
    reg [2:0] addr=0,waddr=0;reg [31:0] wdata=0;
    wire [31:0] rdata;wire active,start;
    wire [7:0] req;wire [31:0] wd;
    reg busy=0,valid=0,parity=0;
    reg [2:0] ack=1;reg [31:0] data=0,tar=0,posted=0;
    integer delay=0,calls=0,waits=0;
    reg inject_wait=0,inject_fault=0,inject_parity=0,hang=0;
    probe_sample_engine #(.FIFO_SAMPLES(4),.TIMEOUT(64),.RETRIES(3)) dut(
        .clk(clk),.rst_n(rst_n),.wr(wr),.rd(rd),.waddr(waddr),.raddr(addr),.wdata(wdata),.rdata(rdata),
        .available(available),.active(active),.core_start(start),.core_req(req),.core_wdata(wd),
        .stream_pop(1'b0),.core_next_ready(1'b0),
        .core_busy(busy),.core_result_valid(valid),.core_ack(ack),.core_parity_err(parity),.core_rdata(data));
    always @(posedge clk) begin
        valid<=0;
        if(start && !busy) begin busy<=1;delay<=5;calls<=calls+1;end
        if(busy && !hang) begin
            if(delay!=0) delay<=delay-1;
            else begin
                busy<=0;valid<=1;ack<=1;parity<=inject_parity;
                if(inject_fault) ack<=4;
                else if(inject_wait) begin ack<=2;inject_wait<=0;waits<=waits+1;end
                else case(req)
                8'h08: if(wd!=0) $fatal(1,"SELECT not AP0 bank0");
                8'h01: if(wd!=32'h23000012) $fatal(1,"CSW not word/increment");
                8'h05: tar<=wd;
                8'h0f: begin data<=posted;posted<=tar^32'hcafe1234;tar<={tar[31:10],tar[9:0]+10'd4};end
                8'h0e: data<=posted;
                default: $fatal(1,"invalid request %x",req);
                endcase
            end
        end
    end
    task write_reg(input [2:0] a,input [31:0] d);
        @(negedge clk);waddr=a;wdata=d;wr=1;@(negedge clk);wr=0;
    endtask
    task read_reg(input [2:0] a,output [31:0] d);
        @(negedge clk);addr=a;rd=1;#1;d=rdata;@(negedge clk);rd=0;
    endtask
    task reset;
        @(negedge clk);rst_n=0;busy=0;hang=0;inject_fault=0;inject_parity=0;
        repeat(4) @(negedge clk);rst_n=1;
    endtask
    task configure;
        write_reg(6,48000000);write_reg(4,48);write_reg(7,32'hffffffe0);
        write_reg(2,0);write_reg(3,32'h200003fc);
        write_reg(2,1);write_reg(3,32'h20000400);
        write_reg(2,2);write_reg(3,32'h20000004);
    endtask
    reg [31:0] value,stamp,previous,skipped;integer n,j,prior_calls;
    initial begin
        reset();configure();
        available=0;write_reg(0,32'h301);if(active) $fatal(1,"enabled on occupied core");
        available=1;inject_wait=1;write_reg(0,32'h301);
        write_reg(4,1000);addr=4;#1;if(rdata!=48) $fatal(1,"active period changed");
        repeat(4000) @(negedge clk);
        read_reg(1,value);if(value[31:16]!=4) $fatal(1,"FIFO occupancy %x",value);
        read_reg(7,skipped);if(skipped==0 || waits!=1) $fatal(1,"missed WAIT/overrun accounting");
        prior_calls=calls;repeat(600) @(negedge clk);
        if(calls!=prior_calls) $fatal(1,"full FIFO still reads target");
        // Stop retains complete records and does not destroy the in-flight result.
        write_reg(0,0);repeat(200) @(negedge clk);if(active) $fatal(1,"stop stuck");
        // Independent AXI read/write channels can handshake on the same edge.
        @(negedge clk);waddr=2;wdata=3;wr=1;addr=7;rd=1;#1;value=rdata;
        if(value<skipped) $fatal(1,"simultaneous read used write address");
        @(negedge clk);wr=0;rd=0;
        previous=0;
        for(n=0;n<4;n=n+1) begin
            read_reg(5,stamp);if(n!=0 && $signed(stamp-previous)<=0) $fatal(1,"timestamp order");previous=stamp;
            for(j=0;j<3;j=j+1) begin
                read_reg(5,value);
                if(value != ((j==0 ? 32'h200003fc : j==1 ? 32'h20000400 : 32'h20000004)^32'hcafe1234))
                    $fatal(1,"posted data mismatch sample=%d word=%d data=%x",n,j,value);
            end
        end
        read_reg(1,value);if(value[31:16]!=0) $fatal(1,"FIFO pop did not release slot");
        read_reg(5,value);if(value!=0) $fatal(1,"empty FIFO read");
        write_reg(0,2);read_reg(7,value);if(value!=0) $fatal(1,"clear counters");
        // Fault and parity invalidate the whole sample; no partial publication.
        inject_fault=1;write_reg(0,32'h301);repeat(200) @(negedge clk);
        read_reg(1,value);if(!value[4] || value[31:16]!=0 || active) $fatal(1,"FAULT publication %x",value);
        inject_fault=0;write_reg(0,2);inject_parity=1;write_reg(0,32'h301);repeat(200) @(negedge clk);
        read_reg(1,value);if(!value[4] || value[31:16]!=0) $fatal(1,"parity publication");
        reset();configure();hang=1;write_reg(0,32'h301);repeat(200) @(negedge clk);
        read_reg(1,value);if(!value[4] || value[31:16]!=0) $fatal(1,"timeout missing");
        reset();configure();write_reg(0,32'h301);wait(busy);write_reg(0,0);
        repeat(500) @(negedge clk);read_reg(1,value);
        if(active || value[31:16]!=1) $fatal(1,"graceful stop did not finish one sample %x",value);
        $display("PASS sampler: posted reads, 1KiB boundary, WAIT, FIFO backpressure, stop, FAULT, parity, watchdog");
        $finish;
    end
    initial begin #2000000;$fatal(1,"test timeout");end
endmodule
