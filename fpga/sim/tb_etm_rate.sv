`timescale 1ns/1ps
// Independent TRACECLK. Data leaves the target with the matching edge;
// fixed per-lane board delays span 0.2..1.4 ns and clock delay is 1.6 ns.
module tb_etm_rate;
    reg refclk=0,hostclk=0,rst=1;
    always #2.5 refclk=~refclk;
    always #3.75 hostclk=~hostclk;
    reg [4:0] drive=0;
    wire [4:0] pins;
    assign #1.6 pins[4]=drive[4];
    for(genvar i=0;i<4;i=i+1)assign #(0.2+0.4*i) pins[i]=drive[i];
    wire [127:0] frame[2];
    wire [1:0] seen,malformed;
    wire [127:0] tail[2];
    wire [4:0] tail_bytes[2];
    integer count[2],errors[2];
    function automatic [7:0] sample_byte(input integer f,input integer b);
        // Vary every nibble; avoid formatter sync octets in the payload.
        sample_byte=((73*f+29*b+19) ^ (f>>1))%251;
    endfunction
    for(genvar d=0;d<2;d=d+1)begin
        orbtrace_parallel #(.RAW_DIAGNOSTIC(4),.DOUBLE_SAMPLE(d),.ENABLE_DDR_TAP(1)) dut(
            .clk(hostclk),.sample_clk(refclk),.rst(rst),.trace_clk(pins[4]),.trace_io_clk(pins[4]),
            .trace_pad_clk(pins[4]),.trace_data(pins[3:0]),.width(2'd3),.ready(1'b1),.diagnostic_reset(rst),
            .ddr_hold(1'b1),.ddr_sampler_gate(1'b1),.ddr_parser_enable(1'b1),.ddr_parser_clear(1'b0),
            .ddr_tail(tail[d]),.ddr_tail_bytes(tail_bytes[d]),.ddr_frame(frame[d]),.ddr_frame_event(seen[d]),.ddr_parser_error(malformed[d]));
        always @(posedge refclk)begin
            if(rst)begin count[d]=0;errors[d]=0;end
            else begin
                if(malformed[d])errors[d]=errors[d]+1;
                if(seen[d])begin
                    for(integer b=0;b<16;b=b+1)
                        if(frame[d][8*(15-b)+:8]!==sample_byte(count[d],b))errors[d]=errors[d]+1;
                    count[d]=count[d]+1;
                end
            end
        end
    end
    realtime half_period;
    task send_byte(input [7:0] data);
        begin
            drive={1'b1,data[3:0]};#(half_period);
            drive={1'b0,data[7:4]};#(half_period);
        end
    endtask
    integer freq=64,phase=0,frames=128;
    initial begin
        if($value$plusargs("mhz=%d",freq))begin end
        if($value$plusargs("phase_ps=%d",phase))begin end
        half_period=500.0/freq;
        #120;rst=0;
        repeat(20)@(negedge refclk);
        #(phase/1000.0);
        repeat(4)begin send_byte(255);send_byte(255);send_byte(255);send_byte(127);end
        for(integer f=0;f<frames;f=f+1)
            for(integer b=0;b<16;b=b+1)send_byte(sample_byte(f,b));
        send_byte(8'h23);send_byte(8'h45);send_byte(8'h67);
        repeat(20)@(posedge refclk);
        for(integer d=0;d<2;d=d+1)
            if(tail_bytes[d]!==3 || tail[d][23:0]!==24'h234567)errors[d]++;
        $display("ETM_RATE %d %d %d %d %d %d",freq,phase,count[0],errors[0],count[1],errors[1]);
        $finish;
    end
endmodule
