# Watermarker research

Free, local A/B testing for invisible recipient-specific image watermarking.
No app interface has been built yet. The recommendation and measured results
are in `recommendation.html`; raw evidence is in `results/full/`.

## Tested scope

TrustMark Q with BCH_SUPER, PixelSeal at default and 1.4× strength with a
BCH/CRC wrapper, and an off-the-shelf DWT/DCT diagnostic baseline.
Nine fixtures, five distinct IDs per fixture, and 13 local transformations.
No platform uploads, private images, paid tools or paid APIs.

## Reproduce

The tested environment is isolated in `.venv`. All downloads are free. Initial
model downloads need network access; subsequent runs use local cached models.
The application environment lives at the repository root. For a separate
research environment, run these commands from this `research` directory.

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-tested.txt
```

`requirements-tested.txt` deliberately includes selected image-only PixelSeal
dependencies. Its pinned source must be installed **separately with `--no-deps`**
because its complete dependency metadata requires `decord`, which has no
matching Mac wheel:

```sh
uv pip install --python .venv/bin/python --no-deps \
  'videoseal @ git+https://github.com/facebookresearch/videoseal.git@870ca7fb33578b90f14c602016b6c2788096226e'
```

Then run the comparison and generate the report:

```sh
MPLCONFIGDIR=/private/tmp/watermarker-mpl \
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 \
.venv/bin/python -u benchmark.py --engines trustmark_q pixelseal pixelseal_1p4 classic_dwt_dct
.venv/bin/python report.py
```

The upstream `configs/attenuation.yaml` is included because the installed
PixelSeal wheel omitted that file. No neural-model computation was changed;
the 1.4× arm changes the documented additive watermark blending coefficient.
Use `--cpu` for an explicitly CPU-only run. Tested performance numbers use MPS.

TrustMark's loader uses trusted official pickle model checkpoints and needs
`TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` with this Torch version. Do not apply that
setting to arbitrary third-party checkpoints. The downloaded official Q model
MD5 values match the constants in TrustMark, and SHA-256 digests are recorded
in `model-manifest.json`. A shipping app should bundle vetted model artifacts
and pin its runtime, rather than automatically fetching arbitrary updates.

`benchmark.py` saves results after every fixture. Stop/restart reruns the
requested arm, replacing its previous JSON. Fixtures and model downloads are
ignored by Git; keep them locally for reproduction. The model-manifest paths
refer to this experiment's environment. The photographic fixtures retain
their upstream scikit-image provenance; the 2048 astronaut is an explicitly
upscaled derivative. Findings do not extrapolate to every image or platform.
