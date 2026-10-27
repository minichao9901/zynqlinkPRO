`timescale 1ns/1ps
// Deterministic control-space sweep. The runner inserts a second, immutable
// main core beside this DUT and compares all pins/results at both FCLK edges.
// Wire-level delayed targets and real MEM-AP tests are separate suite layers.
module tb_swd_timing_equiv;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,start=0,next_valid=0,mode=1,timestamp_en=1;
    reg [7:0] next_request=0,xfer_request=0,swj_count=0;
    reg [31:0] next_wdata=0,xfer_wdata=0;
    reg [3:0] idle_cycles=0,clock_delay=0,delay_fast=0;
    reg data_phase=0;reg [1:0] turn_extra=0;reg [2:0] ack_delay=0;
    reg [255:0] swj_data=0;
    reg swdio_i=0,swdio_i_fall=0;
    wire next_ready,result_valid,busy,parity_err,swclk,swdio_o,swdio_t;
    wire [31:0] xfer_rdata;wire [2:0] ack;wire [15:0] timestamp;
    swd_core dut(.*);
    reg [2:0] target_ack=1;
    reg [31:0] target_word=32'h96a53cc3,lfsr=32'h7b928e51;
    reg bad_parity=0;
    reg [16:0] visited=0;
    integer transactions=0,resets=0,chain_left=0,chains=0;
    always @(posedge clk)begin
        if(rst_n)visited[dut.state]=1;
        if(rst_n && next_valid && next_ready)begin
            chains=chains+1;chain_left=chain_left-1;
            next_wdata<=next_wdata+32'h9e3779b9;
            next_request<=next_request^2;
            if(chain_left==0)next_valid<=0;
        end
    end
    always @(negedge clk)begin
        lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
        swdio_i=lfsr[3];swdio_i_fall=lfsr[7];
        if(dut.state==4)case(dut.lsm_cnt)
            3:swdio_i_fall=target_ack[0];
            5:swdio_i_fall=target_ack[1];
            7:swdio_i_fall=target_ack[2];
            default:;
        endcase
        if(dut.state==15)case(dut.lsm_cnt)
            2:swdio_i_fall=target_ack[0];
            5:swdio_i_fall=target_ack[1];
            8:swdio_i_fall=target_ack[2];
            default:;
        endcase
        if(dut.state==6)begin
            if(dut.lsm_cnt>=3 && dut.lsm_cnt<66 && dut.lsm_cnt[0])
                swdio_i_fall=target_word[(dut.lsm_cnt-3)/2];
            if(dut.lsm_cnt==67)swdio_i_fall=(^target_word)^bad_parity;
        end
    end
    task launch;
        integer budget;
        begin
            @(negedge clk);#0.01;start=1;
            @(negedge clk);#0.01;start=0;budget=0;
            while(dut.state!=12 && budget<20000)begin @(negedge clk);#0.01;budget=budget+1;end
            if(budget==20000)$fatal(1,"control sweep timeout");
            repeat(3)begin @(negedge clk);#0.01;end
            transactions=transactions+1;
        end
    endtask
    integer d,a,r,p,k,c;
    reg wave_example=0;
    initial begin
        wave_example=$test$plusargs("wave");
        if(wave_example)begin
            $dumpfile("main_vs_timing.vcd");$dumpvars(1,dut);
        end
        repeat(4)@(negedge clk);#0.01;rst_n=1;
        // Every legacy divider, ACK-hold value, ACK code, direction, and
        // WAIT/FAULT data-phase policy; idle/turn values rotate independently.
        for(d=0;d<(wave_example?1:16);d=d+1)for(a=0;a<(wave_example?1:8);a=a+1)
        for(r=0;r<2;r=r+1)for(p=0;p<2;p=p+1)for(k=0;k<8;k=k+1)begin
            mode=1;delay_fast=d;ack_delay=a;data_phase=p;target_ack=k;
            turn_extra=(d+a+k+r)%4;idle_cycles=(d+k)%4;
            xfer_request=(k*4)|(r<<1)|1;xfer_wdata=lfsr;
            target_word=lfsr^32'hc63a59e1;bad_parity=k[0];
            launch();
        end
        // All SWJ lengths, including zero, with all distinct divider values.
        mode=0;next_valid=0;
        for(d=0;d<(wave_example?1:16);d=d+1)for(c=0;c<(wave_example?32:256);c=c+1)begin
            clock_delay=d;swj_count=c;swj_data={8{lfsr}};launch();
        end
        // Back-to-back requests keep main's overlapped START and exact speed.
        mode=1;delay_fast=0;target_ack=1;bad_parity=0;
        for(a=0;a<8;a=a+1)for(p=0;p<2;p=p+1)begin
            ack_delay=a;data_phase=p;idle_cycles=(a+p)%3;
            next_request=15;next_wdata=lfsr;chain_left=32;next_valid=1;
            launch();wait(!busy);repeat(3)@(negedge clk);
        end
        // Reset at many different positions in active read/write/SWJ frames.
        for(c=0;c<128;c=c+1)begin
            mode=c%3!=0;clock_delay=c%16;delay_fast=c%4;
            ack_delay=c%8;target_ack=(c%3==0)?2:1;swj_count=255;
            @(negedge clk);#0.01;start=1;
            @(negedge clk);#0.01;start=0;
            repeat(1+c*3)@(negedge clk);
            #0.01;rst_n=0;repeat(2)@(negedge clk);#0.01;rst_n=1;
            resets=resets+1;
        end
        // State 14 is a retained but unreachable legacy decode state.
        if(!wave_example && (visited | (17'b1<<14))!==17'h1ffff)$fatal(1,"missing protocol states %h",visited);
        if(chains!=512)$fatal(1,"chain count %d",chains);
        $display("PASS SWD main waveform matrix transactions=%0d chains=%0d resets=%0d states=%h",transactions,chains,resets,visited);
        $finish;
    end
    initial begin #1000000000;$fatal(1,"equivalence watchdog");end
endmodule
