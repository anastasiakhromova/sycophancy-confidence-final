"""Build offline English review forms from the frozen English validation packets."""

from pathlib import Path
import argparse
import json
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from sycophancy.human_review import validate_packet, write_review_html


INDEX_HTML = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';style-src 'unsafe-inline';base-uri 'none';form-action 'none'">
<title>Response review — start here</title>
<style>body{font:18px/1.65 system-ui,sans-serif;background:#f5f4ee;color:#172b23;margin:0}main{max-width:760px;margin:6vh auto;padding:28px}h1{font-size:42px;line-height:1.1;letter-spacing:-.04em}a{color:#11583f}.cards{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:28px 0}.card{display:block;background:white;padding:26px;border:1px solid #d4ddd4;border-radius:16px;text-decoration:none}.card strong{display:block;font-size:25px}.small{font-size:14px;color:#53665a}.tag{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#11583f}li{margin-bottom:9px}@media(max-width:600px){.cards{grid-template-columns:1fr}h1{font-size:34px}}</style></head>
<body><main><div class="tag">Independent annotation · no data sent</div><h1>Read the response.<br>Choose one label.</h1>
<p>Each example contains a claim, a reference fact, and a model response. Model names, experimental conditions, and previous labels are hidden. The original English texts are shown unchanged.</p>
<div class="cards"><a class="card" href="review_a.html"><strong>Packet A →</strong>__COUNT_A__ responses</a><a class="card" href="review_b.html"><strong>Packet B →</strong>__COUNT_B__ responses</a></div>
<ol><li>Enter your ID, for example <code>reviewer-01</code>. Your full name is not required.</li><li>Read the instructions in the form. Choose a label based on the meaning of the response; if you cannot decide, select UNRESOLVED and add a short comment.</li><li>Work independently, without AI or other reviewers’ labels. A second reviewer uses a different ID and completes the same packets separately.</li><li>Download your labels as JSON after each session and before closing. You can work in stages and continue with “Import / resume”.</li><li>Give the coordinator your latest JSON file for each packet. Do not edit the files manually.</li></ol>
<p class="small">Open these files in a regular browser. Progress is saved locally in that browser; moving the file or clearing browser data may reset the draft. Your JSON file is your backup. No labels are preselected.</p></main></body></html>
'''


def build(project: Path, output: Path) -> None:
    """Render original packet text without loading or applying translations."""
    packets = []
    for source, name in (("development", "review_a"), ("candidate_holdout", "review_b")):
        packet = json.loads(
            (project / "data/validation_v2" / (source + ".json")).read_text(encoding="utf-8")
        )
        validate_packet(packet)
        packets.append((name, packet))

    output.mkdir(parents=True, exist_ok=True)
    for name, packet in packets:
        path = write_review_html(packet, output / (name + ".html"))
        # Keep generated HTML byte-stable across platforms. Original response
        # line breaks remain escaped inside the inert JSON packet.
        path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    counts = [len(packet["items"]) for _, packet in packets]
    (output / "index.html").write_text(
        INDEX_HTML.replace("__COUNT_A__", str(counts[0])).replace("__COUNT_B__", str(counts[1])),
        encoding="utf-8",
        newline="\n",
    )
    (output / "README.txt").write_text(
        "index.html - choose a review packet.\n"
        "review_a.html - Packet A, original English text.\n"
        "review_b.html - Packet B, original English text.\n\n"
        "Open index.html in a browser. Enter your reviewer ID, read each response, and choose a label.\n"
        "Work independently, without AI or other reviewers' labels. No labels are preselected.\n"
        "You may work in stages. Before closing, download your labels as JSON.\n"
        "To resume, import that JSON into the same packet and continue under the same ID.\n"
        "Give the coordinator your latest JSON file for each packet; do not edit it manually.\n"
        "These forms work offline. Source texts are unchanged; no translations are loaded.\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"output": str(output), "items": counts, "language": "en", "preselected_labels": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--output", type=Path, default=PROJECT / "reports/review_v2")
    args = parser.parse_args()
    build(args.project.resolve(), args.output.resolve())
