module top (

);

    wire [31:0] w_u_sink_status_word;
    wire [7:0] w_u_src_status;
    wire [7:0] w_u_sink_lane_a_in;
    wire [7:0] w_u_src_lane_a;
    wire [7:0] w_u_sink_lane_b_in;
    wire [7:0] w_u_src_lane_b;

    assign w_u_sink_status_word = w_u_src_status;
    assign w_u_sink_lane_a_in = w_u_src_lane_a;
    assign w_u_sink_lane_b_in = w_u_src_lane_b;

    byte_src u_src (
        .status(w_u_src_status),
        .lane_a(w_u_src_lane_a),
        .lane_b(w_u_src_lane_b)
    );

    word_sink u_sink (
        .status_word(w_u_sink_status_word),
        .lane_a_in(w_u_sink_lane_a_in),
        .lane_b_in(w_u_sink_lane_b_in)
    );

endmodule
