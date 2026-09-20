module io_monitor (
    inout  wire [7:0] io,
    output wire [7:0] sensed
);
    assign sensed = io;
endmodule
