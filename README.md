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

RTL complete; all cocotb tests pass locally on Icarus Verilog. GDS hardening via
the Tiny Tapeout `tt-gds-action` runs in GitHub Actions (sky130A). Shuttle
submission is deferred until the area/timing reports are reviewed — see the
project plan for the build-first, commit-later sequencing.

## License

Apache-2.0.
