import importlib.util
import zipfile
from pathlib import Path


def load_release_proof():
    path = Path("scripts/release_proof.py")
    spec = importlib.util.spec_from_file_location("release_proof", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_release_proof_requires_packaged_browser_harness_members(tmp_path):
    release_proof = load_release_proof()
    wheel = tmp_path / "browser_harness-0.1.0-py3-none-any.whl"
    members = [
        *release_proof.REQUIRED_MEMBERS,
        "browser_harness-0.1.0.dist-info/METADATA",
    ]
    with zipfile.ZipFile(wheel, "w") as zf:
        for member in members:
            zf.writestr(member, "")

    result = release_proof.inspect_wheel(wheel)

    assert result["required_members"] == list(release_proof.REQUIRED_MEMBERS)
    package_prefixes = ("browser_harness/", "browser_harness_assets/", "browser_harness_docs/")
    assert all(member.startswith(package_prefixes) for member in release_proof.REQUIRED_MEMBERS)
