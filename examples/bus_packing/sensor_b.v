module sensor_b (
    output wire [7:0] pressure,   // placed at packed_bus[15:8]
    output wire [7:0] battery     // placed at packed_bus[31:24]
);

    assign pressure = 8'h22;
    assign battery  = 8'h44;

endmodule
