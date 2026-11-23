`timescale 1ns/1ps
module tb_timing_margin;
    bit clk=0,reset=1,en=0,man=0;
    always #5 clk=!clk;
    reg line=1;
    reg [3:0] samples;
    reg [7:0] captured,wide_samples;
    reg [31:0] period;
    reg [15:0] min_short,short_limit,long_limit;
    wire uv,mv,ue,me;
    wire edge_v,edge_e,fast_v,fast_e;wire [7:0] edge_d,fast_d;
    bit sample_phase=0;
    wire use_fast=(period>=1023 && period<=1025);
    wire [7:0] ud,md;
    selectio_uart_rx uart(clk,reset,en&&!man,samples,period,uv,ud,ue);
    selectio_manchester_rx manch(clk,reset,en&&man&&!use_fast,samples,min_short,short_limit,long_limit,edge_v,edge_d,edge_e);
    selectio_manchester_fast fast(clk,reset,en&&man&&use_fast,sample_phase,wide_samples,fast_v,fast_d,fast_e);
    assign mv=use_fast?fast_v:edge_v;
    assign md=use_fast?fast_d:edge_d;
    assign me=use_fast?fast_e:edge_e;
    reg [7:0] expected[0:1023];
    integer received=0,errors=0,queued=0,mismatches=0;
    always @(negedge clk) begin
        if(en && (ue || me)) errors++;
        if(en && (uv || mv)) begin
            if(received>=queued || (man?md:ud)!==expected[received])
                mismatches++;
            received++;
        end
    end
    // Independent asynchronous source; capture earliest serial sample in slot 0.
    initial begin
        #0.4;
        forever begin
            for(integer i=0;i<8;i++) begin captured[i]=line;#1.25;end
            wide_samples=captured;
            samples={captured[6],captured[4],captured[2],captured[0]};
        end
    end
    task automatic run(input bit is_manchester,input real bit_ns,input integer blocks,input real shift_ns);
        realtime half_bit;
        integer nbytes, rng;
        reg [7:0] value;
        en=0;reset=1;man=is_manchester;line=!man;
        period=1024;
        half_bit=bit_ns/2;
        min_short=$rtoi(bit_ns/2.5*0.25);
        short_limit=$rtoi(bit_ns/2.5*0.75+0.5);
        long_limit=$rtoi(bit_ns/2.5*1.25+0.5);
        received=0;queued=0;errors=0;mismatches=0;rng=743;
        #100; @(negedge clk);reset=0; en=1;
        #(bit_ns*3+shift_ns);
        for(int k=0;k<blocks;k++) begin
            nbytes=man ? 1+k%8 : 1;
            if(man) begin line=1;#(half_bit);line=0;#(half_bit);end
            for(int j=0;j<nbytes;j++) begin
                value=$random(rng);
                expected[queued]=value;queued++;
                if(!man) begin line=0;#(bit_ns);end
                for(int b=0;b<8;b++) begin
                    line=value[b];
                    if(man) begin #(half_bit);line=!line;#(half_bit);end
                    else #(bit_ns);
                end
                if(!man) begin line=1;#(bit_ns);end
            end
            if(man) begin line=0;#(bit_ns);end
        end
        #(bit_ns*5+100);
        $display("TIMING_MARGIN %0d %0d %0.3f %0.2f %0d %0d %0d %0d",man,sample_phase,bit_ns,shift_ns,queued,received,errors,mismatches);
    endtask
    initial begin
        real duration[0:6];
        duration[0]=9.900;duration[1]=9.950;duration[2]=9.980;
        duration[3]=10.000;duration[4]=10.020;duration[5]=10.050;duration[6]=10.100;
        for(int mode=0;mode<2;mode++)
            for(int phase=0;phase<(mode?2:1);phase++) begin
                sample_phase=phase;
                for(int period_idx=0;period_idx<7;period_idx++)
                    for(int offset=0;offset<3;offset++)
                        run(mode,duration[period_idx],128,0.05+offset*0.55);
            end
        $finish;
    end
endmodule
