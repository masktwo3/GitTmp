module io_nibble (
    input  wire       drive_en,
    input  wire [3:0] drive_val,
    inout  wire [3:0] io_lo
);
    assign io_lo = drive_en ? drive_val : 4'bz;
endmodule
