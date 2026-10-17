"""真实环境端到端：用 EdgeDock 真正的 launch_item 起一次 Trae，看进程有没有活。

不做任何 mock。这是这次修复的最终验收 —— 前面已经证明 explorer 通道可行，
现在确认 launch_item 真的走了那条通道并且程序确实起来了。
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, ".")
from edgedock import app as app_mod  # noqa: E402
from edgedock import config as cfg_mod  # noqa: E402


def find_trae() -> list[str]:
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*Trae*' } | "
          "ForEach-Object { \"$($_.ProcessId)|$($_.Name)\" }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=20)
        return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    except Exception as exc:
        return ["<失败 %s>" % exc]


def main() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "Trae CN.exe"], capture_output=True)
    time.sleep(2)

    cfg = cfg_mod.Config()
    it = cfg.items[0]
    print("条目:", it)
    print("起之前:", find_trae() or "无")

    t0 = time.time()
    ok = app_mod.launch_item(it)
    print("launch_item -> %s   （%.2fs）" % (ok, time.time() - t0))

    for w in (4, 6):
        time.sleep(w)
        now = find_trae()
        print("再等 %ds: %s" % (w, "%d 个进程 ✅" % len(now) if now else "❌ 无"))
        if now:
            print("  例:", ", ".join(now[:4]))
            break

    # ---- 第二关：桌面上的快捷方式「不在」了，还要能打开 ----
    # 不去动你桌面上的真文件，而是把条目里的 path 换成一个不存在的路径 ——
    # 对启动逻辑来说这和「桌面快捷方式被删掉」完全是同一件事。
    print("\n" + "=" * 58)
    print("【桌面快捷方式不在时】")
    subprocess.run(["taskkill", "/F", "/IM", "Trae CN.exe"], capture_output=True)
    time.sleep(2)

    ghost = dict(it)
    ghost["path"] = os.path.join(os.path.dirname(it["path"]), "这个快捷方式已经被删了.lnk")
    print("条目 path:", ghost["path"], "（不存在 =", not os.path.exists(ghost["path"]), "）")
    print("条目 target:", ghost["target"], "（存在 =", os.path.exists(ghost["target"]), "）")
    print("起之前:", find_trae() or "无")

    ok2 = app_mod.launch_item(ghost)
    print("launch_item -> %s" % ok2)
    for w in (4, 6):
        time.sleep(w)
        now = find_trae()
        print("再等 %ds: %s" % (w, "%d 个进程 ✅" % len(now) if now else "❌ 无"))
        if now:
            print("  例:", ", ".join(now[:4]))
            break


if __name__ == "__main__":
    main()
