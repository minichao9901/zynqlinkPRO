"""Offline clock arithmetic from the accompanying read-only PS register snapshot.

This never connects to hardware, writes registers, or creates a product image.
Nominal PS_REF is 100/3 MHz; firmware uses its rounded 33,333,333 Hz value.
"""
from fractions import Fraction
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
snapshot = json.loads((HERE / 'live-clock-registers.json').read_text())
regs = {name: int(value, 16) for name, value in snapshot['registers'].items()}
ref = Fraction(100_000_000, 3)
target = 135_000_000
sources = {'IO': 'IO_PLL_CTRL', 'ARM': 'ARM_PLL_CTRL', 'DDR': 'DDR_PLL_CTRL'}
choices = []
for source, register in sources.items():
    feedback = (regs[register] >> 12) & 127
    candidates = [(ref * feedback / d0 / d1, d0, d1)
                  for d0 in range(1, 64) for d1 in range(1, 64)
                  if ref * feedback / d0 / d1 <= target]
    hz, d0, d1 = max(candidates)
    choices.append(dict(source=source, feedback=feedback,
                        nominalPllHz=float(ref * feedback),
                        highestNominalHzAtOrBelowTarget=float(hz),
                        divisor0=d0, divisor1=d1,
                        firmwareCalculatedHz=33_333_333 * feedback // d0 // d1,
                        exactTargetPossible=any(ref * feedback / a / b == target
                                                for a in range(1, 64)
                                                for b in range(1, 64))))
legal_feedback = [n for n in range(1, 128) if 780_000_000 <= ref*n <= 1_800_000_000]
legal_exact = [(n, d0, d1) for n in legal_feedback
               for d0 in range(1, 64) for d1 in range(1, 64)
               if ref*n/d0/d1 == target]
unlimited = [(ref*n, n, d0, d1) for n in range(1, 128)
             for d0 in range(1, 64) for d1 in range(1, 64)
             if ref*n/d0/d1 == target]
minimum, n, d0, d1 = min(unlimited)
live = {}
for clock in ('FPGA0_CLK_CTRL', 'FPGA1_CLK_CTRL'):
    value = regs[clock]
    source = {0: 'IO', 1: 'IO', 2: 'ARM', 3: 'DDR'}[(value >> 4) & 3]
    div0, div1 = (value >> 8) & 63, (value >> 20) & 63
    feedback = (regs[sources[source]] >> 12) & 127
    live[clock] = dict(source=source, divisor0=div0, divisor1=div1,
                       nominalHz=float(ref*feedback/div0/div1),
                       firmwareCalculatedHz=33_333_333*feedback//div0//div1)
report = dict(analysisOnly=True, hardwareModified=False, bitstreamGenerated=False,
              requestedNominalHz=target, nominalReferenceHz=str(ref),
              roundedFirmwareReferenceHz=33_333_333,
              targetPart='xc7z020clg400-2', psPllMinHz=780_000_000,
              psPllMaxHz=1_800_000_000, legalFeedbackRange=[min(legal_feedback), max(legal_feedback)],
              exactTargetWithAnyLegalPsPll=bool(legal_exact),
              lowestPsPllForExactTarget=dict(feedback=n, pllHz=float(minimum),
                                             divisor0=d0, divisor1=d1),
              currentSources=choices, liveFclks=live,
              runtimeFrequencyCounterUsed=False,
              status='pending user clock-point decision; no source/PLL changes applied')
(HERE / 'clock-feasibility.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
