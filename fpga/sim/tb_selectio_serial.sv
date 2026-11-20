`timescale 1ns/1ps
module tb_selectio_serial;
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
    integer received=0,errors=0,queued=0;
    always @(negedge clk) begin
        if(en && (ue || me)) errors++;
        if(en && (uv || mv)) begin
            if(received>=queued || (man?md:ud)!==expected[received])
                $fatal(1,"mode %d byte %d actual=%h expected=%h",man,received,man?md:ud,expected[received]);
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
    task automatic run(input bit is_manchester,input real bit_ns,input integer blocks);
        realtime half_bit;
        integer nbytes;
        reg [7:0] value;
        en=0;reset=1;man=is_manchester;line=!man;
        period=$rtoi(bit_ns/2.5*256+0.5);
        half_bit=bit_ns/2;
        min_short=$rtoi(bit_ns/2.5*0.25);
        short_limit=$rtoi(bit_ns/2.5*0.75+0.5);
        long_limit=$rtoi(bit_ns/2.5*1.25+0.5);
        received=0;queued=0;errors=0;
        #100; @(negedge clk);reset=0; en=1;
        #(bit_ns*3+0.83);
        for(int k=0;k<blocks;k++) begin
            nbytes=man ? 1+k%8 : 1;
            if(man) begin line=1;#(half_bit);line=0;#(half_bit);end
            for(int j=0;j<nbytes;j++) begin
                value=$random;
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
        if(received!=queued || errors) $fatal(1,"mode %d received %d/%d errors %d",man,received,queued,errors);
        $display("SERIAL_PASS manchester=%d bit_ns=%0.3f bytes=%d",man,bit_ns,received);
    endtask
    initial begin
        run(0,10,64);run(0,41.6667,64);run(0,8680.5556,4);
        run(1,10,64);
        sample_phase=1;
        run(1,9.995,128);run(1,10.005,128);
        sample_phase=0;
        run(1,9.995,128);run(1,10.005,128);
        run(1,41.6667,64);run(1,80,64);
        $finish;
    end
endmodule
