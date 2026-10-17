# -*- coding: utf-8 -*-
"""真实环境端到端：用 EdgeDock 真正的 launch_item 起一个应用，看进程有没有活。

不做任何 mock —— 前面已经用 `check_launch.py` 核对过「走哪条通道、带了什么参数」，
这里确认最后一步：**程序确实起来了**。

重点验两件事，正好对应「应用启动器」的两条底线：

  1. 带**应用标识**的条目（商店应用、应用列表里的传统程序）能起得来
  2. 把条目里所有跟桌面/文件有关的东西抹掉之后，**照样起得来**
     —— 抽屉不依赖桌面上有没有那个快捷方式

用法::

    .venv\\Scripts\\python.exe tools\\verify_real_launch.py 名称 进程名 [--force]

    名称     抽屉条目名字的一部分，例如 Cursor / 计算器 / Trae
    进程名   起来之后要数的 exe 名字，不用带 .exe，例如 Cursor / CalculatorApp

会先 `taskkill` 掉目标进程 —— 所以如果它**已经在运行**，脚本会直接拒绝，
免得把没保存的活儿关掉。确认无所谓就加 `--force`。
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from edgedock import app as app_mod      # noqa: E402
from edgedock import config as cfg_mod   # noqa: E402


def count(proc: str) -> int:
    """数一下这个 exe 有几个进程（按 ImageName 精确匹配，不用 *通配*）。"""
    ps = ("(Get-Process -Name '%s' -ErrorAction SilentlyContinue | Measure-Object)"
          ".Count" % proc)
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=20)
        return int((out.stdout or "0").strip() or 0)
    except Exception:
        return -1


def kill(proc: str) -> None:
    subprocess.run(["taskkill", "/F", "/IM", proc + ".exe"], capture_output=True)
    time.sleep(2)


def wait_up(proc: str, label: str) -> bool:
    """等进程起来，最多约 10 秒。"""
    for w in (4, 6):
        time.sleep(w)
        n = count(proc)
        if n > 0:
            print("  %s：%d 个进程 ✅" % (label, n))
            return True
        print("  %s：❌ 还没有" % label)
    return False


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        print("当前抽屉里的条目：")
        for it in cfg_mod.Config().items:
            print("  %-28s %s" % (it.get("name", "?"),
                                  ("appid " + it["appid"]) if it.get("appid")
                                  else ("file  " + it["path"])))
        return

    want, proc = sys.argv[1], sys.argv[2]
    force = "--force" in sys.argv

    cfg = cfg_mod.Config()
    hit = [it for it in cfg.items if want.lower() in (it.get("name") or "").lower()]
    if not hit:
        print("抽屉里没有名字含「%s」的条目。" % want)
        return
    it = hit[0]
    print("条目:", it.get("name"))
    print("  寻址:", ("appid " + it["appid"]) if it.get("appid")
          else ("file  " + it["path"]))
    print("  目标:", it.get("target") or "(无)")

    running = count(proc)
    if running > 0 and not force:
        print("\n%s 已经在跑 %d 个进程。先退出它，或者加 --force 让我直接结束。"
              % (proc, running))
        return

    # ---- 第一关：按条目原样启动 ----
    print("\n" + "=" * 58)
    print("【第一关】按条目原样启动")
    kill(proc)
    print("  起之前：%d 个进程" % max(0, count(proc)))
    t0 = time.time()
    ok = app_mod.launch_item(it)
    print("  launch_item -> %s （%.2fs）" % (ok, time.time() - t0))
    first = wait_up(proc, "起来了吗")
    second = True                     # 第二关不适用时，算它过

    # ---- 第二关：抹掉一切和桌面/文件有关的线索 ----
    # 对「应用启动器」来说这才是常态考验：应用标识才是唯一依据，
    # 桌面上的快捷方式在不在、旁边那个 exe 动没动过，都不该有影响。
    print("\n" + "=" * 58)
    print("【第二关】把 path / target 全部抹掉再启动")
    ghost = dict(it)
    ghost["path"] = ""
    ghost["target"] = ""
    ghost["workdir"] = ""
    print("  条目里还剩：", "appid " + ghost["appid"] if ghost.get("appid")
          else "什么都没有")
    if not ghost.get("appid"):
        print("  这条不是应用标识条目，没有可抹的东西 —— 跳过。")
    else:
        kill(proc)
        print("  起之前：%d 个进程" % max(0, count(proc)))
        ok2 = app_mod.launch_item(ghost)
        print("  launch_item -> %s" % ok2)
        second = wait_up(proc, "起来了吗")

    print("\n" + "=" * 58)
    if first and second:
        print("结论：两关都通过 —— 应用标识能独立把程序拉起来，跟桌面无关。")
    else:
        print("结论：有环节没通过，见上面的 ❌。")


if __name__ == "__main__":
    main()
