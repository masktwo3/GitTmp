module sensor_a (
    output wire [7:0] temp,       // placed at packed_bus[7:0]
    output wire [7:0] humidity    // placed at packed_bus[23:16]
);

    assign temp     = 8'h11;
    assign humidity = 8'h33;

endmodule
