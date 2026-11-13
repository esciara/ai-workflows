"""Compare a target repo's caller workflow with templates/caller.yml, tolerating intended differences.

Checked: top-level `permissions`; `permissions` of every job present in both; `concurrency` (cancel-in-progress equal,
group equal once the caller's group prefix is normalised). Jobs absent from the caller are skipped on purpose.
"""

from __future__ import annotations

from aiwf import policy


def compare(template_text: str, caller_text: str, group_prefix: tuple[str, str] | None = None) -> list[str]:
    """Problems found (empty when consistent). `group_prefix` = (caller prefix, template prefix) to normalise."""
    tpl, cal = policy.load_workflow(template_text), policy.load_workflow(caller_text)
    problems: list[str] = []
    if cal.get("permissions") != tpl.get("permissions"):
        problems.append(f"top-level permissions differ: caller {cal.get('permissions')!r}, template {tpl.get('permissions')!r}")
    tjobs, cjobs = tpl.get("jobs") or {}, cal.get("jobs") or {}
    for name in sorted(set(tjobs) & set(cjobs)):
        tp, cp = tjobs[name].get("permissions"), cjobs[name].get("permissions")
        if cp != tp:
            problems.append(f"job {name!r} permissions differ: caller {cp!r}, template {tp!r}")
    tc, cc = tpl.get("concurrency") or {}, cal.get("concurrency") or {}
    if cc.get("cancel-in-progress") != tc.get("cancel-in-progress"):
        problems.append(f"concurrency cancel-in-progress differs: caller {cc.get('cancel-in-progress')!r}, "
                        f"template {tc.get('cancel-in-progress')!r}")
    group = str(cc.get("group", ""))
    if group_prefix:
        group = group.replace(group_prefix[0], group_prefix[1], 1)
    if group != str(tc.get("group", "")):
        problems.append(f"concurrency group differs:\n  caller   {group}\n  template {tc.get('group')}")
    return problems


def jobs_of(text: str) -> set[str]:
    return set((policy.load_workflow(text).get("jobs") or {}))
