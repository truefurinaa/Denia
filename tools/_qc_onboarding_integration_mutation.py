# -*- coding: utf-8 -*-
"""引导页集成门的变异刀：证明 `tools/test_onboarding_integration.py` 的判据真的有牙。

背景（2026-11-14）：这道门 2026-10-21 收进 GATES 时就标着「本轮已补判据，刀待补」，
至今是全仓 44 道「有门无刀」之一。没有刀，判据被改松、锚点被搬家、甚至整段断言被删，
它都仍然打印 108 PASS —— 和「真的验过」长得一模一样。

做法：每把刀只改**产品代码**里的一个真实行为点，跑一次门，要求
  ①退出码非 0，且 ②输出里点名了**该行为对应的那条判据**。
两件事缺一不可：只要求「红一个」会被任意别的崩溃满足（本仓 #18 已实证：
把判定整个换成 raise，18 把刀照样全红）。跑完立刻按字节还原并核对 sha256。

刀具（打在真代码上，不在测试里）：
  M1 [B10]/[B20] webapp.save_character 的非达妮娅 model_3d 兜底 → 改成 True
  M2 [A4]        first_launch_setup.html 的 MODE_SEQ 少一个 screenRole
  M3 [B18]       webapp.save_first_run_config 的「混合推荐」→ 改成 skip
  M4 [B4]        cloud_tts.merge_cloud_tts_provider 的空值不改 → 改成无条件覆盖
  M5 对照        html 里只加一行注释（行为不变）→ 必须**仍然绿**

用法：
    python tools/_qc_onboarding_integration_mutation.py            # 跑全部
    python tools/_qc_onboarding_integration_mutation.py M2         # 只跑指定刀

退出码：0 = 全部符合预期；1 = 有刀不符合（含锚点命中 0 次）。
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

GATE = "tools/test_onboarding_integration.py"
TIMEOUT = 300


def _sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _run_gate() -> tuple[int, str]:
    p = subprocess.run([sys.executable, GATE], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# (编号, 说明, 相对路径, 原文片段, 替换片段, 期望被点名的判据)
KNIVES = [
    ("M1", "非达妮娅 model_3d 兜底被抹平",
     "src/ui/webapp.py",
     '_merged_m3d["enabled"] = False',
     '_merged_m3d["enabled"] = True',
     "[B10] 后端兜底：非达妮娅传 enabled:true 也存成 false"),

    ("M2", "本机免费链路少了「建角色」屏",
     "src/ui/web/first_launch_setup.html",
     "'本机免费': ['screenVisionDl','screenVoice','screenMic','screenRole','screenSummary'],",
     "'本机免费': ['screenVisionDl','screenVoice','screenMic','screenSummary'],",
     "[A4] 每条链路都含「建角色 + 体检」"),

    # 档位映射表在 save_first_run_config 与 validate_onboarding 里各有一份（两处必须同口径），
    # 所以这里期望命中 2 次：一起改，才是「档位名不再被识别」这个真实事故的形状。
    ("M3", "「混合推荐」档位名不再映射",
     "src/ui/webapp.py",
     '"混合推荐": "mixed"',
     '"混合推荐": "skip"',
     "[B18] companion_mode 映射为 mixed", 2),

    ("M4", "空 api_key 覆盖了已存 Key",
     "src/models/cloud_tts.py",
     '"api_key": api_key or _prev.get("api_key") or "",',
     '"api_key": api_key,',
     "[B4] 空 api_key 不擦除已存 Key（契约成立）"),
]

CONTROL = ("M5", "对照：只加注释，行为不变",
           "src/ui/web/first_launch_setup.html",
           "const STEP_LABELS = {",
           "// onboarding-knife 对照行（无行为改动）\n  const STEP_LABELS = {")


def apply_and_check(number: str, why: str, rel: str, anchor: str, repl: str,
                    label: str, hits: int = 1) -> bool:
    path = os.path.join(ROOT, *rel.split("/"))
    if not os.path.isfile(path):
        print("  ✗ %s 文件不存在：%s" % (number, rel))
        return False
    raw = open(path, "rb").read()
    a = anchor.encode("utf-8")
    n = raw.count(a)
    if n != hits:
        # 锚点搬家 = 这把刀以后什么都没验，必须当场报红，不能当成通过
        print("  ✗ %s 锚点命中 %d 次（要求 %d 次）：%s" % (number, n, hits, rel))
        return False

    before = _sha(path)
    mutated = raw.replace(a, repl.encode("utf-8"))
    open(path, "wb").write(mutated)
    t0 = time.time()
    try:
        rc, out = _run_gate()
    finally:
        open(path, "wb").write(raw)
    cost = time.time() - t0

    after = _sha(path)
    if after != before:
        print("  ✗ %s 还原失败（sha256 不一致）%s" % (number, rel))
        return False

    named = label in out
    ok = (rc != 0) and named
    print("  %s %s %s  rc=%d 点名=%s  %.1fs"
          % ("✓" if ok else "✗", number, why, rc, "是" if named else "否", cost))
    if not ok:
        tail = [ln for ln in out.splitlines() if "FAIL" in ln][:3]
        print("      期望点名：%s" % label)
        print("      实际 FAIL 行：%s" % (tail or "<无>"))
    return ok


def run_control(number: str, why: str, rel: str, anchor: str, repl: str) -> bool:
    """对照组：行为不变的改动，门必须仍然绿（否则这把刀证明的是「门怕任何改动」）。"""
    path = os.path.join(ROOT, *rel.split("/"))
    raw = open(path, "rb").read()
    a = anchor.encode("utf-8")
    if raw.count(a) != 1:
        print("  ✗ %s 锚点命中 %d 次" % (number, raw.count(a)))
        return False
    before = _sha(path)
    try:
        open(path, "wb").write(raw.replace(a, repl.encode("utf-8"), 1))
        rc, out = _run_gate()
    finally:
        open(path, "wb").write(raw)
    ok = (rc == 0) and (_sha(path) == before) and ("108 PASS" in out or "PASS = 108" in out)
    print("  %s %s %s  rc=%d  还原=%s" % ("✓" if ok else "✗", number, why,
                                         rc, "一致" if _sha(path) == before else "不一致"))
    return ok


def main(argv: list[str]) -> int:
    only = argv[0] if argv else ""
    print("== 基线：原样跑一次门（刀生效的前提是起点绿）==")
    t0 = time.time()
    rc, out = _run_gate()
    print("   rc=%d  %.1fs  %s" % (rc, time.time() - t0,
                                  "起点绿" if rc == 0 else "起点就是红的——后面所有刀的读数都不成立"))
    if rc != 0:
        print("MUTATION_RESULT: BASELINE_RED")
        return 1

    results = []
    for item in KNIVES:
        if only and item[0] != only:
            continue
        results.append(apply_and_check(*item))
    if not only or only == CONTROL[0]:
        results.append(run_control(*CONTROL))

    print()
    if results and all(results):
        print("MUTATION_RESULT: ALL PASS（%d 把）" % len(results))
        return 0
    print("MUTATION_RESULT: FAIL（%d/%d 把不符合预期）"
          % (results.count(False), len(results)))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
