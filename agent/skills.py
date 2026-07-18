"""Skill 系統：markdown 知識包，模型判斷相關時自行載入。

Skill 是「操作手冊」而非可執行工具——一份 SKILL.md 教模型
怎麼做某類任務（報告格式、SOP、公司術語等）。

目錄結構（兩處都會掃描，同名時使用者目錄優先）：
    <repo>/skills/<name>/SKILL.md          # 隨專案發佈
    ~/.my-agent/skills/<name>/SKILL.md     # 使用者自訂

SKILL.md 格式：
    ---
    name: weekly-report
    description: 一句話說明何時該用這個 skill
    ---
    （給模型的完整指示，markdown 自由發揮）
"""
import logging
import re
from pathlib import Path

log = logging.getLogger("my-agent")

REPO_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
USER_SKILLS_DIR = Path.home() / ".my-agent" / "skills"


# ── 解析 ─────────────────────────────────────────

_FRONTMATTER = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL
)


def _parse(text: str) -> tuple[dict, str]:
    """回傳 (frontmatter dict, 本文)。沒有 frontmatter 時 meta 為空。"""
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text

    meta: dict = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()

    return meta, text[match.end():]


# ── 掃描與載入 ────────────────────────────────────

def list_skills() -> list[dict]:
    """列出所有 skill 的 {name, description, path}，使用者目錄優先。"""
    found: dict[str, dict] = {}

    for base in (REPO_SKILLS_DIR, USER_SKILLS_DIR):
        if not base.is_dir():
            continue
        for skill_md in sorted(base.glob("*/SKILL.md")):
            try:
                meta, _ = _parse(skill_md.read_text(encoding="utf-8"))
            except Exception:
                log.warning("skill 解析失敗：%s", skill_md)
                continue

            name = meta.get("name") or skill_md.parent.name
            found[name] = {
                "name":        name,
                "description": meta.get("description", ""),
                "path":        skill_md,
            }

    return list(found.values())


def load_skill(name: str) -> str | None:
    """回傳指定 skill 的本文；找不到時回傳 None。"""
    for skill in list_skills():
        if skill["name"] == name:
            try:
                _, body = _parse(
                    skill["path"].read_text(encoding="utf-8")
                )
                return body.strip()
            except Exception as e:
                log.error("skill 讀取失敗 %s: %s", name, e)
                return None
    return None


# ── 系統提示注入 ──────────────────────────────────

def skills_index_prompt() -> str:
    """產生附加到 system prompt 的 skill 目錄；沒有 skill 時回傳空字串。"""
    skills = list_skills()
    if not skills:
        return ""

    lines = [
        "\n\n## 可用的 Skills",
        "以下 skill 是特定任務的操作手冊。當使用者的請求與某個",
        "skill 的描述相關時，先呼叫 use_skill 工具載入完整指示，",
        "再依照指示執行：",
    ]
    for s in skills:
        lines.append(f"- {s['name']}：{s['description']}")

    return "\n".join(lines)


# ── use_skill 工具 ────────────────────────────────

SKILL_TOOL = {
    "type": "function",
    "name": "use_skill",
    "description": (
        "載入指定 skill 的完整指示（操作手冊）。"
        "當使用者的請求符合某個 skill 的描述時呼叫，"
        "然後依照回傳的指示完成任務。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "skill 名稱（見系統提示中的清單）",
            },
        },
        "required": ["name"],
    },
}


def skill_tools() -> list[dict]:
    """有 skill 才註冊工具，避免無謂佔用 context。"""
    return [SKILL_TOOL] if list_skills() else []


def is_skill_tool(name: str) -> bool:
    return name == "use_skill"


def call_skill_tool(args: dict) -> str:
    name = str(args.get("name", "")).strip()
    body = load_skill(name)

    if body is None:
        available = ", ".join(s["name"] for s in list_skills()) or "（無）"
        return f"[ERROR] 找不到 skill「{name}」。可用：{available}"

    return f"# Skill: {name}\n\n{body}"
