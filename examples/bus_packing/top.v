module top (

);

    wire [31:0] w_u_sink_packed_word;
    wire [7:0] w_u_a_temp;
    wire [7:0] w_u_b_pressure;
    wire [7:0] w_u_a_humidity;
    wire [7:0] w_u_b_battery;

    assign w_u_sink_packed_word[7:0] = w_u_a_temp;
    assign w_u_sink_packed_word[15:8] = w_u_b_pressure;
    assign w_u_sink_packed_word[23:16] = w_u_a_humidity;
    assign w_u_sink_packed_word[31:24] = w_u_b_battery;

    sensor_a u_a (
        .temp(w_u_a_temp),
        .humidity(w_u_a_humidity)
    );

    sensor_b u_b (
        .pressure(w_u_b_pressure),
        .battery(w_u_b_battery)
    );

    packed_sink u_sink (
        .packed_word(w_u_sink_packed_word)
    );

endmodule
