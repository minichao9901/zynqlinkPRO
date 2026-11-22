`timescale 1ps/1ps
module tb_selectio_spi_slave_offset;
    reg clk=0, reset=1, enable=0;
    reg sck=0, cs_n=1, mosi=0;
    reg direct=0;
    reg [1:0] mode=0;
    reg [3:0] sck_word=0, cs_word=4'hf, mosi_word=0;
    wire valid, error;
    wire [7:0] data;
    selectio_spi_slave_rx dut(clk,reset,enable,mode,
        sck_word,cs_word,mosi_word,valid,error,data);

    // Exact 100 MHz source and a reference 0.08% slower than nominal.
    // This models phase drift at the output of the asynchronous samplers.
    integer slot=0;
    always begin
        #2502;
        if(!direct) begin
            sck_word[slot]=sck;
            cs_word[slot]=cs_n;
            mosi_word[slot]=mosi;
            if(slot==3) begin
                clk <= #1 1;
                clk <= #1000 0;
                slot=0;
            end else slot=slot+1;
        end
    end

    task automatic samples(input [3:0] clock_bits, select_bits, data_bits);
        sck_word=clock_bits;
        cs_word=select_bits;
        mosi_word=data_bits;
        #1000; clk=1;
        #5000; clk=0;
        #4000;
    endtask

    function automatic [7:0] probe_pattern(input integer index,input integer m);
        probe_pattern=(index*73) ^ (index>>2) ^ 8'h96 ^ (m*37);
    endfunction
    reg [7:0] value, first_byte, second_byte;
    integer m, index, bit_number;
    integer received=0, split_words=0;
    reg previous_sck=0;
    wire [3:0] edges=(sck_word ^ {sck_word[2:0],previous_sck}) &
        ((mode[1] ^ mode[0]) ? ~sck_word : sck_word) & ~cs_word;
    always @(posedge clk) begin
        previous_sck<=sck_word[3];
        if(enable && (edges & (edges-4'd1))) split_words<=split_words+1;
    end
    always @(negedge clk) if(enable) begin
        if(error) $fatal(1,"100 MHz CDC sampler reported a framing error, mode %0d",mode);
        if(valid) begin
            if(data!==probe_pattern(received,mode))
                $fatal(1,"mode %0d byte %0d: got %02x expected %02x",mode,received,data,probe_pattern(received,mode));
            received=received+1;
        end
    end

    initial begin
        #200007; reset=0;
        for(m=0;m<4;m=m+1) begin
            enable=0;
            mode=m;
            sck=mode[1];
            received=0;
            #101731;
            enable=1;
            #101731; cs_n=0;
            #20391;
            for(index=0;index<2048;index=index+1) begin
                value=probe_pattern(index,m);
                for(bit_number=7;bit_number>=0;bit_number=bit_number-1) begin
                    if(!mode[0]) mosi=value[bit_number];
                    #5000; sck=~mode[1];
                    if(mode[0]) mosi=value[bit_number];
                    #5000; sck=mode[1];
                end
            end
            #5000; cs_n=1;
            #100007;
            if(received!=2048) $fatal(1,"mode %0d received %0d bytes",mode,received);
        end
        if(!split_words) $fatal(1,"frequency-offset fixture did not exercise two-edge words");
        // End one complete byte and start a new CS frame in a single word.
        @(negedge clk);
        #1; direct=1; enable=0; mode=0; received=0;
        samples(0,4'hf,0);
        enable=1;
        samples(0,4'hf,0);
        first_byte=probe_pattern(0,0);
        second_byte=probe_pattern(1,0);
        for(bit_number=7;bit_number>0;bit_number=bit_number-1)
            samples(4'b0110,0,{4{first_byte[bit_number]}});
        samples(4'b1001,4'b0010,{second_byte[7],2'b00,first_byte[0]});
        for(bit_number=6;bit_number>=0;bit_number=bit_number-1)
            samples(4'b0110,0,{4{second_byte[bit_number]}});
        samples(0,4'hf,0);
        samples(0,4'hf,0);
        if(received!=2) $fatal(1,"CS gap between edges lost or joined frames");
        $display("SPI_SLAVE_OFFSET_PASS 100MHz bytes=8192 modes=4 two_edge_words=%0d same_word_cs_gap=pass",
                 split_words);
        $finish;
    end
    initial #2000000000 $fatal(1,"test timeout");
endmodule
