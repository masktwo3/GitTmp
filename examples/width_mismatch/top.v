module top (

);

    wire [31:0] status_net;
    wire [23:0] bus;

    byte_src u_src (
        .status(status_net),
        .lane_a(bus[7:0]),
        .lane_b(bus[23:16])
    );

    word_sink u_sink (
        .status_word(status_net),
        .lane_a_in(bus[7:0]),
        .lane_b_in(bus[23:16])
    );

endmodule
