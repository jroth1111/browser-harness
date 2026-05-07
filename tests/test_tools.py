import importlib.util
from pathlib import Path


def test_render_airbnb_fixtures_imports_packaged_data_display():
    spec = importlib.util.spec_from_file_location(
        "render_airbnb_fixtures",
        Path("tools/render_airbnb_fixtures.py"),
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None

    spec.loader.exec_module(module)

    assert module.render_dataset.__module__ == "browser_harness.data_display"
