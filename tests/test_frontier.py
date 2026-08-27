import dataclasses

from crawler.config import DEFAULT_LIMITS
from crawler.frontier import Frontier

HOST = "http://54.214.7.161"


def test_deduplicates_canonical_urls():
    f = Frontier(DEFAULT_LIMITS)
    assert f.add(f"{HOST}/docs/", 1) is True
    assert f.add(f"{HOST}/docs/", 1) is False
    assert len(f) == 1


def test_respects_max_depth():
    limits = dataclasses.replace(DEFAULT_LIMITS, max_depth=2)
    f = Frontier(limits)
    assert f.add(f"{HOST}/a/", 2) is True
    assert f.add(f"{HOST}/b/", 3) is False
    assert f.rejected["depth"] == 1


def test_caps_distinct_values_for_a_single_param():
    limits = dataclasses.replace(DEFAULT_LIMITS, max_values_per_param=5)
    f = Frontier(limits)
    added = [f.add(f"{HOST}/report/?page={n}", 1) for n in range(1, 11)]
    assert added.count(True) == 5
    assert added.count(False) == 5
    assert f.rejected["param_budget"] == 5


def test_param_cap_is_per_path_not_global():
    limits = dataclasses.replace(DEFAULT_LIMITS, max_values_per_param=2)
    f = Frontier(limits)
    assert f.add(f"{HOST}/report/?page=1", 1) is True
    assert f.add(f"{HOST}/report/?page=2", 1) is True
    assert f.add(f"{HOST}/report/?page=3", 1) is False
    # different path, fresh budget
    assert f.add(f"{HOST}/archive/?page=9", 1) is True


def test_rejects_trap_shapes():
    f = Frontier(DEFAULT_LIMITS)
    looping = f"{HOST}/a/b/a/b/a/b/a/b/"
    assert f.add(looping, 1) is False
    assert f.rejected["trap_shape"] == 1


def test_pop_is_fifo():
    f = Frontier(DEFAULT_LIMITS)
    f.add(f"{HOST}/first/", 1)
    f.add(f"{HOST}/second/", 1)
    assert f.pop()[0] == f"{HOST}/first/"
    assert f.pop()[0] == f"{HOST}/second/"
