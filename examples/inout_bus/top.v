module top (
    inout [7:0] shared_bus,
    input a_drive_en,
    input [7:0] a_drive_val,
    input b_drive_en,
    input [7:0] b_drive_val,
    input nib_drive_en,
    input [3:0] nib_drive_val,
    output [7:0] a_sensed,
    output [7:0] b_sensed,
    output [7:0] mon_sensed
);

    wire w_u_a_drive_en;
    wire [7:0] w_u_a_drive_val;
    wire w_u_b_drive_en;
    wire [7:0] w_u_b_drive_val;
    wire w_u_nib_drive_en;
    wire [3:0] w_u_nib_drive_val;
    wire [7:0] w_u_a_sensed;
    wire [7:0] w_u_b_sensed;
    wire [7:0] w_u_mon_sensed;

    assign w_u_a_drive_en = a_drive_en;
    assign w_u_a_drive_val = a_drive_val;
    assign w_u_b_drive_en = b_drive_en;
    assign w_u_b_drive_val = b_drive_val;
    assign w_u_nib_drive_en = nib_drive_en;
    assign w_u_nib_drive_val = nib_drive_val;
    assign a_sensed = w_u_a_sensed;
    assign b_sensed = w_u_b_sensed;
    assign mon_sensed = w_u_mon_sensed;

    io_driver u_a (
        .drive_en(w_u_a_drive_en),
        .drive_val(w_u_a_drive_val),
        .sensed(w_u_a_sensed),
        .io(shared_bus)
    );

    io_driver u_b (
        .drive_en(w_u_b_drive_en),
        .drive_val(w_u_b_drive_val),
        .sensed(w_u_b_sensed),
        .io(shared_bus)
    );

    io_monitor u_mon (
        .io(shared_bus),
        .sensed(w_u_mon_sensed)
    );

    io_nibble u_nib (
        .drive_en(w_u_nib_drive_en),
        .drive_val(w_u_nib_drive_val),
        .io_lo(shared_bus[3:0])
    );

endmodule
