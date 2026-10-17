# -*- coding: utf-8 -*-
"""把抽屉里残留的「桌面快捷方式」条目升级成「系统应用」条目。

早期版本是从桌面扫快捷方式的，所以 config.json 里存的是 ``.lnk`` 路径。
现在抽屉是**应用启动器**，条目应该指向系统登记的应用标识 —— 桌面上那个
快捷方式在不在、叫什么、删没删，都跟抽屉无关。

迁移只做**高置信度**的匹配，宁可不改也不改错：

  * 路径本身就等于某个应用的 exe 路径
  * 记下来的真实目标等于某个应用的 exe 路径
  * 名字完全一致（去掉扩展名后，忽略大小写）

对不上的条目原样保留 —— 它们照样能用，只是还依赖那个文件。

用法::

    python tools/upgrade_to_apps.py          # 只看会改什么，不落盘
    python tools/upgrade_to_apps.py --apply  # 真的改（先备份 config.json）
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from edgedock import apps, config as config_mod, winapi


def _norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(p)).strip() if p else ""


def _stem(p: str) -> str:
    return os.path.splitext(os.path.basename(p))[0].strip().lower()


def build_index() -> tuple[dict, dict]:
    """返回 (按 exe 路径索引, 按名字索引)，只收能寻址到系统应用的项。"""
    pool = apps.scan_apps()
    by_path: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    for a in pool:
        # 路径型的按 exe 路径索引；标识型的也塞一份，防止条目里存的就是标识
        if a.get("path"):
            by_path[_norm(a["path"])] = a
        if a.get("appid"):
            by_path[_norm(a["appid"])] = a
        by_name.setdefault(a["name"].strip().lower(), a)
        if a.get("path"):
            by_name.setdefault(_stem(a["path"]), a)
    return by_path, by_name


def match(it: dict, by_path: dict, by_name: dict) -> tuple[dict | None, str]:
    """给条目找对应的系统应用，返回 (应用, 依据)。"""
    if (it.get("appid") or "").strip():
        return None, "已经是应用条目"

    for field in ("target", "path"):
        p = _norm(it.get(field) or "")
        if p and p in by_path:
            return by_path[p], field

    name = (it.get("name") or "").strip().lower()
    if name and name in by_name:
        return by_name[name], "名字"

    # 「IntelliJ IDEA 2026.2.1」对「IntelliJ IDEA」这种带版本号的写法
    if name:
        for cand_name, app in by_name.items():
            if len(cand_name) >= 4 and name.startswith(cand_name):
                return app, "名字前缀"
    return None, ""


def convert(it: dict, app: dict) -> dict:
    """按系统应用重写条目，用户已有的附加信息尽量保住。"""
    new = dict(it)
    new["path"] = app.get("path") or ""
    new["appid"] = app.get("appid") or ""
    # 名字换成系统里那个（不带版本号，更干净）
    new["name"] = app.get("name") or it.get("name") or ""
    # target / workdir 故意留着：它们只是「记下的信息」，不构成依赖，
    # 但右键的「打开文件所在位置」要靠它 —— 应用条目本身没有磁盘路径。
    return new


def verified(app: dict) -> str:
    """确认改完之后真的能寻址。返回可用的寻址串，不行就返回空串。

    shell 命名空间路径不对应任何文件，``os.path.exists`` 判断不了，只能拿去
    问 shell 一次。宁可留着原来能用的条目，也不换成一条指向空气的标识。
    """
    appid = (app.get("appid") or "").strip()
    if appid:
        return appid if winapi.resolve_app(winapi.app_spec(appid)) else ""
    path = (app.get("path") or "").strip()
    return path if path and os.path.exists(path) else ""


def main() -> None:
    apply = "--apply" in sys.argv
    cfg = config_mod.Config()
    by_path, by_name = build_index()
    print("系统应用: %d 个" % len(apps.scan_apps()))
    print("抽屉条目: %d 个" % len(cfg.items))
    print("模式    : %s\n" % ("写入" if apply else "只看不改（加 --apply 才落盘）"))

    changed = 0
    out = []
    for it in cfg.items:
        app, why = match(it, by_path, by_name)
        if app:
            where = verified(app)
            if not where:
                print("  ! %-28s 匹配到了但系统认不出，保持原样" % it.get("name", "?"))
                out.append(it)
                continue
            changed += 1
            new = convert(it, app)
            print("  ✓ %-28s <- %-12s %s" % (new["name"], why, where))
            out.append(new)
        else:
            print("  · %-28s 保持原样（%s）" % (it.get("name", "?"), why or "未匹配"))
            out.append(it)

    print("\n可升级: %d / %d" % (changed, len(cfg.items)))
    if not apply:
        print("（未写入任何文件）")
        return
    if not changed:
        print("没有需要改的，config.json 未动。")
        return

    bak = cfg.path + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(cfg.path, bak)
    print("已备份:", bak)

    raw = {}
    with open(cfg.path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    raw["items"] = out
    with open(cfg.path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2)
    print("已写入:", cfg.path)

    back = config_mod.Config()
    ok = sum(1 for it in back.items if (it.get("appid") or "").strip())
    print("回读校验: %d 个条目走应用标识，%d 个仍走文件路径"
          % (ok, len(back.items) - ok))


if __name__ == "__main__":
    main()
