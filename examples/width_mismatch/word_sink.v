module word_sink (
    input wire [31:0] status_word,  // reads the whole (zero-extended) net
    input wire [7:0]  lane_a_in,     // reads only bus[7:0]
    input wire [7:0]  lane_b_in      // reads only bus[23:16]
);

    initial begin
        #1;
        $display("status_word=%h lane_a_in=%h lane_b_in=%h",
                  status_word, lane_a_in, lane_b_in);
    end

endmodule
