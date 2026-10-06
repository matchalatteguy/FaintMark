"""Build an offline HTML research report from completed benchmark JSON."""
import html
import json
import statistics
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "full"
LABELS = {"trustmark_q": "TrustMark Q · strongest built-in ECC", "pixelseal": "PixelSeal · default strength", "pixelseal_1p4": "PixelSeal · 1.4× strength", "classic_dwt_dct": "Classic DWT/DCT · raw ID"}


def summarize(payload):
    rows = payload["rows"]
    target = [r for r in rows if not r["transform"].endswith("stress")]
    stress = [r for r in rows if r["transform"].endswith("stress")]
    return {
        "total": len(rows), "correct": sum(r["correct"] for r in rows),
        "target_total": len(target), "target_correct": sum(r["correct"] for r in target),
        "stress_total": len(stress), "stress_correct": sum(r["correct"] for r in stress),
        "wrong_recipient": sum(r["wrong_registered_id"] for r in rows),
        "control_total": len(payload["controls"]), "control_matches": sum(r["registered_match"] for r in payload["controls"]),
        "median_psnr_db": statistics.median(r["psnr_db"] for r in payload["quality"]),
        "min_psnr_db": min(r["psnr_db"] for r in payload["quality"]),
        "median_ssim": statistics.median(r["ssim"] for r in payload["quality"]),
        "median_encode_s": statistics.median(r["encode_s"] for r in payload["quality"]),
        "median_decode_s": statistics.median(r["decode_s"] for r in rows),
        "cold_load_s": payload["cold_load_s"],
        "by_transform": {t: {"correct": sum(r["correct"] for r in rows if r["transform"] == t),
                              "total": sum(r["transform"] == t for r in rows)} for t in dict.fromkeys(r["transform"] for r in rows)},
        "by_image": {im: {"correct": sum(r["correct"] for r in target if r["image"] == im),
                           "total": sum(r["image"] == im for r in target),
                           "psnr_db": statistics.median(r["psnr_db"] for r in payload["quality"] if r["image"] == im)}
                      for im in dict.fromkeys(r["image"] for r in rows)},
    }


