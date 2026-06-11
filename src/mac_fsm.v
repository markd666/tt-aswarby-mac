/*
 * mac_fsm - strobe handshake controller for mac_core
 *
 * Turns an externally driven `strobe` level into a single-cycle `do_op` pulse,
 * so each rising edge of strobe executes exactly one command in the datapath
 * (no repeated accumulation while strobe is held high). `done` trails `do_op`
 * by one cycle as a completion flag for the host.
 *
 * Note: `strobe` is assumed roughly synchronous to clk (it is driven by the
 * Tiny Tapeout Commander). For a genuinely asynchronous source a two-flop
 * synchroniser would be inserted ahead of this FSM.
 *
 * Copyright (c) 2026 Mark Shilton
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module mac_fsm (
    input  wire clk,
    input  wire rst_n,
    input  wire strobe,
    output reg  do_op,    // one-cycle execute pulse
    output reg  done      // one-cycle completion pulse (do_op delayed by 1)
);

  localparam S_WAIT_HIGH = 1'b0,   // arm: waiting for strobe to go high
             S_WAIT_LOW  = 1'b1;   // executed: waiting for strobe to fall (re-arm)

  reg state;

  always @(posedge clk) begin
    if (!rst_n) begin
      state <= S_WAIT_HIGH;
      do_op <= 1'b0;
      done  <= 1'b0;
    end else begin
      do_op <= 1'b0;        // default: one-shot, deassert next cycle
      done  <= do_op;       // completion trails execution by one cycle
      case (state)
        S_WAIT_HIGH:
          if (strobe) begin
            do_op <= 1'b1;
            state <= S_WAIT_LOW;
          end
        S_WAIT_LOW:
          if (!strobe)
            state <= S_WAIT_HIGH;
      endcase
    end
  end

endmodule
