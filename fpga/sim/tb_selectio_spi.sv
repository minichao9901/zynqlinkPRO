`timescale 1ns/1ps
module tb_selectio_spi;
    bit clk=0,reset=1,start=0;
    always #5 clk=!clk;
    reg [1:0] mode;
    reg [12:0] count;
    wire [9:0] tx_addr;
    reg [31:0] tx_word,tx_mem[0:1023];
    reg [7:0] expected_rx[0:4095];
    reg [3:0] miso=0;
    wire [3:0] sck,cs_n,mosi;
    wire valid,busy,done;
    wire [11:0] rx_addr;
    wire [7:0] rx_byte;
    reg [5:0] sample_slot;
    selectio_spi dut(clk,reset,start,mode,count,sample_slot,tx_addr,tx_word,miso,
                     sck,cs_n,mosi,valid,rx_addr,rx_byte,busy,done);
    always @(posedge clk) tx_word<=tx_mem[tx_addr];
    int received,observed,edges;
    always @(posedge clk) if(valid) begin
        if(rx_addr!==received[11:0] || rx_byte!==expected_rx[received])
            $fatal(1,"mode=%d index=%d address=%d rx=%h expected=%h",mode,received,rx_addr,rx_byte,expected_rx[received]);
        received++;
    end
    // Independently traverse the four chronological samples. Model a slave
    // that advances MISO only on its shift edge and checks MOSI on its latch edge.
    bit prev_sck, prev_cs=1,slave_bit=1;
    int slave_index;
    reg [3:0] return_slots, pipe[0:2];
    always @(posedge clk) begin
        for(int slot=0;slot<4;slot++) begin
            if(prev_cs && !cs_n[slot]) begin
                if(sck[slot]!==mode[1]) $fatal(1,"CS asserted before idle polarity");
                slave_index=0;
                slave_bit=expected_rx[0][7];
            end
            if(!cs_n[slot] && sck[slot]!=prev_sck) begin
                edges++;
                if ((sck[slot]!=mode[1])!=mode[0]) begin
                    if(mosi[slot]!==tx_mem[observed>>5][8*((observed>>3)&3)+7-(observed&7)])
                        $fatal(1,"MOSI mode=%d bit=%d",mode,observed);
                    observed++;
                end else begin
                    if (mode[0] && edges==1) slave_index=0;
                    else slave_index++;
                    slave_bit=expected_rx[slave_index>>3][7-(slave_index&7)];
                end
            end
            return_slots[slot]=slave_bit;
            prev_cs=cs_n[slot]; prev_sck=sck[slot];
        end
        pipe[0]<=return_slots;pipe[1]<=pipe[0];pipe[2]<=pipe[1];
        miso<=pipe[2];
    end
    task automatic transfer(input integer bytes);
        for(int i=0;i<bytes;i++) begin
            tx_mem[i>>2][(i&3)*8+:8]=$random;
            expected_rx[i]=$random;
        end
        count=bytes;
        // Four quartet registers of return delay. CPHA1 captures at the
        // following trailing edge, whose incoming bit is unchanged.
        sample_slot=mode[0]?20:18;
        observed=0;received=0;edges=0;
        @(negedge clk);start=1;
        @(negedge clk);start=0;
        wait(done);
        if(observed!=8*bytes || edges!=16*bytes || received!=bytes)
            $fatal(1,"wrong counts %d %d %d",observed,edges,received);
        @(negedge clk);
    endtask
    initial begin
        repeat(3) @(negedge clk);reset=0;
        for(int i=0;i<4;i++) begin
            mode=i; transfer(1); transfer(5); transfer(4096);
        end
        $display("SPI_PASS CPOL/CPHA 0..3: full duplex 1, 5, 4096 bytes at 100 MHz");
        $finish;
    end
    initial begin #3000000; $fatal(1,"timeout"); end
endmodule
