from pathlib import Path

import pytest

from sycophancy.paths import resolve_recorded_path


@pytest.mark.parametrize("origin,target,relative", [
    ("C:/old/project/data/runs/main", "C:/old/project/data/runs/main/luna", "data/runs/main/luna"),
    (r"C:\old\project\data\runs\main", r"C:\old\project\data\verification\aliases.json", "data/verification/aliases.json"),
    ("/old/project/data/runs/main", "/old/project/data/runs/budget.json", "data/runs/budget.json"),
    ("c:/OLD/project/data/runs/main", "C:/old/project/data/runs/baseline", "data/runs/baseline"),
    ("/old/project/data/runs/main", "../budget.json", "data/runs/budget.json"),
])
def test_recorded_paths_relocate_across_operating_systems(tmp_path, origin, target, relative):
    assert resolve_recorded_path(target, origin, tmp_path / "data/runs/main") == tmp_path / relative


@pytest.mark.parametrize("origin,target", [
    (None, "/old/project/file.json"),
    ("C:/old/project/main", "D:/external/budget.json"),
    ("/old/main", "/unrelated/budget.json"),
    ("C:/old/project/main", "C:budget.json"),
])
def test_unmappable_paths_fail_without_searching_another_copy(tmp_path, origin, target):
    with pytest.raises(ValueError, match="[Rr]ecorded|recorded"):
        resolve_recorded_path(target, origin, tmp_path / "main")
