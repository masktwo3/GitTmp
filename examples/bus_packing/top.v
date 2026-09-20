module top (

);

    wire [31:0] packed_bus;

    sensor_a u_a (
        .temp(packed_bus[7:0]),
        .humidity(packed_bus[23:16])
    );

    sensor_b u_b (
        .pressure(packed_bus[15:8]),
        .battery(packed_bus[31:24])
    );

    packed_sink u_sink (
        .packed_word(packed_bus)
    );

endmodule
