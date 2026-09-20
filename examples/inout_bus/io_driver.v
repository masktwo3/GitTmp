module io_driver (
    input  wire       drive_en,
    input  wire [7:0] drive_val,
    output wire [7:0] sensed,
    inout  wire [7:0] io
);
    assign io = drive_en ? drive_val : 8'bz;
    assign sensed = io;
endmodule
