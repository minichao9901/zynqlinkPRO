`timescale 1ns/1ps
// DMI response ownership across fast data, periodic polls, fences, AP shadow
// reads, final words, and scalar writes which have no following RDBUFF.
module tb_riscv_words;
    reg clk=0;always #4.166667 clk=~clk;
    reg rst_n=0,start=0,fence=0,nv=0;
    reg [7:0] req=0,nreq=0;reg [31:0] value=0,nvalue=0;
    wire valid,busy,nready,tck,tms,tdi,tdo,fd,fe;
    wire [2:0] ack;wire [31:0] data,cycles,bits,scans;
    jtag_core dut(.clk(clk),.rst_n(rst_n),.start(start),.invalidate(1'b0),
        .operation(3'd0),.request(req),.wdata(value),.seq_count(9'd0),.seq_data(256'd0),.seq_tms(1'b0),
        .ir_length(8'd5),.ir_before(11'd0),.ir_after(11'd0),.dr_before(8'd0),.dr_after(8'd0),
        .idcode_ir(8'd1),.riscv_mode(1'b1),.half_delay(4'd1),.idle_cycles(4'd1),.late_return(1'b0),
        .tdo(tdo),.tdo_alternate(tdo),.tdi_sense(tdi),
        .next_valid(nv),.next_request(nreq),.next_wdata(nvalue),.next_ready(nready),
        .result_valid(valid),.busy(busy),.ack(ack),.rdata(data),.tck(tck),.tms(tms),.tdi(tdi),
        .fence_req(fence),.fence_done(fd),.fence_error(fe),
        .stat_cycles(cycles),.stat_bits(bits),.stat_transfers(scans));
    riscv_sba_model #(.RETURN_NS(3)) target(.rst_n(rst_n),.tck(tck),.tms(tms),.tdi(tdi),.tdo(tdo));
    task launch(input [7:0] r,input [31:0] v);
        @(negedge clk);req=r;value=v;start=1;@(negedge clk);start=0;
    endtask
    task result(input [2:0] expected);
        integer budget;
        begin
            budget=0;
            while(!valid && budget<50000)begin @(negedge clk);budget=budget+1;end
            if(!valid || ack!==expected)$fatal(1,"RV req=%h state=%d ack=%d expected=%d",req,dut.state,ack,expected);
        end
    endtask
    task call(input [7:0] r,input [31:0] v,input [2:0] expected);
        launch(r,v);result(expected);@(negedge clk);
    endtask
    task chained_write(input integer count);
        integer i,scans_start;
        begin
            scans_start=scans;nv=0;nreq=13;nvalue=32'h8abc0001;
            launch(13,32'h8abc0000);
            repeat(12)@(negedge clk);nv=1; // Packet BRAM prefetch is not ready at launch.
            for(i=0;i<count;i=i+1)begin
                result(1);@(negedge clk);
                nreq=i+2==count ? 14 : 13;nvalue=32'h8abc0000+i+2;
                nv=0;
                if(i!=count-1)begin repeat(12)@(negedge clk);nv=1;end
            end
            result(1);@(negedge clk);
            if(scans-scans_start>count*3/2)$fatal(1,"RV write is not pipelined: %0d scans for %0d words",scans-scans_start,count);
            $display("PASS RV pipelined writes: words=%0d scans=%0d",count,scans-scans_start);
        end
    endtask
    task chained_read(input integer count);
        integer i,scans_start;
        begin
            scans_start=scans;nv=1;nreq=15;nvalue=0;launch(15,0);
            for(i=0;i<count;i=i+1)begin
                result(1);
                if(i!=0 && data!==(32'h8abc0000+i-1))$fatal(1,"RV posted read %0d got=%h",i,data);
                @(negedge clk);nreq=i+2==count ? 14 : 15;
                if(i==count-1)nv=0;
            end
            result(1);
            if(data!==(32'h8abc0000+count-1))$fatal(1,"RV final read got=%h",data);
            @(negedge clk);
            if(scans-scans_start>count*3/2)$fatal(1,"RV read is not pipelined: %0d scans",scans-scans_start);
            $display("PASS RV pipelined reads: words=%0d scans=%0d",count,scans-scans_start);
        end
    endtask
    integer i,reads_before,writes_before;
    initial begin
        for(i=0;i<8192;i=i+1)target.mem[i]=32'h12340000+i;
        repeat(6)@(negedge clk);rst_n=1;
        call(4,1,1);call(1,'h23000012,1);call(5,'hf0406000,1);
        chained_write(128);
        for(i=0;i<128;i=i+1)if(target.mem['h6000/4+i]!==(32'h8abc0000+i))$fatal(1,"RV write data %0d",i);
        call(5,'hf0406000,1);chained_read(128);
        // A fence consumes the pending DMI response, but the next AP read
        // still owns that exact word, not the following word or SBCS.
        call(5,'hf0406000,1);call(15,0,1);call(15,0,1);
        if(data!==32'h8abc0000)$fatal(1,"RV first posted word");
        @(negedge clk);fence=1;wait(fd);@(negedge clk);fence=0;
        if(fe)$fatal(1,"RV unexpected fence error");
        call(15,0,1);if(data!==32'h8abc0001)$fatal(1,"RV fence swallowed pending data %h",data);
        call(14,0,1);if(data!==32'h8abc0002)$fatal(1,"RV fence tail %h",data);
        call(5,'hf0406000,1);call(15,0,1);call(3,0,1);
        if(data!==32'h8abc0000)$fatal(1,"RV AP shadow swallowed posted word %h",data);
        call(14,0,1);if(data!==32'h23000012)$fatal(1,"RV AP CSW shadow %h",data);
        // Fixed-address samples still perform periodic checks. Give each bus
        // read a new value so a swallowed response cannot hide behind constants.
        call(1,'h23000002,1);call(5,'hf0407000,1);call(15,0,1);
        for(i=1;i<65;i=i+1)begin
            call(15,0,1);if(data!==i)$fatal(1,"RV periodic poll lost fixed sample %0d: %h",i,data);
        end
        call(14,0,1);if(data!==65)$fatal(1,"RV fixed tail after periodic poll %h",data);
        // Last RAM word must not cause a read beyond the implemented region.
        call(1,'h23000012,1);
        reads_before=target.bus_reads;call(5,'hf0407ffc,1);call(15,0,1);call(14,0,1);
        if(data!==32'h12341fff || target.bus_reads!=reads_before+1 || target.out_of_range_reads!=0)
            $fatal(1,"RV RAM boundary prefetch data=%h reads=%0d OOB=%0d",data,target.bus_reads-reads_before,target.out_of_range_reads);
        // Side-effecting MMIO is never prefetched, even if AP auto-inc is off.
        call(1,'h23000002,1);call(5,'h40010000,1);call(15,0,1);call(14,0,1);
        if(data!==1 || target.mmio_reads!=1)$fatal(1,"RV MMIO over-read %h / %0d",data,target.mmio_reads);
        // An unchained write (RTT RdOff) is checked before ACK, with no replay.
        call(5,'hf0406100,1);writes_before=target.bus_writes;target.fault_next=1;
        call(13,32'hdeadbeef,4);
        if(target.bus_writes!=writes_before+1)$fatal(1,"RV failed write was replayed");
        call(0,'h1e,1);
        // A packet may acknowledge a posted write, but its mandatory final
        // RDBUFF must surface the last write's sticky bus error.
        call(1,'h23000012,1);call(5,'hf0406104,1);
        writes_before=target.bus_writes;target.fault_next=1;
        nv=1;nreq=14;nvalue=0;launch(13,32'h55aa1234);result(1);
        @(negedge clk);nv=0;result(4);@(negedge clk);
        if(target.bus_writes!=writes_before+1)$fatal(1,"RV packet tail failure replayed write");
        call(0,'h1e,1);
        $display("PASS RV response ownership: polls/fence/shadows/tail, bounded read-ahead, scalar write confirmation");
        $finish;
    end
    initial begin #30000000;$fatal(1,"RV words watchdog");end
endmodule
