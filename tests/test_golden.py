"""Golden records: platform hashes + a tolerant signature (tests/golden.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from golden import record, sig_diff  # noqa: E402

SIG = {"tris": 700, "bounds": [[-0.24, 0.0, -0.042], [0.24, 1.396, 0.042]], "area": 0.6078, "volume": 0.0065097}


def test_float_noise_is_within_the_signature_and_a_modelling_change_is_not():
    noisy = {**SIG, "bounds": [[-0.24000004, 0.0, -0.042], [0.24, 1.39600002, 0.042]], "area": 0.60780007}
    assert sig_diff(noisy, SIG) == []
    moved = {**SIG, "bounds": [[-0.24, 0.0, -0.042], [0.24, 1.398, 0.042]]}  # a part raised by 2 mm
    assert sig_diff(moved, SIG) and "bounds" in sig_diff(moved, SIG)[0]
    assert sig_diff({**SIG, "tris": 760}, SIG)
    assert sig_diff({**SIG, "volume": 0.0066}, SIG)


def test_record_adds_a_platform_for_the_same_geometry_and_resets_on_a_change():
    entry = {"hash": {"linux-x86_64": "aaaa"}, "sig": SIG}
    same, what = record(entry, "bbbb", {**SIG, "area": 0.60780004}, "win32-amd64")
    assert what == "platform-added" and same["hash"] == {"linux-x86_64": "aaaa", "win32-amd64": "bbbb"}
    assert record(same, "bbbb", SIG, "win32-amd64")[1] == "unchanged"
    changed, what = record(same, "cccc", {**SIG, "tris": 800}, "win32-amd64")
    assert what == "changed" and changed["hash"] == {"win32-amd64": "cccc"} and changed["sig"]["tris"] == 800
    # a sub-tolerance change on a platform that has a hash is still a change (the hash is the fine check)
    assert record(same, "dddd", SIG, "linux-x86_64")[1] == "changed"
    assert record(None, "eeee", SIG, "darwin-arm64")[1] == "new"


def test_merge_takes_another_platforms_hash_only_where_the_signature_agrees():
    from golden import merge

    ours = {"a": {"hash": {"win32-amd64": "w"}, "sig": SIG}, "b": {"hash": {"win32-amd64": "w2"}, "sig": SIG}}
    theirs = {"a": {"hash": {"darwin-arm64": "m"}, "sig": SIG}, "b": {"hash": {"darwin-arm64": "m2"}, "sig": {**SIG, "tris": 900}}}
    assert merge(ours, theirs) == ["a"]
    assert ours["a"]["hash"] == {"win32-amd64": "w", "darwin-arm64": "m"} and ours["b"]["hash"] == {"win32-amd64": "w2"}
