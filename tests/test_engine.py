import pytest
from PIL import Image

from copymark.engine import TrustMarkEngine


class Decoder:
    result = ("0" * 40, True, 0)

    def decode(self, image, **kwargs):
        return self.result


@pytest.mark.parametrize(
    "result,expected",
    [
        (("0" * 39 + "1", True, 0), 1),
        (("0" * 40, False, 0), None),
        (("0" * 40, True, 1), None),
        (("0" * 39, True, 0), None),
        (("x" * 40, True, 0), None),
    ],
)
def test_decode_requires_corrected_exact_schema(tmp_path, result, expected):
    engine = TrustMarkEngine(tmp_path)
    decoder = Decoder()
    decoder.result = result
    engine._model = lambda: decoder
    assert engine.decode(Image.new("RGB", (32, 32))) == expected


def test_invalid_identifier_fails_before_loading(tmp_path):
    engine = TrustMarkEngine(tmp_path)
    engine._model = lambda: pytest.fail("Should remain lazy")
    with pytest.raises(ValueError):
        engine.encode(Image.new("RGB", (32, 32)), 2**40)
