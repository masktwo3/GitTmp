module top (

);

    wire [31:0] w_u_a_humidity;

    sensor_a u_a (
        .temp(w_u_a_humidity[7:0]),
        .humidity(w_u_a_humidity[23:16])
    );

    sensor_b u_b (
        .pressure(w_u_a_humidity[15:8]),
        .battery(w_u_a_humidity[31:24])
    );

    packed_sink u_sink (
        .packed_word(w_u_a_humidity)
    );

endmodule
