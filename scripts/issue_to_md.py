#!/usr/bin/env python3
"""Превращает GitHub Issue (и комментарии к нему) в markdown-заметку в issues/.

Запускается из .github/workflows/issue-to-md.yml. Читает событие из GITHUB_EVENT_PATH.
Правила:
  * один Issue = один файл issues/P-0042 <название>.md;
  * всё ниже MARKER скрипт не трогает (причина, решение, скриншоты, правки LLM);
  * status, tags, related, cause и другие поля, которых нет в форме, при обновлении сохраняются.
"""
import json
import os
import re
import sys
from pathlib import Path

ISSUES = Path(os.environ.get("ISSUES_DIR", "issues"))
MARKER = "<!-- ДОПОЛНЕНИЯ: всё ниже этой строки скрипт не трогает -->"

# Заголовок поля в форме -> (ключ frontmatter или None, название раздела в заметке)
FIELDS = [
    ("Автор", "reporter"),
    ("Версия плагина", "plugin_version"),
    ("Операционная система", "os"),
    ("Серьёзность", "severity"),
]
BODY_SECTIONS = [
    "Что произошло",
    "Шаги воспроизведения",
    "Ожидаемый результат",
    "Лог / текст ошибки",
]

DEFAULT_TAIL = """
## Причина

## Решение

## Скриншоты и дополнения
Вставьте скриншоты сюда (Ctrl+V в Obsidian). Файлы сохраняются в `issues/attachments/`.
"""


def safe_title(title: str) -> str:
    t = re.sub(r'[\\/:*?"<>|#^\[\]]', "", title).strip()
    t = re.sub(r"\s+", " ", t)
    return t[:60] or "без названия"


def parse_sections(body: str) -> dict:
    """Разбирает тело Issue, созданного из формы (### Заголовок / значение)."""
    body = body or ""
    parts = re.split(r"^### (.+?)\s*$", body, flags=re.M)
    if len(parts) < 3:  # свободный текст, например от GPT без формы
        return {"Что произошло": body.strip()}
    sections = {}
    for i in range(1, len(parts), 2):
        value = parts[i + 1].strip()
        if value == "_No response_":
            value = ""
        sections[parts[i].strip()] = value
    return sections


def parse_frontmatter(text: str):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, text[m.end():]


def yaml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def parse_list(raw: str):
    raw = (raw or "").strip().strip("[]")
    return [x.strip().strip('"') for x in raw.split(",") if x.strip()]


def fmt_list(items):
    return "[" + ", ".join(yaml_str(x) for x in items) + "]"


def build(issue: dict, action: str, old_text: str | None) -> str:
    old_fm, old_body = parse_frontmatter(old_text) if old_text else ({}, "")
    tail = DEFAULT_TAIL
    if old_text and MARKER in old_body:
        tail = old_body.split(MARKER, 1)[1]

    sections = parse_sections(issue.get("body"))
    labels = [l["name"] for l in issue.get("labels", [])]
    source = next((l.split(":", 1)[1] for l in labels if l.startswith("source:")), None)
    tags = [l for l in labels if not l.startswith("source:")]

    if action == "closed":
        status = "closed"
    elif action in ("opened", "reopened"):
        status = "open"
    else:
        status = old_fm.get("status", "open").strip('"')

    num = issue["number"]
    fm = dict(old_fm)  # сохраняем чужие поля (related, cause, ...)
    fm.update({
        "id": yaml_str(f"P-{num:04d}"),
        "title": yaml_str(issue["title"]),
        "status": yaml_str(status),
        "severity": yaml_str(sections.get("Серьёзность", "") or old_fm.get("severity", "").strip('"')),
        "plugin_version": yaml_str(sections.get("Версия плагина", "")),
        "os": yaml_str(sections.get("Операционная система", "")),
        "reporter": yaml_str(sections.get("Автор") or "@" + issue["user"]["login"]),
        "source": yaml_str(source or old_fm.get("source", "").strip('"') or "form"),
        "tags": fmt_list(sorted(set(tags) | set(parse_list(old_fm.get("tags", ""))))),
        "created": issue["created_at"][:10],
        "updated": issue["updated_at"][:10],
        "issue_url": yaml_str(issue["html_url"]),
    })
    order = ["id", "title", "status", "severity", "plugin_version", "os", "reporter",
             "source", "tags", "created", "updated", "issue_url"]
    keys = order + [k for k in fm if k not in order]

    out = ["---"]
    out += [f"{k}: {fm[k]}" for k in keys]
    out += ["---", "", f"# P-{num:04d} {issue['title']}", ""]
    for name in BODY_SECTIONS:
        value = sections.get(name, "")
        out += [f"## {name}", "", value if value else "_не указано_", ""]
    out += [MARKER]
    return "\n".join(out) + tail  # tail всегда начинается с перевода строки


def main() -> int:
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        event = json.load(f)
    issue = event.get("issue")
    if not issue or "pull_request" in issue:
        return 0
    action = event.get("action", "")
    comment = event.get("comment")

    ISSUES.mkdir(parents=True, exist_ok=True)
    num = issue["number"]
    existing = sorted(ISSUES.glob(f"P-{num:04d}*.md"))
    path = existing[0] if existing else ISSUES / f"P-{num:04d} {safe_title(issue['title'])}.md"
    old_text = path.read_text(encoding="utf-8") if existing else None

    # При комментарии статус и поля не меняем
    text = build(issue, "" if comment else action, old_text)

    if comment:
        date = comment["created_at"][:10]
        text = text.rstrip("\n") + (
            f"\n\n### Комментарий @{comment['user']['login']} ({date})\n\n{comment['body'].strip()}\n"
        )
    path.write_text(text, encoding="utf-8")
    print(f"written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
