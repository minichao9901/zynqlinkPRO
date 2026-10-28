`timescale 1ns/1ps
module tb_probe_stream_dma;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,en=0;reg [3:0] we=0;reg [31:0] addr=0,wd=0;wire [31:0] data;
    reg [31:0] fifo[0:8191];integer fi=0,fo=0;
    reg [31:0] tick=0;reg sampling=0;
    wire pop,active,start,nvalid,busy,valid,nready,parity;
    wire [7:0] req,nreq;wire [31:0] cw,cr;wire [2:0] ack;
    reg chain=1;
    probe_stream_engine dut(.clk(clk),.rst_n(rst_n),.host_en(en),.host_we(we),.host_addr(addr),.host_wdata(wd),.host_rdata(data),
        .sample_empty(fi==fo),.sample_data(fifo[fo]),.tick(tick),.sampler_active(sampling),.sample_pop(pop),
        .rtt_active(active),.core_start(start),.core_req(req),.core_wdata(cw),.core_next_valid(nvalid),.core_next_req(nreq),
        .core_available(1'b1),.core_busy(busy),.core_result_valid(valid),.core_next_ready(nready),
        .core_ack(ack),.core_parity_err(parity),.core_rdata(cr),.transport_jtag(1'b0),.fence_done(1'b0),.fence_error(1'b0));
    probe_ap_model ap(.clk(clk),.rst_n(rst_n),.start(start),.next_valid(nvalid),.chain_enable(chain),.req(req),.next_req(nreq),
        .wdata(cw),.busy(busy),.result_valid(valid),.next_ready(nready),.ack(ack),.parity(parity),.rdata(cr));
    always @(posedge clk) begin tick<=tick+1;if(pop) begin if(fi==fo) $fatal(1,"empty pop");fo<=fo+1;end end
    task wr(input integer a,input [31:0] d);
        @(negedge clk);addr=a;wd=d;en=1;we=15;@(negedge clk);en=0;we=0;
    endtask
    task rd(input integer a,output [31:0] d);
        @(negedge clk);addr=a;en=1;we=0;@(negedge clk);d=data;en=0;
    endtask
    task cfg(input integer i,input [31:0] d);wr(24,i);wr(28,d);endtask
    task sample(input [31:0] t,input [31:0] v);fifo[fi]=t;fifo[fi+1]=v;fi=fi+2;endtask
    task wait_packet;
        integer t;reg [31:0] d;
        begin t=0;d=0;while(d==0 && t<20000) begin rd(8,d);t=t+1;end
        if(d==0) $fatal(1,"packet timeout state=%d rtt=%d phase=%d",dut.state,dut.u_rtt.state,dut.u_rtt.phase);end
    endtask
    integer i,j;reg [31:0] d,base,prior,expected;
    initial begin
        repeat(4) @(negedge clk);rst_n=1;
        cfg(0,4);cfg(1,2);cfg(2,48);cfg(5,1);
        for(i=0;i<4;i=i+1) cfg(16+i,i);
        sampling=1;wr(0,1);
        for(i=0;i<124;i=i+1) sample(1000+48*i,32'hcafe0000+i);
        wait_packet();rd(4096,d);if(d!=32'h02024a53) $fatal(1,"header %x",d);
        rd(4104,d);if(d!=1000) $fatal(1,"stamp %d",d);
        rd(4108,d);if(d!=32'h01f0007c) $fatal(1,"counts %x",d);
        for(i=0;i<124;i=i+1) begin rd(4112+4*i,d);if(d!=32'hcafe0000+i) $fatal(1,"payload %d %x",i,d);end
        // Bank remains immutable until DMA ACK, even if USB stalls.
        rd(12,prior);repeat(100) @(negedge clk);rd(12,d);if(d!=prior) $fatal(1,"premature release");wr(12,1);
        sample(8000,1);sample(8048,2);sample(8144,3);
        wait_packet();rd(4096+2048+12,d);if(d[15:0]!=2) $fatal(1,"timestamp gap compressed %x",d);wr(12,1);
        sampling=0;wr(0,0);wait_packet();rd(4096+4096+8,d);if(d!=8144) $fatal(1,"gap timestamp");wr(12,1);
        // One-byte HSS variables can pack 496 samples, beyond an 8-bit count.
        wr(0,256);cfg(0,1);cfg(16,3);wr(0,1);
        for(i=0;i<496;i=i+1) sample(9000+48*i,i<<24);
        wait_packet();rd(4108,d);if(d!=32'h01f001f0) $fatal(1,"u8 sample count %x",d);
        rd(4112,d);if(d!=32'h03020100) $fatal(1,"u8 gather %x",d);wr(12,1);wr(0,0);
        // v1 uses accumulated elapsed ticks across u32 timer wrap, with /24
        // converted outside the sample read path. A gap cannot reset time.
        wr(0,256);cfg(0,4);cfg(1,1);
        for(i=0;i<4;i=i+1) cfg(16+i,i);
        sampling=1;wr(0,1);sample(0,1);sample(32'hfffffff0,2);sample(32'h20,3);sample(32'h80,4);
        wait_packet();rd(4104,d);if(d!=0) $fatal(1,"v1 origin %x",d);wr(12,1);
        wait_packet();rd(4096+2048+8,d);if(d!=178956970) $fatal(1,"v1 convert %d",d);wr(12,1);
        sampling=0;wr(0,0);wait_packet();rd(4096+4096+8,d);
        if(d!=178956976) $fatal(1,"v1 timer wrap %d",d);wr(12,1);
        // RTT wrap, descriptor and data 1 KiB AP boundaries, unaligned bytes.
        wr(0,256);wr(32,32'h200023f8);wr(36,32'h200003f1);wr(40,4093);wr(44,2);wr(48,2048);
        ap.mem['h23fc/4]=32'h200003f1;ap.mem['h2400/4]=4093;ap.mem['h2404/4]=2500;ap.mem['h2408/4]=2;
        for(i='h3f0/4;i<('h3f1+4093+3)/4;i=i+1) ap.mem[i]=32'h03020100+((i*4-'h3f0)*32'h01010101);
        wr(0,2);wait(dut.u_rtt.state==2 && dut.u_rtt.phase==4);ap.inject_wait=1;wait_packet();
        rd(8,d);if((d&4095)!=2048) $fatal(1,"RTT size %d",d);
        if(ap.mem['h2408/4]!=2) $fatal(1,"RdOff before DMA");
        for(i=0;i<512;i=i+1) begin
            for(j=0;j<4;j=j+1) expected[j*8+:8]=ap.mem[('h3f3+i*4+j)/4][(('h3f3+i*4+j)%4)*8+:8];
            rd(4096+4*i,d);if(d!=expected) $fatal(1,"RTT bytes %d %x != %x",i,d,expected);
        end
        rd(12,prior);wr(12,1);i=0;
        wait(dut.u_rtt.state==2 && dut.u_rtt.phase==7);ap.inject_fault=1;
        wait(dut.rtt_fault);if(ap.mem['h2408/4]!=2) $fatal(1,"failed RdOff advanced");
        rd(12,d);if(d!=prior) $fatal(1,"failed commit released bank");ap.inject_fault=0;wr(12,1);
        while(ap.mem['h2408/4]!=2050 && i<20000) begin @(negedge clk);i=i+1;end
        if(i==20000) $fatal(1,"commit timeout");
        wait_packet();chain=0;wr(12,1);repeat(200) @(negedge clk);
        wr(0,0);repeat(1000) @(negedge clk);
        rd(8,d);if(d!=0) begin wr(12,1);repeat(200) @(negedge clk);end
        wait(!active);
        // Ring tail then wrap to its unaligned base, without reading/committing
        // either packet twice. Keep chain disabled for the entire transfer.
        wr(0,256);wr(44,4050);wr(48,128);
        ap.mem['h2404/4]=20;ap.mem['h2408/4]=4050;wr(0,2);wait_packet();
        rd(8,d);if((d&4095)!=43) $fatal(1,"ring tail length %x",d);
        wr(12,1);wait(dut.tail==1);wait_packet();
        rd(8,d);if((d&4095)!=20) $fatal(1,"ring head length %x",d);
        for(j=0;j<4;j=j+1) expected[j*8+:8]=ap.mem[('h3f1+j)/4][(('h3f1+j)%4)*8+:8];
        rd(4096+2048,d);if(d!=expected) $fatal(1,"unaligned ring wrap payload %x",d);
        wr(0,0);wr(12,1);wait(ap.mem['h2408/4]==20);wait(!active);
        $display("PASS PL packet DMA: HSS payload/headers/gaps/partial stop, immutable banks, RTT 2048-byte posted reads, AP wrap, WAIT, DDR-before-RdOff, chain fallback");$finish;
    end
    initial begin #10000000;$fatal(1,"watchdog");end
endmodule
