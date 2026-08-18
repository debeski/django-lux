#!/usr/bin/env bash
# Measure this machine's rendering noise, per image.
#
#   ./calibrate.sh [runs]      # default 3
#
# Skia rasterises blurred shadows non-deterministically, and the two themes that
# lean hardest on them (neon: 46 text-shadow + 137 box-shadow; gothic: 15 + 67)
# drift by a few hundred to a few thousand pixels between identical runs. The
# tempting fixes both cost real coverage: raising --threshold blunts colour
# sensitivity everywhere, and disabling shadows blinds the harness to the 492
# box-shadow declarations the refactor has to convert to tokens.
#
# So instead: shoot the unchanged app several times, record the worst diff each
# image produces, and let compare.mjs hold each image to its own measured
# ceiling. Images that never drift (most of them) stay strict at zero.
#
# Re-run this after changing the machine, the browser, or the route matrix —
# and NOT after changing CSS, or you will bake a regression into the ceiling.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:$PATH"

RUNS="${1:-3}"

if [[ ! -d shots/baseline ]]; then
  echo "no baseline yet — run ./run.sh baseline first" >&2
  exit 2
fi

echo "calibrating over $RUNS runs of unchanged code..."
rm -f state/noise-*.json

for i in $(seq 1 "$RUNS"); do
  echo "  run $i/$RUNS"
  ./run.sh current > /dev/null 2>&1
  node compare.mjs --min-px 1 --json "state/noise-$i.json" > /dev/null 2>&1 || true
done

node -e '
const fs=require("fs");
const files=fs.readdirSync("state").filter(f=>f.startsWith("noise-")&&f.endsWith(".json"));
if(!files.length){console.error("no calibration data");process.exit(1);}
const worst={};
for(const f of files){
  const d=JSON.parse(fs.readFileSync("state/"+f));
  for(const [k,v] of Object.entries(d)) worst[k]=Math.max(worst[k]||0,v);
}
fs.writeFileSync("noise.json",JSON.stringify(worst,null,1));
const drifty=Object.entries(worst).filter(([,v])=>v>0).sort((a,b)=>b[1]-a[1]);
console.log(`\n  images measured : ${Object.keys(worst).length}`);
console.log(`  never drift     : ${Object.keys(worst).length-drifty.length}`);
console.log(`  drift at all    : ${drifty.length}`);
if(drifty.length){
  console.log("\n  image                            max noise px");
  for(const [k,v] of drifty) console.log(`  ${k.replace(".png","").padEnd(32)} ${v.toLocaleString()}`);
}
console.log("\n  written to noise.json");
'
