`timescale 1ns/1ps
module tb_selectio_debug #(parameter integer QUAD_DMA=0, VARIABLE_CLOCK=0, SELECTIO_SLICE=0);
    bit axi_clk=0, resetn=0, ref_clk=0, delay_ref=0, hclk=0, use_swd=0, released=0;
    always #3.75 axi_clk = !axi_clk;
    realtime ref_ns=VARIABLE_CLOCK ? 20.0 : 5.0, requested_ref_ns;
    always #(ref_ns/2) ref_clk = !ref_clk;
    always #2.5 delay_ref = !delay_ref;
    real hclk_ns=20.834;
    real swd_return_ns=0.8;
    initial begin
        if($value$plusargs("target_clk_ns=%f",hclk_ns))begin end
        if($value$plusargs("return_ns=%f",swd_return_ns))begin end
        forever #(hclk_ns/2) hclk=!hclk;
    end
    wire serial_rx_clk,serial_clk, quad_clk, octet_clk, phy_reset, js_reset, ss_reset, js_ready;
    wire jhold, shold, calibrated, jload, sload;
    wire shared_calibrated, local_calibrated;
    wire [1:0] clock_control;
    assign calibrated=SELECTIO_SLICE==1 ? local_calibrated : shared_calibrated;
    wire bus_clk=QUAD_DMA ? quad_clk : axi_clk;
    wire [2:0] owner;
    wire [4:0] jtap, stap;
    wire [23:0] lanes;
    wire [7:0] jrx;
    wire [3:0] sclock, sdata, srelease, srx;
    wire [26:0] live_config;
    reg [26:0] profile_meta=0, profile_sync=0;
    always @(posedge axi_clk) begin
        profile_meta<=live_config;
        profile_sync<=profile_meta;
    end
    wire [26:0] host_profile=QUAD_DMA ? profile_sync : live_config;
    reg [1:0] live_sync=0;
    reg live_start=0;
    reg [7:0] live_req=0;
    reg [31:0] live_wdata=0;
    wire live_done, live_parity;
    wire [2:0] live_ack;
    wire [31:0] live_rdata;
    wire [3:0] live_clock,live_data,live_release;
    wire clk_pin, tdi_pin;
    tri1 data_pin;
    wire target_tdo, tdo_disabled, target_swd, target_drive, boundary_tdo;
    wire #0.8 tdo_pin = tdo_disabled ? 1'b1 : target_tdo;
    reg delayed_oe=0,delayed_data=1;
    always @(target_drive or target_swd)begin
        delayed_oe<=#(swd_return_ns) (target_drive===1'b1);
        delayed_data<=#(swd_return_ns) target_swd;
    end
    assign data_pin=delayed_oe ? delayed_data : 1'bz;
    wire wire_budget_pin=clk_pin;
    `include "swd_wire_budget.svh"
    if (SELECTIO_SLICE!=1) begin:g_wire_budget
    always @(posedge quad_clk)
        wire_budget_link(swd.g_batch.batch.link.state==4 && swd.g_batch.batch.link.segment.state==2,
                         swd.g_batch.batch.link.state==5 && swd.g_batch.batch.link.segment.state==2,
                         swd.g_batch.batch.link_done,swd.g_batch.batch.issue_next || swd.g_batch.batch.retry);
    end
    IDELAYCTRL calibration(.REFCLK(delay_ref), .RST(!resetn), .RDY(shared_calibrated));
    selectio_clocking #(.VARIABLE_CLOCK(VARIABLE_CLOCK),.LOCAL_CALIBRATION(SELECTIO_SLICE==1)) clocks(ref_clk,resetn,calibrated,jhold,shold,released,1'b0,host_profile[0],1'b0,
        serial_clk,quad_clk,octet_clk,phy_reset,js_reset,ss_reset,js_ready,owner,,serial_rx_clk,clock_control,delay_ref,local_calibrated);
    always @(posedge quad_clk) live_sync<={live_sync[0],host_profile[0]};
    selectio_live_swd live(
        .host_clk(axi_clk),.quad_clk(quad_clk),.reset(!resetn || !host_profile[0]),
        .granted(owner==3 && live_sync[1]),.start(live_start),.mode(1'b1),.request(live_req),.wdata(live_wdata),
        .seq_data(256'b0),.seq_count(8'b0),.sample_slot(host_profile[6:1]),.idle(host_profile[17:14]),
        .half_rate(host_profile[26]),.busy(),.valid(live_done),.ack(live_ack),.parity(live_parity),.rdata(live_rdata),
        .rx(srx),.clocks(live_clock),.data(live_data),.release_bits(live_release));
    selectio_debug_phy phy(serial_clk,quad_clk,octet_clk,phy_reset,owner,
        1'b0,1'b1,1'b1,1'b0,1'b1,lanes,jrx,live_sync[1]?live_clock:sclock,
        live_sync[1]?live_data:sdata,live_sync[1]?live_release:srelease,srx,
        bus_clk,jload,sload,jtap,stap,clk_pin,data_pin,tdi_pin,tdo_pin,,, , ,1'b0,4'b0,4'b0,4'b0,,1'b0,1'b0,serial_rx_clk,);
    jtag_dp_model #(.IRLEN(5),.DUMMY(1),.RETURN_NS(0.2)) boundary(
        .rst_n(resetn),.tck(clk_pin),.tms(data_pin),.tdi(tdi_pin),.tdo(boundary_tdo));
    localparam SRAM_ADDR_BITS=12;
    cm3_target #(.WORDS(1<<SRAM_ADDR_BITS),.ADDR_BITS(SRAM_ADDR_BITS)) cm3(
        .clk(hclk),.rst_n(resetn),.dbg_rst_n(resetn),.trst_n(resetn),.swclktck(clk_pin),
        .swditms(data_pin),.tdi(boundary_tdo),.tdo(target_tdo),.ntdoen(tdo_disabled),
        .swdo(target_swd),.swdoen(target_drive));

    reg [13:0] awaddr=0, araddr=0;
    reg [31:0] wdata=0;
    reg awvalid=0, wvalid=0, arvalid=0;
    wire [1:0] awr,wr,br,arr,rr,bresponse[0:1],rresponse[0:1];
    wire [31:0] rvalues[0:1];
    wire awready=awr[use_swd], wready=wr[use_swd], bvalid=br[use_swd];
    wire arready=arr[use_swd], rvalid=rr[use_swd];
    wire [1:0] bresp=bresponse[use_swd],rresp=rresponse[use_swd];
    wire [31:0] rdata=rvalues[use_swd];
    wire [9:0] jpa,jra,spa,sra;
    wire [31:0] jpd,jrd,spd,srd;
    wire jwe,swe;
    reg dma_en=0;reg [3:0] dma_we=0;reg [31:0] dma_addr=0,dma_data=0;
    wire [31:0] dma_result;
    selectio_payload_ram #(.SELECTIO_SLICE(SELECTIO_SLICE)) payload(bus_clk,!resetn,dma_en,dma_we,dma_addr,dma_data,dma_result,
        octet_clk,quad_clk,jpa,spa,jpd,spd,jwe,swe,jra,sra,jrd,srd);
    task automatic load_payload(input int address,input reg [31:0] value);
        @(negedge bus_clk);dma_en=1;dma_we=15;dma_addr=address;dma_data=value;
        @(negedge bus_clk);dma_en=0;dma_we=0;
    endtask
    task automatic check_payload(input int address,input reg [31:0] value);
        @(negedge bus_clk);dma_en=1;dma_we=0;dma_addr=address;
        @(negedge bus_clk);if(dma_result!==value)$fatal(1,"DMA payload %h got %h expected %h",address,dma_result,value);
        dma_en=0;
    endtask
    jtag200_regs #(.ENABLE_BLOCK(SELECTIO_SLICE!=2),.ENABLE_ENGINE(SELECTIO_SLICE!=2)) jtag(
        .axi_aclk(bus_clk),.axi_aresetn(resetn),
        .s_axi_awaddr(awaddr),.s_axi_awprot(3'b0),.s_axi_awvalid(awvalid && use_swd==0),.s_axi_awready(awr[0]),
        .s_axi_wdata(wdata),.s_axi_wstrb(4'hf),.s_axi_wvalid(wvalid && use_swd==0),.s_axi_wready(wr[0]),
        .s_axi_bresp(bresponse[0]),.s_axi_bvalid(br[0]),.s_axi_bready(1'b1),
        .s_axi_araddr(araddr),.s_axi_arprot(3'b0),.s_axi_arvalid(arvalid && use_swd==0),.s_axi_arready(arr[0]),
        .s_axi_rdata(rvalues[0]),.s_axi_rresp(rresponse[0]),.s_axi_rvalid(rr[0]),.s_axi_rready(1'b1),
        .payload_tx_addr(jpa),.payload_rx_addr(jra),.payload_tx_data(jpd),.payload_rx_data(jrd),.payload_rx_write(jwe),
        .phy_hold(jhold), .ready(js_ready), .delay_ready(calibrated), .delay_load(jload),
        .delay_value(jtap), .word_clk(octet_clk), .word_reset(js_reset), .lane_word(lanes), .rx_word(jrx));
    swd200_regs #(.SAME_CLOCK(QUAD_DMA),.VARIABLE_CLOCK(VARIABLE_CLOCK),.ENABLE_BATCH(SELECTIO_SLICE!=1)) swd(
        .axi_aclk(bus_clk),.axi_aresetn(resetn),
        .s_axi_awaddr(awaddr),.s_axi_awprot(3'b0),.s_axi_awvalid(awvalid && use_swd==1),.s_axi_awready(awr[1]),
        .s_axi_wdata(wdata),.s_axi_wstrb(4'hf),.s_axi_wvalid(wvalid && use_swd==1),.s_axi_wready(wr[1]),
        .s_axi_bresp(bresponse[1]),.s_axi_bvalid(br[1]),.s_axi_bready(1'b1),
        .s_axi_araddr(araddr),.s_axi_arprot(3'b0),.s_axi_arvalid(arvalid && use_swd==1),.s_axi_arready(arr[1]),
        .s_axi_rdata(rvalues[1]),.s_axi_rresp(rresponse[1]),.s_axi_rvalid(rr[1]),.s_axi_rready(1'b1),
        .payload_tx_addr(spa),.payload_rx_addr(sra),.payload_tx_data(spd),.payload_rx_data(srd),.payload_rx_write(swe),
        .hold(shold), .live_config(live_config), .delay_ready(calibrated), .delay_load(sload), .delay_value(stap),
        .word_clk(quad_clk), .word_reset(ss_reset), .rx_slots(srx), .clk_slots(sclock),
        .data_slots(sdata), .release_slots(srelease),.clock_control(clock_control),.phy_reset(phy_reset));
    task automatic write_reg(input [13:0] addr, input [31:0] data, input [1:0] response);
        fork
            begin
                repeat (addr[2] ? 2 : 1) @(negedge bus_clk);
                awaddr = addr;
                awvalid = 1;
                do @(posedge bus_clk); while (!awready);
                @(negedge bus_clk);
                awvalid = 0;
            end
            begin
                repeat (addr[2] ? 1 : 2) @(negedge bus_clk);
                wdata = data;
                wvalid = 1;
                do @(posedge bus_clk); while (!wready);
                @(negedge bus_clk);
                wvalid = 0;
            end
        join
        do @(posedge bus_clk); while (!bvalid);
        if (bresp !== response) $fatal(1, "AXI write response addr=%h got=%b expected=%b", addr, bresp, response);
    endtask

    task automatic read_reg(input [13:0] addr, output [31:0] data);
        @(negedge bus_clk);
        araddr = addr;
        arvalid = 1;
        do @(posedge bus_clk); while (!arready);
        @(negedge bus_clk);
        arvalid = 0;
        do @(posedge bus_clk); while (!rvalid);
        if (rresp !== 0) $fatal(1, "AXI read response addr=%h got=%b", addr, rresp);
        data = rdata;
    endtask

    task automatic wait_clock_control(input [2:0] status);
        reg [31:0] ctl;
        for(int k=0;k<5000;k++) begin
            read_reg('h38,ctl);
            if(ctl[31:8]!==24'h53494f) $fatal(1,"missing variable-clock control");
            if(ctl[2:0]==status) return;
        end
        $fatal(1,"clock handshake stuck, got %h expected %b",ctl,status);
    endtask

    task automatic switch_reference;
        use_swd=1;
        wait_clock_control(4);
        write_reg('h38,3,2); // Reject reset until the PHY acknowledges park.
        write_reg('h38,1,0);
        wait_clock_control(1);
        if(owner!=0 || phy.clock_tri!==1'b1 || phy.data_tri!==1'b1)
            $fatal(1,"pins were not parked before reference change");
        write_reg('h38,3,0);
        wait_clock_control(3);
        ref_ns=requested_ref_ns;
        #500;
        if(!calibrated) $fatal(1,"fixed FCLK2 calibration lost during relock");
        write_reg('h38,0,0);
        wait_clock_control(4);
        wait(owner==1);
        use_swd=0;
        $display("SELECTIO_CLOCK_SWITCH_PASS FCLK1_period_ns=%0.3f FCLK2_period_ns=5.000",ref_ns);
    endtask

    task automatic wait_status(input [4:0] expected);
        reg [31:0] status;
        read_reg(4, status);
        for (int attempts = 0; status !== expected && attempts < 180000; attempts++)
            read_reg(4, status);
        if (status !== expected) $fatal(1, "Status %h expected %h", status, expected);
    endtask


    task automatic put(input int index, input [4:0] req, input [31:0] data);
        write_reg('h1000+index*8, req, 0);
        write_reg('h1004+index*8, data, 0);
    endtask
    task automatic scalar(input [7:0] request,input [31:0] data,output [31:0] reply);
        for(int attempt=0;attempt<64;attempt++)begin
            @(negedge axi_clk);live_req=request;live_wdata=data;live_start=1;
            @(negedge axi_clk);live_start=0;
            do @(negedge axi_clk); while(!live_done);
            if(live_ack!=2)break;
        end
        if(owner!=3 || live_ack!=1 || live_parity)
            $fatal(1,"live SWD req=%h owner=%d ack=%d parity=%b",request,owner,live_ack,live_parity);
        reply=live_rdata;
    endtask
    integer block_idle=2, jtag_idle=33,swd_batches=0;
    realtime jtag_start;
    bit swd50_windows;
    task automatic batch(input int count);
        realtime started;
        reg [31:0] status;
        started=$realtime;
        if(count==259 && !swd50_windows)wire_budget_begin();
        write_reg('h10,count,0);
        do read_reg(4,status); while (!(status[2] && status[5]));
        read_reg('h14,status);
        if(count==259 && !swd50_windows)begin
            wire_budget_end(swd_batches==0 ? 0 : 1,1024);
            $display("QUEUE_MBPS swd %s %f",swd_batches==0?"write":"read ",1024000.0/($realtime-started));swd_batches++;
        end
        if (status[15:0]!==count[15:0]) $fatal(1,"SWD batch summary %h",status);
    endtask
    integer jslot=29, sslot=12, skip_jtag=0;
    integer i, edges=0, adjacent=0;
    realtime last_edge;
    real expected_period;
    always @(posedge clk_pin) if (owner>=2 && clk_pin===1) begin
        if (last_edge!=0 && $realtime-last_edge < expected_period-0.010) $fatal(1,"short clock");
        if (last_edge!=0 && $realtime-last_edge < expected_period+0.010) adjacent++;
        last_edge=$realtime;
        edges++;
    end
    always @(target_drive or phy.data_tri)
        if (owner==3 && target_drive===1 && phy.data_tri===0) $fatal(1,"SWD contention");
    reg [31:0] value;
    function automatic [31:0] pattern(input int i);
        pattern=32'h379db26a ^ (32'h9e3779b9*i);
    endfunction
    `include "swd50_queue_windows.svh"
    initial begin
        swd50_windows=$test$plusargs("swd50_windows");
        if($value$plusargs("idle=%d",block_idle))begin end
        if($value$plusargs("jidle=%d",jtag_idle))begin end
        requested_ref_ns=ref_ns;
        if($value$plusargs("fclk1_ns=%f",requested_ref_ns))begin end
        expected_period=(VARIABLE_CLOCK ? requested_ref_ns/2.0 : 10.0) *
                        ($test$plusargs("half_rate") ? 2.0 : 1.0);
        wire_budget_period=expected_period;
        if(VARIABLE_CLOCK) wire_budget_tolerance=0.010;
        if ($value$plusargs("jslot=%d",jslot)) begin end
        if ($value$plusargs("sslot=%d",sslot)) begin end
        skip_jtag=$test$plusargs("swd_only");
        #300; resetn=1;
        wait(owner==1);
        if(VARIABLE_CLOCK) switch_reference();
        released=1;
        if (!skip_jtag) begin
            write_reg(8,0,0); wait_status(5);
            write_reg('h018,256,0);
            write_reg('h01c,($test$plusargs("half_rate") ? 32'h00600004 : 32'h00780002) | (jtag_idle<<10) | (jslot<<3),0);
            write_reg('h014,32'h20008000,0);
            write_reg('h034,6,0);
            for (i=0;i<256;i++) begin
                write_reg('h1004+4*i,~pattern(i),0);
                load_payload('h800+4*i,pattern(i));
            end
            jtag_start=$realtime;write_reg(8,13,0); wait_status(15);
            $display("QUEUE_MBPS jtag write %f",1024000.0/($realtime-jtag_start));
            read_reg('h020,value);
            if (value!==1) $fatal(1,"JTAG write ACK %h, slot %d",value,jslot);
            for (i=0;i<256;i++) if (cm3.u_sys.mem[i]!==pattern(i)) $fatal(1,"JTAG write %d",i);
            write_reg(8,0,0); wait_status(5);
            jtag_start=$realtime;write_reg(8,5,0); wait_status(15);
            $display("QUEUE_MBPS jtag read %f",1024000.0/($realtime-jtag_start));
            read_reg('h020,value); if (value!==1) $fatal(1,"JTAG read ACK %h",value);
            for (i=0;i<256;i++) begin
                check_payload('h1800+4*i,pattern(i));
                read_reg('h2004+4*i,value);
                if (value!==pattern(i)) $fatal(1,"JTAG read %d",i);
            end
            write_reg(8,2,0);
            wait(owner==0);
            if (adjacent<256) $fatal(1,"missing continuous JTAG");
            $display("JTAG_PASS %0d MHz words=256 edges=%d slot=%d",$test$plusargs("half_rate")?50:100,edges,jslot);
        end
        if($test$plusargs("jtag_only")) begin
            $display("SELECTIO_JTAG_ONLY_PASS");
            $finish;
        end
        adjacent=0; last_edge=0;
        use_swd=1; write_reg(8,0,0);
        do read_reg(4,value); while (!value[0]);
        write_reg('h0c,(block_idle<<14)|(sslot<<8)|(sslot<<2)|(!$test$plusargs("half_rate")),0);
        put(0,5'h10,0); batch(1);
        put(0,2,0); batch(1); read_reg('h2000,value);
        if(value!==32'h2ba01477) $fatal(1,"SWD DPIDR %h",value);
        put(0,0,'h1e); put(1,4,'h50000000); batch(2);
        put(0,8,0); put(1,1,'h23000052); batch(2);
        if(swd50_windows) begin
            standard_sram();
            queued_rtt();
            $display("SWD50_WINDOWS_PASS SWD_period_ns=%0.3f SRAM=512 words RTT=8192 bytes",expected_period);
            $finish;
        end
        put(0,5,'h20008000);
        write_reg('h2c,5,0);write_reg('h1c,2,0);
        put(0,5,'h20008000);
        for(i=0;i<256;i++) begin
            put(i+1,'hd,pattern(i));
            load_payload('h2400+4*i,~pattern(i));
        end
        put(257,'he,0); put(258,'h6,0); batch(259);
        for(i=0;i<256;i++) if(cm3.u_sys.mem[i]!==~pattern(i)) $fatal(1,"SWD write %d",i);
        put(0,5,'h20008000);
        write_reg('h1c,1,0);put(0,5,'h20008000);
        for(i=0;i<256;i++) put(i+1,'hf,0);
        put(257,'he,0); put(258,'h6,0); batch(259);
        for(i=0;i<256;i++) begin
            check_payload('h3400+4*i,~pattern(i));
            read_reg('h2008+4*i,value); if(value!==~pattern(i)) $fatal(1,"SWD read %d",i);
        end
        if (adjacent<256) $fatal(1,"missing continuous SWD");
        if ($test$plusargs("half_rate")) begin
            write_reg('h24,'h04000001|(sslot<<1)|(block_idle<<14),0);
            write_reg(8,1,0);repeat(30)@(posedge quad_clk);
            scalar(5,'h20008020,value);
            scalar(14,0,value);
            write_reg(8,0,0);
            write_reg('h24,'h04000000|(sslot<<1)|(block_idle<<14),0);
            repeat(30)@(posedge quad_clk);
            put(0,14,0);put(33,14,0);put(34,6,0);batch(35);
            for(i=0;i<32;i++) check_payload('h3400+4*i,~pattern(i+8));
            write_reg('h24,'h04000001|(sslot<<1)|(block_idle<<14),0);
            write_reg(8,1,0);repeat(30)@(posedge quad_clk);
            scalar(7,0,value);scalar(14,0,value);
            if(value!='h200080a0)$fatal(1,"host TAR changed unexpectedly %h",value);
            scalar(15,0,value);scalar(14,0,value);
            if(value!==~pattern(40))$fatal(1,"host posted read %h",value);
            write_reg(8,0,0);
            write_reg('h24,0,0);repeat(30)@(posedge quad_clk);
            write_reg('h1c,2,0);
            put(0,14,0);put(17,14,0);put(18,6,0);batch(19);
            for (i=0;i<16;i++) if(cm3.u_sys.mem[41+i]!==~pattern(i))$fatal(1,"raw SWD write %d",i);
            $display("LIVE_RAW_QUEUE_PASS SWD scalar and queued DRW share TAR, sample phase and pad owner");
        end
        write_reg(8,1,0); wait(owner==0); released=0; wait(owner==1);
        $display("SELECTIO_PASS SWD %0d MHz words=256 slot=%d",$test$plusargs("half_rate")?50:100,sslot);
        $finish;
    end
    initial begin #8_000_000; $fatal(1,"deadline owner=%d",owner); end
endmodule
