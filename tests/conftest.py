import base64
import io
import sys
from pathlib import Path

import pytest
from PIL import Image

# Domain skill scripts use bare `import login_session` etc. because they run
# inside browser-harness exec sessions where the package internals are on the path.
# Add src/browser_harness/ so those bare imports resolve in tests too.
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "browser_harness"))


def make_png(width, height):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def fake_png():
    return make_png