def gallery(engines):
    names = ["astronaut", "coffee", "text_document", "smooth_gradient"]
    cols = ["original"] + list(engines)
    cell_w, cell_h = 360, 280
    canvas = Image.new("RGB", (cell_w * len(cols), cell_h * len(names)), "#ffffff")
    draw = ImageDraw.Draw(canvas)
    for y, name in enumerate(names):
        for x, engine in enumerate(cols):
            path = ROOT / "fixtures" / f"{name}.png" if engine == "original" else OUT / "previews" / f"{engine}_{name}.png"
            im = Image.open(path).convert("RGB")
            thumb = ImageOps.contain(im, (cell_w - 16, cell_h - 48))
            canvas.paste(thumb, (x * cell_w + (cell_w - thumb.width) // 2, y * cell_h + 38))
            draw.text((x * cell_w + 10, y * cell_h + 8), f"{engine} · {name}", fill="#263238", font_size=14)
    canvas.save(OUT / "comparison.png")


def main():
    payloads = {p.stem: json.loads(p.read_text()) for p in sorted(OUT.glob("*.json")) if p.stem in LABELS}
    summaries = {k: summarize(v) for k, v in payloads.items()}
    (OUT / "summary.json").write_text(json.dumps(summaries, indent=2))
    print(json.dumps(summaries, indent=2))
    gallery(payloads)
    env = json.loads((OUT / "environment.json").read_text())
    transforms = list(next(iter(summaries.values()))["by_transform"])
    headers = "".join(f"<th>{html.escape(LABELS[k])}</th>" for k in summaries)
    transform_rows = ""
    for t in transforms:
        transform_rows += "<tr><td>" + t.replace("_", " ") + "</td>"
        for s in summaries.values():
            v = s["by_transform"][t]
            transform_rows += f"<td>{v['correct']}/{v['total']}</td>"
        transform_rows += "</tr>"
    metric_rows = ""
    for label, key, fmt in [("Routine exact recovery", "target_correct", None), ("Stress exact recovery", "stress_correct", None),
                             ("Median image PSNR (higher better)", "median_psnr_db", "{:.1f} dB"),
                             ("Median image SSIM (closer to 1 better)", "median_ssim", "{:.4f}"),
                             ("Median encode time", "median_encode_s", "{:.3f} s"),
                             ("Median decode time", "median_decode_s", "{:.3f} s"),
                             ("Wrong registered recipient IDs", "wrong_recipient", "{}"),
                             ("Unmarked controls matching registry", "control_matches", None)]:
        metric_rows += f"<tr><td>{label}</td>"
        for s in summaries.values():
            denom = "target_total" if key == "target_correct" else "stress_total" if key == "stress_correct" else "control_total"
            val = fmt.format(s[key]) if fmt else f"{s[key]}/{s[denom]}"
            metric_rows += f"<td>{val}</td>"
        metric_rows += "</tr>"
    image_rows = ""
    for im in next(iter(summaries.values()))["by_image"]:
        image_rows += f"<tr><td>{im}</td>"
        for s in summaries.values():
            v = s["by_image"][im]
            image_rows += f"<td>{v['correct']}/{v['total']} · {v['psnr_db']:.1f} dB</td>"
        image_rows += "</tr>"
    recommendation = (ROOT / "recommendation-fragment.html").read_text() if (ROOT / "recommendation-fragment.html").exists() else "<p>Recommendation pending analysis.</p>"
    document = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Local invisible watermarking · A/B test</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;color:#18262d;background:#f5f7f8;margin:0}}main{{max-width:1100px;margin:auto;padding:40px 24px}}h1{{font-size:38px;line-height:1.15}}h2{{margin-top:42px;font-size:25px}}.eyebrow{{color:#58717d;font-size:13px;letter-spacing:.1em}}section{{background:white;border:1px solid #dfe5e8;border-radius:14px;padding:22px;margin:22px 0}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:10px;border-bottom:1px solid #e1e7e9;text-align:left}}th{{background:#eef4f5}}.scroll{{overflow-x:auto}}img{{width:100%;height:auto}}a{{color:#166178}}code{{background:#edf2f4;padding:2px 5px}}li{{margin:9px 0}}.note{{color:#52646e}}@media print{{body{{background:white}}main{{padding:0}}section{{break-inside:avoid}}}}</style>
<main><div class="eyebrow">LOCAL RESEARCH · 6 OCTOBER 2026 · NO PAID SERVICES</div>
<h1>Which invisible watermark should power a simple local app?</h1>
<p>Controlled A/B comparison for recipient-specific copies intended for Discord, Instagram and WhatsApp.</p>
<section>{recommendation}</section>
<h2>Measured results</h2><p>Every success is an exact recovered 40-bit recipient-copy ID. No nearest-ID guesses.</p>
<div class="scroll"><table><tr><th>Measure</th>{headers}</tr>{metric_rows}</table></div>
<h2>Recovery by transformation</h2><p>JPEG quality numbers are Pillow encoder settings; they are not claims about any platform's internal settings. Stress rows exceed the first-version target.</p>
<div class="scroll"><table><tr><th>Transformation</th>{headers}</tr>{transform_rows}</table></div>
<h2>Recovery by image type</h2><p>Routine successes / cases, followed by median watermark-only PSNR. The 2048-pixel astronaut is an upscaled derivative, not a new independent photograph.</p>
<div class="scroll"><table><tr><th>Fixture</th>{headers}</tr>{image_rows}</table></div>
<h2>Visual comparison</h2><p class="note">Thumbnails can conceal artifacts. Full-resolution watermarked examples are in <code>results/full/previews</code>; PSNR and SSIM complement visual inspection but do not prove invisibility.</p>
<img src="results/full/comparison.png" alt="Original and watermarked photos, document and smooth gradient">
<h2>Method and reproducibility</h2><ul>
<li>Nine fixtures: six bundled photographic examples (including one grayscale), two generated smooth/text images, and one explicitly upscaled photographic derivative. Five deterministic distinct IDs per fixture; 13 transformations; 585 marked cases and 117 unmarked controls per engine.</li>
<li>Routine group: unchanged PNG; JPEG 95, 85, 70, 50; WebP 80, 50; half-size JPEG 70; longest side capped at 1080 then JPEG 80; three successive 0.75 resizes and JPEG encodes at 80, 70, 60. Stress: JPEG 30, quarter-size JPEG 50, longest side capped at 160 then JPEG 50.</li>
<li>The initial neural-engine comparison uses documented default strengths. A separate PixelSeal run increases its blending strength by 1.4× to bring its median PSNR close to TrustMark Q for a more comparable image-quality budget. TrustMark Q carries 40 bits using BCH_SUPER (up to eight bit errors). PixelSeal carries a 40-bit ID, 16-bit checksum, BCH with m=8/t=24, plus padding to 256 bits. The classical baseline carries the same 40-bit ID without ECC. This compares usable pipelines exploiting their native capacity, not identical coding schemes. The classical result does not rule out custom classical algorithms with stronger error correction.</li>
<li>Outputs are quantized to 8-bit RGB and serialized before extraction. PNG preserves the marked master. JPEG uses 4:2:0 chroma subsampling. Resizing uses Lanczos. Controls undergo the same transformations.</li>
<li>Encode and decode timings exclude transforms and model loading, use a warm model and explicit GPU synchronization. Model initialization is recorded separately in raw data. Hardware: Apple M2 Max, 32 GB RAM; device {env['device']}; Torch {env['torch']}; four CPU threads.</li>
<li>The checksum is an accidental-error check, not authentication. The registry accepts only exact known IDs. Copy IDs are global per export and should be generated securely and checked for collisions in the eventual app.</li>
</ul>
<h2>Limits of this evidence</h2><ul>
<li>No images were sent to Discord, Instagram or WhatsApp. These are controlled local transformations. Real platform compatibility remains unverified; no private account credentials or paid APIs were used.</li>
<li>Many fixtures are 451–1000 pixels wide; capping at 1080 changes only the larger fixtures. An upscaled fixture tests output size but does not replace native high-resolution photographs.</li>
<li>This is a small convenience sample with correlated transformations and only five messages per image. Aggregate fractions are descriptive, not a population reliability estimate.</li>
<li>No adversarial removal, collusion, severe cropping, screen capture, colour-profile/HEIC handling or legal ownership proof is evaluated. An absent/unreadable watermark is inconclusive.</li>
<li>Zero false registry matches in this control set, if observed, does not establish a zero false-positive rate. A recovered registered ID identifies an assigned copy, not the person who posted it.</li>
</ul>
<h2>Sources and local evidence</h2><ul>
<li><a href="https://github.com/adobe/trustmark">Adobe TrustMark</a> · <a href="https://opensource.contentauthenticity.org/docs/durable-cr/tm-faq/">official FAQ and limitations</a> · tested PyPI version 0.9.2, Q encoder and decoder model hashes recorded separately.</li>
<li><a href="https://github.com/facebookresearch/videoseal/tree/870ca7fb33578b90f14c602016b6c2788096226e">Meta PixelSeal pinned source</a> · checkpoint URL in its model card. The standard installer required unsupported decord; image inference works with selected dependencies and no decord.</li>
<li><a href="https://github.com/ShieldMnt/invisible-watermark">Classical baseline</a> · tested invisible-watermark 0.2.0.</li>
<li><a href="https://scikit-image.org/docs/stable/api/skimage.data.html">scikit-image sample-image provenance</a> · bundled samples used locally; upstream licensing/provenance applies.</li>
<li><a href="https://faq.whatsapp.com/759301289012856">WhatsApp standard/HD modes</a> · <a href="https://support.discord.com/hc/en-us/articles/25444343291031-File-Attachments-FAQ">Discord attachment documentation</a>.</li>
<li><a href="https://fastapi.tiangolo.com/">FastAPI local application framework</a> · suggested for the app; not part of the benchmark.</li>
<li><a href="results/full/summary.json">Aggregate results</a> · <a href="results/full/environment.json">Environment</a> · <a href="model-manifest.json">Model digests</a> · <a href="benchmark.py">Reproducible harness</a> · <a href="requirements-tested.txt">Tested packages</a>.</li>
</ul></main></html>'''
    (ROOT / "recommendation.html").write_text(document)


if __name__ == "__main__":
    main()
