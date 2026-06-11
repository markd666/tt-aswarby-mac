# tt-aswarby-mac — Tiny Tapeout INT8 MAC engine

A byte-serial, **weight-stationary signed-INT8 multiply-accumulate** engine on a
single Tiny Tapeout tile. It is the compute atom of the quantized object
detectors deployed elsewhere in the Aswarby project — reduced to one block as a
proof-of-skill pass through the full open-source RTL → GDS → silicon flow.

```
acc = clamp_int32( acc + weight * activation )   // signed INT8 operands, INT32 saturating
```

## Layout

| Path | What |
|---|---|
| `src/mac_core.v` | datapath: weight reg, signed 8×8 multiplier, saturating 32-bit accumulator, byte-read mux |
| `src/mac_fsm.v` | strobe-handshake controller (one strobe edge = one op) |
| `src/tt_um_aswarby_mac.v` | TT top wrapper + pin map |
| `test/` | cocotb suite + Verilog testbench (golden-model checked) |
| `tools/export_vectors.py` | generate INT8 test vectors (random, or from a real quantized layer) |
| `docs/info.md` | datasheet: protocol, pin map, worked example |
| `info.yaml` | TT project metadata + pinout |

The pin protocol and a worked example are in [`docs/info.md`](docs/info.md).

## Running the tests

Requires `iverilog` and `cocotb==2.0.1`:

```bash
cd test
make            # full RTL suite (incl. exhaustive saturation, ~100 s)
SKIP_SLOW=1 make   # fast subset (skips the two exhaustive saturation tests)
```

The same suite re-runs against the synthesized gate-level netlist in CI
(`GATES=yes`, the `gl_test` job) as the signoff gate.

## Status

**Submission-ready for the GF26B shuttle** (GlobalFoundries 180nm, `gf180mcuD`).

- RTL complete; cocotb suite 7/7 on Icarus (incl. both INT32 saturation directions).
- GDS hardens cleanly via `tt-gds-action@ttgf26b`; all CI gates green —
  `gds`, gate-level `gl_test`, all 11 Tiny Tapeout prechecks, and the GDS viewer.
- Occupies ~54% of one 1×1 tile.
- Timing: setup closes with +7.4 ns margin at the typical corner; a small
  residual remains only at the slow `ss` 125°C/3.0V corner (≈−1.6 ns, a
  sign-off warning, not a blocker). The design runs at the 50 MHz target under
  normal conditions.

Layout viewer: https://markd666.github.io/tt-aswarby-mac/

## License

Apache-2.0.
