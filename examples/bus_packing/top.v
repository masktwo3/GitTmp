module top (

);

    wire [31:0] w_u_sink_packed_word;

    sensor_a u_a (
        .temp(w_u_sink_packed_word[7:0]),
        .humidity(w_u_sink_packed_word[23:16])
    );

    sensor_b u_b (
        .pressure(w_u_sink_packed_word[15:8]),
        .battery(w_u_sink_packed_word[31:24])
    );

    packed_sink u_sink (
        .packed_word(w_u_sink_packed_word)
    );

endmodule
