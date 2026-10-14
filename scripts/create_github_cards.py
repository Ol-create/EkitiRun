"""Create EkitiRun task cards on GitHub from docs/tasks/*.md.

Dry run (default) prints what would be created:
    python scripts/create_github_cards.py
Create everything:
    python scripts/create_github_cards.py --apply

Safe to re-run: existing labels, milestones, issues (matched by the
"[E1]" style title prefix) and the project are reused, not duplicated.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

OWNER = "Ol-create"
REPO = f"{OWNER}/EkitiRun"
PROJECT_TITLE = "EkitiRun v1"
DOCS = Path(__file__).resolve().parent.parent / "docs"
DOCS_URL = f"https://github.com/{REPO}/blob/main/docs"

PEOPLE = {
    # role label: (github username, task file, short role description)
    "lead": ("Ol-create", "lead.md", "Lead"),
    "frontend-1": ("logicgirl", "frontend-1.md", "Frontend 1"),
    "frontend-2": ("Greatest-grace123", "frontend-2.md", "Frontend 2"),
    "backend": ("sammyfemmy", "backend.md", "Backend"),
}

MILESTONES = {
    0: "Phase 0: Foundation",
    1: "Phase 1: Registration & Sponsors",
    2: "Phase 2: Timing & Tracking",
    3: "Phase 3: Hardening",
}

LABELS = {
    "lead": ("0B6E4F", "Lead's work"),
    "frontend-1": ("1D76DB", "Registration and sponsor screens"),
    "frontend-2": ("5319E7", "Public race-day pages"),
    "backend": ("D93F0B", "Sponsor and public read endpoints"),
    "phase-0": ("EDEDED", "Foundation"),
    "phase-1": ("C5DEF5", "Registration and sponsors"),
    "phase-2": ("BFD4F2", "Timing and tracking"),
    "phase-3": ("D4C5F9", "Hardening"),
    "onboarding": ("FBCA04", "Getting set up"),
}

# Phase for newbie tickets (lead.md carries its own "## Phase N" headings).
NEWBIE_PHASE = {"B3": 2}
DEFAULT_NEWBIE_PHASE = 1

APPLY = "--apply" in sys.argv


def gh(*args, check=True):
    # Retry transient network failures (slow or flaky connections).
    for attempt in range(5):
        result = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
        if "error connecting to" not in result.stderr and "timeout" not in result.stderr.lower():
            break
        time.sleep(3 * (attempt + 1))
    if check and result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}… failed:\n{result.stderr.strip()}")
    return result


def gh_json(*args):
    return json.loads(gh(*args).stdout or "null")


# ---------------------------------------------------------------- parsing

TICKET_RE = re.compile(r"^(#{2,3}) ((?:E\d+|F\d\.\d|B\d)): (.+?) \((\d+) pts?.*\)\s*$")
PHASE_RE = re.compile(r"^## Phase (\d)")


def section_after(lines, start, level):
    """Lines after a heading until the next heading of the same/higher level or '---'."""
    out = []
    for line in lines[start + 1:]:
        m = re.match(r"^(#+) ", line)
        if (m and len(m.group(1)) <= level) or line.strip() == "---":
            break
        out.append(line)
    return "\n".join(out).strip()


def parse_tickets():
    tickets = []
    for role, (user, filename, role_name) in PEOPLE.items():
        lines = (DOCS / "tasks" / filename).read_text(encoding="utf-8").splitlines()
        phase = None
        for i, line in enumerate(lines):
            pm = PHASE_RE.match(line)
            if pm:
                phase = int(pm.group(1))
            m = TICKET_RE.match(line)
            if not m:
                continue
            level, tid, title, pts = len(m.group(1)), m.group(2), m.group(3), int(m.group(4))
            if role != "lead":
                phase = NEWBIE_PHASE.get(tid, DEFAULT_NEWBIE_PHASE)
            tickets.append(dict(id=tid, title=title, points=pts, phase=phase, role=role,
                                user=user, file=filename, body=section_after(lines, i, level)))

        if role != "lead":
            idx = next(i for i, l in enumerate(lines) if l.startswith("## Before you start"))
            tickets.insert(len(tickets) - sum(t["role"] == role for t in tickets), dict(
                id=f"ON-{role_name.replace(' ', '')}", title=f"Onboarding: {role_name} setup",
                points=0, phase=0, role=role, user=user, file=filename,
                body=re.sub(r"(?m)^- ", "- [ ] ", section_after(lines, idx, 2)) + "\n- [ ] Open a first small PR (e.g. add your name to the README) and get it merged",
                onboarding=True))
    return tickets


def issue_body(t):
    pts = f" · **Points:** {t['points']}" if t["points"] else ""
    if t["role"].startswith("frontend"):
        done = "CI passes · works at 375px · loading, empty and error states"
    else:
        done = "CI passes · pytest tests for new endpoints · responses match the API contract"
    return (
        f"**Owner:** @{t['user']}{pts} · **Milestone:** {MILESTONES[t['phase']]}\n\n"
        f"📄 Task file: [{t['file']}]({DOCS_URL}/tasks/{t['file']}) · "
        f"API contract: [api-contract.md]({DOCS_URL}/api-contract.md)\n\n---\n\n"
        f"{t['body']}\n\n---\n\n"
        f"**Definition of done:** {done} · acceptance criteria ticked in the PR. "
        "Put `Closes #<this issue>` in the PR description."
    )


# ---------------------------------------------------------------- GitHub

def ensure_labels():
    existing = {l["name"] for l in gh_json("label", "list", "-R", REPO, "--limit", "200", "--json", "name")}
    for name, (color, desc) in LABELS.items():
        if name not in existing:
            gh("label", "create", name, "-R", REPO, "--color", color, "--description", desc)
            print(f"  + label {name}")


def ensure_milestones():
    existing = {m["title"]: m["number"] for m in
                gh_json("api", f"repos/{REPO}/milestones?state=all&per_page=100")}
    for title in MILESTONES.values():
        if title not in existing:
            gh("api", f"repos/{REPO}/milestones", "-f", f"title={title}")
            print(f"  + milestone {title}")


def invite_collaborators():
    for user, _, _ in PEOPLE.values():
        if user.lower() == OWNER.lower():
            continue
        if gh("api", f"repos/{REPO}/collaborators/{user}", check=False).returncode == 0:
            continue
        gh("api", "-X", "PUT", f"repos/{REPO}/collaborators/{user}", "-f", "permission=push")
        print(f"  + invited {user} (they must accept the invite before they can be assigned)")


def ensure_project():
    projects = gh_json("project", "list", "--owner", OWNER, "--format", "json")["projects"]
    project = next((p for p in projects if p["title"] == PROJECT_TITLE), None)
    if not project:
        project = gh_json("project", "create", "--owner", OWNER, "--title", PROJECT_TITLE, "--format", "json")
        print(f"  + project {PROJECT_TITLE}")
    gh("project", "link", str(project["number"]), "--owner", OWNER, "--repo", REPO, check=False)
    return project


def create_issues(tickets, project):
    existing = {}
    for issue in gh_json("issue", "list", "-R", REPO, "--state", "all", "--limit", "500", "--json", "title,url"):
        m = re.match(r"^\[([^\]]+)\]", issue["title"])
        if m:
            existing[m.group(1)] = issue["url"]

    failed_assign = set()
    for t in tickets:
        title = f"[{t['id']}] {t['title']}"
        labels = [t["role"], f"phase-{t['phase']}"] + (["onboarding"] if t.get("onboarding") else [])
        url = existing.get(t["id"])
        if not url:
            url = gh("issue", "create", "-R", REPO, "--title", title, "--body", issue_body(t),
                     "--label", ",".join(labels), "--milestone", MILESTONES[t["phase"]]).stdout.strip()
            print(f"  + {title}  {url}")
        if gh("issue", "edit", url, "--add-assignee", t["user"], check=False).returncode != 0:
            failed_assign.add(t["user"])
        gh("project", "item-add", str(project["number"]), "--owner", OWNER, "--url", url, check=False)

    if failed_assign:
        print("\n⚠ Could not assign: " + ", ".join(sorted(failed_assign)) +
              ".\n  They probably haven't accepted the repo invite yet. Re-run this script "
              "with --apply after they accept, and it will assign them.")


def main():
    tickets = parse_tickets()
    total = {}
    for t in tickets:
        total[t["user"]] = total.get(t["user"], 0) + t["points"]

    print(f"{len(tickets)} cards for {REPO}:\n")
    for t in tickets:
        print(f"  [{t['id']:<15}] {t['title'][:55]:<55} @{t['user']:<18} phase-{t['phase']}  {t['points']} pts")
    print("\nPoints per person: " + ", ".join(f"@{u} {p}" for u, p in total.items()))

    if not APPLY:
        print("\nDry run only. Re-run with --apply to create everything on GitHub.")
        return

    print("\nLabels…");       ensure_labels()
    print("Milestones…");     ensure_milestones()
    print("Collaborators…");  invite_collaborators()
    print("Project…");        project = ensure_project()
    print("Issues…");         create_issues(tickets, project)
    print(f"\nDone. Board: https://github.com/users/{OWNER}/projects/{project['number']}")


if __name__ == "__main__":
    main()
