# Engine selection

Local tests on 6 October 2026 used nine fixtures, five distinct copy IDs per
fixture and 13 transformations. Each success required the exact 40-bit ID.

| Pipeline | Routine recovery | Stress recovery | Median PSNR |
| --- | --- | --- | --- |
| TrustMark Q, BCH_SUPER | 435/450 (96.7%) | 75/135 | 43.31 dB |
| PixelSeal, default strength, BCH/checksum | 354/450 (78.7%) | 30/135 | 46.30 dB |
| PixelSeal, 1.4× strength, BCH/checksum | 390/450 (86.7%) | 46/135 | 43.54 dB |
| Classical DWT/DCT, raw ID | 25/450 (5.6%) | 0/135 | 40.27 dB |

There were zero wrong registered IDs across 2,340 marked-image cases and zero
registered matches across 468 unmarked controls. Those counts do not establish
a zero false-positive rate. The classical baseline lacked added error
correction and does not represent every classical watermark design.

TrustMark recovered all 45 IDs at each tested JPEG quality from 95 to 50.
Repeated shrinking/recompression caused most routine failures. Its median
warm-model embedding/extraction times on an Apple M2 Max were 22/11 ms. The
1.4× PixelSeal arm brought its image distortion close to TrustMark's, and
TrustMark still had higher recovery in this sample.

Routine transformations: unchanged PNG; JPEG 95/85/70/50; WebP 80/50; half-size
JPEG 70; longest side capped at 1080 then JPEG 80; three successive 0.75 resizes
with JPEG 80/70/60. Stress: JPEG 30, quarter-size JPEG 50, and longest side 160
with JPEG 50. These encoder settings simulate transformations; they are not
platform-specific codecs or settings.

The sample contained six bundled photographic examples, two generated
smooth/text images, and one upscaled derivative. It was small and correlated;
most examples were below 1080 pixels, so capping at 1080 did not resize them.
PSNR is a distortion metric, not proof that changes are invisible.

**No Discord, Instagram or WhatsApp round trips were performed.** Their actual
compatibility remains subject to [manual QA](QA.md). Recipient identification
does not prove personal culpability, legal ownership, or resistance to deliberate
watermark removal.

Reproduction code and dependencies are in [research/README.md](../research/README.md).
Raw outputs, sample images and the generated HTML report remain local and
ignored by Git. They can be regenerated from the harness. The default app uses
only TrustMark and does not install PixelSeal or the research runtime.

Sources: [TrustMark](https://github.com/adobe/trustmark),
[official FAQ](https://opensource.contentauthenticity.org/docs/durable-cr/tm-faq/),
[PixelSeal](https://github.com/facebookresearch/videoseal),
[classical library](https://github.com/ShieldMnt/invisible-watermark).
