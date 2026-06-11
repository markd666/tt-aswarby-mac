/*
 * tt_um_aswarby_mac - Tiny Tapeout top wrapper
 *
 * A byte-serial, weight-stationary signed-INT8 multiply-accumulate engine.
 * The compute primitive of the quantized detectors this project deploys on
 * edge NPUs, reduced to a single Tiny Tapeout tile as a proof-of-skill block.
 *
 * Pin map
 * -------
 *   ui_in[7:0]   data byte in (signed INT8: weight or activation)
 *   uio_in[1:0]  command  : 00 NOP / 01 load weight / 10 MAC / 11 clear
 *   uio_in[2]    strobe   : rising edge executes one command
 *   uio_in[4:3]  rd_sel   : selects which accumulator byte appears on uo_out
 *   uio_in[7:5]  unused
 *   uo_out[7:0]  selected accumulator byte (read 4 bytes LSB-first for INT32)
 *   uio_out[5]   done     : one-cycle completion pulse
 *   uio_out[6]   ovf      : sticky saturation flag (cleared by clear/reset)
 *
 * Copyright (c) 2026 Mark Shilton
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_aswarby_mac (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (1=output, 0=input)
    input  wire       ena,      // high while the design is selected
    input  wire       clk,      // clock
    input  wire       rst_n     // active-low reset
);

  wire       do_op;
  wire       done;
  wire       ovf;
  wire [7:0] rd_byte;

  mac_fsm u_fsm (
      .clk   (clk),
      .rst_n (rst_n),
      .strobe(uio_in[2]),
      .do_op (do_op),
      .done  (done)
  );

  mac_core u_core (
      .clk    (clk),
      .rst_n  (rst_n),
      .do_op  (do_op),
      .cmd    (uio_in[1:0]),
      .data   (ui_in),
      .rd_sel (uio_in[4:3]),
      .rd_byte(rd_byte),
      .ovf    (ovf)
  );

  assign uo_out  = rd_byte;

  // Bidirectional bus: bits 5,6,7 are outputs; bits 0..4 are inputs.
  assign uio_out = {1'b0, ovf, done, 5'b0_0000};
  assign uio_oe  = 8'b1110_0000;

  // Silence unused-signal warnings (ena and the spare uio inputs).
  wire _unused = &{ena, uio_in[7:5], 1'b0};

endmodule
