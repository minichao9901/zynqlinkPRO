"""Compare the original 200 MS/s and candidate 400 MS/s TPIU receivers on identical pins."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--jobs",type=int,choices=range(1,5),default=2)
    args=ap.parse_args()
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    model=out/"rate.vvp"
    subprocess.run(["iverilog","-g2012","-s","tb_etm_rate","-o",model,
                    ROOT/"fpga/sim/tb_etm_rate.sv",ROOT/"fpga/sim/sim_primitives.v",
                    *sorted((ROOT/"fpga/rtl").glob("orbtrace*.v"))],check=True)
    points=[(f,p) for f in (24,36,48,50,52,56,60,64,72,80,88,96,100,104,112)
            for p in (90,690,1290,1890,2490,3090,3690,4290)]
    def run(point):
        f,p=point
        proc=subprocess.run(["vvp",model,f"+mhz={f}",f"+phase_ps={p}"],capture_output=True,text=True,check=True,timeout=90)
        _,mf,mp,count0,bad0,count1,bad1=next(l for l in proc.stdout.splitlines() if l.startswith("ETM_RATE ")).split()
        assert (int(mf),int(mp))==point
        return dict(mhz=f,phase_ps=p,legacy_frames=int(count0),legacy_errors=int(bad0),
                    ddr_frames=int(count1),ddr_errors=int(bad1))
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        rows=list(pool.map(run,points))
    (out/"results.json").write_text(json.dumps(rows,indent=2)+"\n")
    for f in sorted({row["mhz"] for row in rows}):
        r=[p for p in rows if p["mhz"]==f]
        print(f,*(sum(p[k+"_frames"]==128 and p[k+"_errors"]==0 for p in r) for k in ("legacy","ddr")))
    return 0 if all(p["ddr_frames"]==128 and p["ddr_errors"]==0 for p in rows if p["mhz"]<=64) else 1


if __name__=="__main__":raise SystemExit(main())
