"""CLI 服务管理：进程匹配规则 + 项目根目录解析。

不起进程（真正拉服务/kill 的验证在 e2e 里做），这里只锁住最容易回归的匹配规则。
"""

import os

from offerhelper_cli import cli


def test_matches_new_module_launch():
    assert cli._is_boss_cmdline(["python", "-m", "boss.app", "--port", "8010"])
    assert cli._is_boss_cmdline(["C:/Python314/python.exe", "-m", "boss.app"])


def test_matches_package_path_both_separators():
    assert cli._is_boss_cmdline(["python", "D:/xjh/offer-helper/boss/app.py"])
    assert cli._is_boss_cmdline(["python", "D:\\xjh\\offer-helper\\boss\\app.py"])


def test_matches_legacy_flat_path():
    assert cli._is_boss_cmdline(["python", "D:/offer-helper/boss_app.py"])


def test_ignores_unrelated_python():
    assert not cli._is_boss_cmdline(["python", "-c", "print(1)"])
    assert not cli._is_boss_cmdline(["pytest", "tests/"])
    assert not cli._is_boss_cmdline(["python", "D:/other/app.py"])
    assert not cli._is_boss_cmdline([])


def test_project_dir_points_at_repo_root():
    root = cli._project_dir()
    assert os.path.exists(os.path.join(root, "boss", "app.py"))
    assert os.path.isdir(os.path.join(root, "offerhelper_cli"))
