`timescale 1ns/1ps
module tb_swj_clk_gen;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,enable=0,sample_at_end=1;
    reg [31:0] half_q=65536;
    reg [15:0] sample_offset=0;
    wire edge_tick,sample_tick;
    swj_clk_gen dut(.*);
    integer cases=0;
    task run(input [31:0] q,input integer intervals,input integer offset);
        integer elapsed,edges,last_edge,samples,first_sample,n,lo,hi;
        reg [63:0] ideal,actual;
        begin
            @(negedge clk);enable=0;half_q=q;
            sample_at_end=offset<0;sample_offset=offset;
            repeat(2) @(posedge clk);
            @(negedge clk);enable=1;
            elapsed=0;edges=0;last_edge=0;samples=0;first_sample=-1;
            lo=(q<65536)?1:q>>16;hi=lo+((q[15:0]!=0 && q>=65536)?1:0);
            while(edges<intervals)begin
                @(posedge clk);elapsed=elapsed+1;
                if(sample_tick)begin
                    samples=samples+1;
                    if(first_sample<0)first_sample=elapsed;
                    if(offset>=0 && elapsed-last_edge!=offset+1)
                        $fatal(1,"sample offset q=%d elapsed=%d last=%d",q,elapsed,last_edge);
                end
                if(edge_tick)begin
                    n=elapsed-last_edge;
                    if(n<lo || n>hi)$fatal(1,"half period out of bounds q=%d got=%d",q,n);
                    if(offset<0 && !sample_tick)$fatal(1,"missing sample-at-end");
                    last_edge=elapsed;edges=edges+1;
                end
            end
            actual=64'(elapsed)*65536;ideal=64'(intervals)*((q<65536)?65536:q);
            if(actual>ideal || ideal-actual>=65536)
                $fatal(1,"integral period drift q=%d actual=%d ideal=%d",q,actual,ideal);
            if(samples!=edges)$fatal(1,"sample count q=%d %d != %d",q,samples,edges);
            @(negedge clk);enable=0;
            repeat(2)begin @(posedge clk);#0.001;
                if(edge_tick || sample_tick)$fatal(1,"disabled event leaked");end
            cases=cases+1;
        end
    endtask
    integer i;
    initial begin
        repeat(3)@(negedge clk);rst_n=1;
        for(i=1;i<=16;i=i+1)begin run(i*65536,128,-1);run(i*65536,128,0);end
        run(78643,50000,-1);run(87381,50000,-1);run(98304,50000,-1);
        run(157286,50000,-1);run(3932160,2000,7);run(32'hffffffff,3,123);
        run(0,128,-1);run(65535,128,-1);
        // Cancel an interval and fraction remainder, then restart from phase 0.
        @(negedge clk);half_q=157286;enable=1;
        repeat(7)@(posedge clk);
        run(157286,50000,-1);
        $display("PASS swj_clk_gen cases=%0d integer first-edge/steady, Q16 integral accuracy, independent samples, disable/restart",cases);
        $finish;
    end
    initial begin #100000000;$fatal(1,"generator watchdog");end
endmodule
