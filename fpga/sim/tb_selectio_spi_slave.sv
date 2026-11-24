`timescale 1ns/1ps
module tb_selectio_spi_slave #(parameter FILTER=0);
    reg reference_clock = 0, reset_n = 0;
    wire serial_clk, quad_clk, octet_clk, wide_clk, phy_reset;
    always #10 reference_clock = ~reference_clock;
    selectio_clocking #(.VARIABLE_CLOCK(1)) clocks(
        .ref_clk(reference_clock),.resetn(reset_n),.calibrated(1'b1),
        .jtag_hold(1'b0),.swd_hold(1'b0),.legacy_released(1'b1),
        .live_jtag(1'b0),.live_swd(1'b0),.aux_request(1'b0),
        .serial_clk(serial_clk),.quad_clk(quad_clk),.octet_clk(octet_clk),
        .serial_rx_clk(wide_clk),.phy_reset(phy_reset),
        .clock_control(2'b00),.delay_ref(1'b0));

    reg listener=0, master_sck=0, master_cs=1, master_data=0;
    reg [1:0] mode=0;
    tri sck, cs_n, mosi;
    reg sck_glitch=0, nss_glitch=0;
    assign #0.21 sck = master_sck ^ sck_glitch;
    assign #0.32 cs_n = master_cs | nss_glitch;
    assign #0.98 mosi = master_data;
    wire [3:0] sck_samples, cs_samples, mosi_samples;
    wire [7:0] sck_wide, mosi_wide;
    selectio_debug_phy #(.SPI_PAD_FILTER(FILTER)) pads(
        .serial_clk(serial_clk),.quad_clk(quad_clk),.octet_clk(octet_clk),
        .serial_rx_clk(wide_clk),.reset(phy_reset),.owner(3'd4),
        .legacy_clock(1'b0),.legacy_data(1'b1),.legacy_release(1'b1),
        .legacy_tdi(1'b0),.legacy_tdi_release(1'b1),.jtag_lanes(24'h0),
        .swd_clock(4'h0),.swd_data(4'h0),.swd_release(4'hf),
        .tap_clk(quad_clk),.tdo_load(1'b0),.swdio_load(1'b0),
        .tdo_tap(5'd0),.swdio_tap(5'd0),.clock_pin(sck),.data_pin(cs_n),
        .tdi_pin(mosi),.tdo_pin(1'b1),.aux_spi(1'b1),.aux_spi_slave(1'b1),
        .aux_sck(4'h0),.aux_cs(4'hf),.aux_tx(4'h0),
        .uart_sideband(1'b0),.monitor_tdi(1'b0),
        .slave_sck(sck_samples),.slave_cs_n(cs_samples),.slave_mosi(mosi_samples),
        .slave_sck_wide(sck_wide),.slave_mosi_wide(mosi_wide));
    wire valid, error;
    wire [7:0] data;
    generate if (FILTER) begin: filtered
        wire [7:0] cs_wide={{2{cs_samples[3]}},{2{cs_samples[2]}},
                            {2{cs_samples[1]}},{2{cs_samples[0]}}};
        selectio_spi_slave_rx #(.WIDTH(8),.FILTER(1)) receiver(
            quad_clk,phy_reset,listener,mode,sck_wide,cs_wide,mosi_wide,valid,error,data);
    end else begin: original
        selectio_spi_slave_rx receiver(quad_clk,phy_reset,listener,mode,
            sck_samples,cs_samples,mosi_samples,valid,error,data);
    end endgenerate

    task automatic inject_glitches;
        begin
            // The ringing adds a repeated sampling-polarity edge and a
            // separate short high pulse while NSS should remain selected.
            sck_glitch <= #1.6 1;
            sck_glitch <= #3.3 0;
            nss_glitch <= #1.5 1;
            nss_glitch <= #5.0 0;
        end
    endtask

    reg [7:0] expected[0:16383];
    integer sent=0, received=0, errors=0;
    always @(negedge quad_clk) if(!phy_reset) begin
        if(listener && {pads.clock_tri,pads.data_tri,pads.tdi_tri}!==3'b111)
            $fatal(1,"SPI slave must release all bus inputs, got %b%b%b",
                   pads.clock_tri,pads.data_tri,pads.tdi_tri);
        if(valid) begin
            if(received>=sent || data!==expected[received])
                $fatal(1,"SPI mismatch mode %0d byte %0d got %02x expected %02x",mode,received,data,expected[received]);
            received=received+1;
        end
        if(error) errors=errors+1;
    end

    task automatic transaction(input integer count,input realtime half_period,input integer seed);
        integer i,b;
        reg [7:0] value;
        begin
            master_cs=0;
            #(half_period*2);
            for(i=0;i<count;i=i+1) begin
                value=(i*73)^(seed*43)^(i>>2);
                expected[sent]=value;
                sent=sent+1;
                for(b=7;b>=0;b=b-1) begin
                    if(!mode[0]) master_data=value[b];
                    #half_period;
                    master_sck=~mode[1];
                    if(FILTER && !mode[0] && b==3) inject_glitches;
                    if(mode[0]) master_data=value[b];
                    #half_period;
                    master_sck=mode[1];
                    if(FILTER && mode[0] && b==3) inject_glitches;
                end
            end
            #half_period;
            master_cs=1;
            #50;
        end
    endtask

    integer m,f,phase,bit_number;
    realtime half_period;
    initial begin
        #100; reset_n=1;
        wait(phy_reset===1'b0);
        repeat(10) @(negedge quad_clk);
        for(m=0;m<4;m=m+1) begin
            listener=0; mode=m; master_sck=mode[1];
            #50;
            listener=1;
            #50;
            for(f=0;f<3;f=f+1) begin
                half_period=f==0 ? 10.0 : f==1 ? 6.875 : 5.0;
                for(phase=0;phase<8;phase=phase+1) begin
                    @(negedge quad_clk);
                    #(phase*1.25+0.17);
                    transaction(1,half_period,m+f+phase);
                    transaction(97,half_period,7+m+f+phase);
                    if(received!=sent || errors) $fatal(1,"complete SPI transaction did not drain");
                end
            end
            master_cs=0; #15;
            for(bit_number=0;bit_number<3;bit_number=bit_number+1) begin
                #5; master_sck=~mode[1];
                #5; master_sck=mode[1];
            end
            #5; master_cs=1;
            #60;
            if(errors!=1 || received!=sent) $fatal(1,"partial byte did not abort on CS");
            transaction(4,5.0,11+m);
            if(received!=sent) $fatal(1,"SPI did not recover for the next CS");
            errors=0;
        end
        $display("SPI_SLAVE_PASS bytes=%0d modes=4 rates=50,72.727,100MHz phases=8 partial=4 glitches=%0d",received,FILTER);
        $finish;
    end
    initial #3000000 $fatal(1,"SPI slave timeout");
endmodule
