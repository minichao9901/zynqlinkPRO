// Pin-clock accounting for the marked 50 MHz diagnostic windows.
bit wire_budget_active=0;
integer wire_rises, wire_extended, wire_short;
realtime wire_start, wire_first, wire_last, wire_extra, wire_deficit;
integer ack_drain_cycles, read_drain_cycles, handoffs;
realtime last_link_done, handoff_ns;
bit saw_link;

task automatic wire_budget_begin;
    if($test$plusargs("wire_budget")) begin
        wire_start=$realtime;
        wire_rises=0;wire_extended=0;wire_short=0;
        wire_first=0;wire_last=0;wire_extra=0;wire_deficit=0;
        ack_drain_cycles=0;read_drain_cycles=0;handoffs=0;
        last_link_done=0;handoff_ns=0;saw_link=0;
        wire_budget_active=1;
    end
endtask

always @(posedge wire_budget_pin) if(wire_budget_active && wire_budget_pin===1'b1) begin
    if(!wire_rises) wire_first=$realtime;
    else if($realtime-wire_last>20.001) begin
        wire_extended++;
        wire_extra=wire_extra+($realtime-wire_last)-20.0;
    end else if($realtime-wire_last<19.999) begin
        wire_short++;
        wire_deficit=wire_deficit+20.0-($realtime-wire_last);
    end
    wire_last=$realtime;
    wire_rises++;
end

// These events are sampled at the 100 MHz quad clock, independent of the
// output serializer latency seen by the physical SWCLK edge monitor.
task automatic wire_budget_link(input bit ack_drain, input bit read_drain,
                                input bit done, input bit launch);
    if(wire_budget_active) begin
        saw_link=1;
        if(ack_drain)ack_drain_cycles++;
        if(read_drain)read_drain_cycles++;
        if(done)last_link_done=$realtime;
        if(launch && last_link_done!=0) begin
            handoffs++;
            handoff_ns+=($realtime-last_link_done);
            last_link_done=0;
        end
    end
endtask

// 0 = SRAM write, 1 = SRAM read, 2 = first RTT buffer.
task automatic wire_budget_end(input integer workload,input integer bytes);
    if(wire_budget_active) begin
        wire_budget_active=0;
        if(wire_rises<2)$fatal(1,"missing measured SWCLK edges");
        $display("WIRE_BUDGET work=%0d bytes=%0d ns=%0.3f rises=%0d lead_ns=%0.3f tail_ns=%0.3f extended=%0d extra_ns=%0.3f short=%0d deficit_ns=%0.3f",
                 workload,bytes,$realtime-wire_start,wire_rises,wire_first-wire_start,$realtime-wire_last,
                 wire_extended,wire_extra,wire_short,wire_deficit);
        if(saw_link)
            $display("LINK_BUDGET work=%0d ack_drain_cycles=%0d read_drain_cycles=%0d handoffs=%0d handoff_ns=%0.3f",
                     workload,ack_drain_cycles,read_drain_cycles,handoffs,handoff_ns);
    end
endtask
