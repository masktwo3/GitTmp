module top (

);

    wire [31:0] w_u_sink_packed_word;
    wire [31:0] w_u_a_data;
    wire [31:0] w_u_b_data;
    wire w_u_flag_flag;

    assign w_u_sink_packed_word[15:8] = w_u_a_data[23:16];
    assign w_u_sink_packed_word[27:16] = w_u_b_data[15:4];
    assign w_u_sink_packed_word[31:28] = 4'hA;
    assign w_u_sink_packed_word[7] = w_u_flag_flag;
    assign w_u_sink_packed_word[6:0] = 7'h55;

    wide_src_a u_a (
        .data(w_u_a_data)
    );

    wide_src_b u_b (
        .data(w_u_b_data)
    );

    flag_src u_flag (
        .flag(w_u_flag_flag)
    );

    wide_sink u_sink (
        .packed_word(w_u_sink_packed_word)
    );

endmodule
