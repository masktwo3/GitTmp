module top (

);

    wire [31:0] w_u_sink_status_word;
    wire [7:0] w_u_sink_lane_a_in;
    wire [7:0] w_u_sink_lane_b_in;

    byte_src u_src (
        .status(w_u_sink_status_word),
        .lane_a(w_u_sink_lane_a_in),
        .lane_b(w_u_sink_lane_b_in)
    );

    word_sink u_sink (
        .status_word(w_u_sink_status_word),
        .lane_a_in(w_u_sink_lane_a_in),
        .lane_b_in(w_u_sink_lane_b_in)
    );

endmodule
