# Third-party components

FaintMark's code is MIT licensed. Dependencies retain their own licenses.

- [Adobe TrustMark](https://github.com/adobe/trustmark), version 0.9.2: MIT,
  including its official model files. FaintMark uses Q at strength 1.0 with
  BCH_SUPER (40-bit payload, schema 0). The engine adapter retains the upstream
  inference architecture; it redirects model storage and verifies SHA-256
  digests before safe tensor loading. Attribution is retained in the dependency.
- [PyTorch](https://github.com/pytorch/pytorch) and torchvision: BSD-style licenses.
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk): MIT.
- [FastAPI](https://github.com/fastapi/fastapi): MIT.
- [Pillow](https://github.com/python-pillow/Pillow): HPND.

Official model download source:
`https://cai-watermark.adobe.net/watermarking/trustmark-models/`

| File | SHA-256 |
| --- | --- |
| trustmark_Q.yaml | 43f37103f92efa8bd6b1c5902bb537cc12a981dc699fca19d9bb7de8c62d03d9 |
| decoder_Q.ckpt | e3d9cea5406a26590735719f8f15cb10802b11852ae69047eaf4cf17214df781 |
| encoder_Q.ckpt | dc382c3f6b4fd568b27d6fbb763d6ffc2d2587126d84afe9d5ee95b4c5d99826 |

Model checkpoints are not committed. A hash mismatch is an error; model updates
require an explicit version/hash change and new recovery tests.

The research folder contains an earlier PixelSeal and classical-method
comparison. Its model files and sample photographs remain local and ignored.
Photographic sample provenance and rights follow [scikit-image's data
documentation](https://scikit-image.org/docs/stable/api/skimage.data.html).
The small research attenuation config is from Meta's MIT-licensed VideoSeal
repository; its source commit is recorded in the file.
