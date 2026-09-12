"""Generate profile activity assets from GitHub GraphQL, using only the stdlib.

Authenticate with `gh auth login` locally or GH_TOKEN in GitHub Actions.
API errors stop the update before any existing profile assets are changed.
"""

import argparse
from datetime import date, datetime, timezone
from html import escape
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import quote

try:  # imported as part of the package (tests)
    from scripts import theme as tokens
except ImportError:  # run directly, with scripts/ on sys.path
    import theme as tokens

THEMES = tokens.THEMES
CHART_VARS = ("bg", "border", "text", "muted", "accent", "rule", "ink", "dim")


ROOT = Path(__file__).resolve().parents[1]
START = "<!--START_SECTION:activity-->"
END = "<!--END_SECTION:activity-->"
LEVELS = ("NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE")


PROJECTS = {
    "netra": "Netra", "nextstop": "NextStop.AI-Web", "nextstopDesktop": "NextStop.AI-Desktop",
    "codemate": "AI-codemate-", "vulnscanner": "vulnscanner", "threatforge": "ThreatForge", "healthdoc": "healthdoc",
}


def graphql(login, query_file):
    payload = json.dumps({
        "query": (ROOT / "scripts" / query_file).read_text(encoding="utf-8"),
        "variables": {"login": login},
    })
    for attempt in range(3):
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "--input", "-"], input=payload,
                capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
            )
        except subprocess.TimeoutExpired:
            if attempt == 2:
                raise RuntimeError("GitHub GraphQL timed out; existing assets were retained.") from None
        else:
            if result.returncode == 0:
                response = json.loads(result.stdout)
                if response.get("errors"):
                    raise ValueError("GraphQL returned errors; partial data will not be published.")
                return response
            if attempt == 2:
                # Do not print subprocess output: API responses can contain private metadata.
                raise RuntimeError("GitHub GraphQL failed. Check gh authentication, permissions, and API availability.")
        time.sleep(2 ** attempt)
    raise RuntimeError("GitHub GraphQL did not return a response.")


def fetch_activity(login):
    return validate_response(graphql(login, "contributions.graphql"), login)


def validate_projects(payload, login):
    if payload.get("errors"):
        raise ValueError("Project query returned partial data.")
    projects = payload.get("data") or {}
    for key, name in PROJECTS.items():
        repo = projects.get(key)
        if not repo or repo.get("isPrivate") is not False:
            raise ValueError(f"Public project metadata unavailable: {key}.")
        expected = f"{login}/{name}"
        if repo["nameWithOwner"].lower() != expected.lower() or repo["url"] != "https://github.com/" + repo["nameWithOwner"]:
            raise ValueError("Unexpected project identity.")
        nonnegative(repo["stargazerCount"])
        branch = repo["defaultBranchRef"]
        if branch is not None:
            if not isinstance(branch["name"], str) or not branch["name"]:
                raise ValueError("Missing default branch name.")
            target = branch["target"]
            nonnegative(target["history"]["totalCount"])
            parsed = datetime.fromisoformat(target["committedDate"].replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("Commit timestamp requires a timezone.")
            if not re.fullmatch(re.escape(repo["url"]) + r"/commit/[0-9a-f]{40}", target["url"]):
                raise ValueError("Unexpected commit URL.")
    return projects


def fetch_projects(login):
    return validate_projects(graphql(login, "projects.graphql"), login)


def nonnegative(value):
    if type(value) is not int or value < 0:
        raise ValueError("Expected a nonnegative contribution count.")
    return value


def validate_response(payload, login):
    if payload.get("errors"):
        raise ValueError("GraphQL returned errors; partial data will not be published.")
    user = payload.get("data", {}).get("user")
    if not user or user.get("login", "").lower() != login.lower():
        raise ValueError("GraphQL did not return the requested profile.")
    activity = user["contributionsCollection"]
    period_start = date.fromisoformat(activity["startedAt"][:10])
    period_end = date.fromisoformat(activity["endedAt"][:10])
    # GitHub can align the default past-year collection to a week boundary.
    if not 0 <= (period_end - period_start).days <= 371:
        raise ValueError("Unexpected contribution period.")
    calendar = activity["contributionCalendar"]
    nonnegative(calendar["totalContributions"])
    nonnegative(activity["totalCommitContributions"])
    weeks = calendar["weeks"]
    if not 1 <= len(weeks) <= 54:
        raise ValueError("Unexpected number of calendar weeks.")
    previous = None
    for week in weeks:
        days = week["contributionDays"]
        if not 1 <= len(days) <= 7:
            raise ValueError("Unexpected number of days in a week.")
        for day in days:
            current = date.fromisoformat(day["date"])
            if day["weekday"] != (current.weekday() + 1) % 7:
                raise ValueError("Calendar weekday does not match its date.")
            if previous and (current - previous).days != 1:
                raise ValueError("Calendar dates are not consecutive.")
            previous = current
            nonnegative(day["contributionCount"])
            if day["contributionLevel"] not in LEVELS:
                raise ValueError("Unknown contribution level.")
    for item in activity["commitContributionsByRepository"]:
        nonnegative(item["contributions"]["totalCount"])
        repo = item["repository"]
        if type(repo["isPrivate"]) is not bool:
            raise ValueError("Missing repository visibility.")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo["nameWithOwner"]):
            raise ValueError("Unexpected repository name.")
        if repo["url"] != "https://github.com/" + repo["nameWithOwner"]:
            raise ValueError("Unexpected repository URL.")
    return activity


def render_svg(activity, theme, updated):
    # One SVG, with CSS theme switching inside the image. No duplicate <picture> sources.
    palette = {key: f"var(--{key})" for key in ("bg", "border", "text", "muted", "accent")}
    palette["cells"] = tuple(f"var(--cell{i})" for i in range(5))
    calendar = activity["contributionCalendar"]
    start = calendar["weeks"][0]["contributionDays"][0]["date"]
    end = calendar["weeks"][-1]["contributionDays"][-1]["date"]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 306" role="img" aria-labelledby="title desc">',
        '<title id="title">GitHub contribution activity</title>',
        f'<desc id="desc">{calendar["totalContributions"]:,} contributions from {start} to {end}. '
        f'Last successful update: {escape(updated)}. Each square represents one day.</desc>',
        '<style>' + tokens.theme_css(CHART_VARS, cells=True)
        + 'text{font-family:' + tokens.SANS + '}'
        + '.s{font-family:' + tokens.SERIF + '}'
        + '.l{letter-spacing:1.6px}</style>',
        f'<rect x="0.5" y="0.5" width="899" height="305" rx="8" fill="{palette["bg"]}" stroke="var(--rule)"/>',
        f'<rect x="28" y="26" width="3" height="24" rx="1.5" fill="{palette["accent"]}"/>',
    ]

    def text(x, y, content, size=12, color=None, weight=400, cls=""):
        name = f' class="{cls}"' if cls else ""
        parts.append(f'<text x="{x}" y="{y}"{name} font-size="{size}" font-weight="{weight}" '
                     f'fill="{color or palette["muted"]}">{escape(str(content))}</text>')

    text(43, 43, "Contribution activity", 17, palette["text"], 400, "s")
    text(610, 42, f"{start} — {end}", 12)
    days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
    metrics = (
        ("Contributions", calendar["totalContributions"]),
        ("Commits", activity["totalCommitContributions"]),
        ("Active days", sum(day["contributionCount"] > 0 for day in days)),
        ("Most in one day", max(day["contributionCount"] for day in days)),
    )
    for index, (label, count) in enumerate(metrics):
        x = 32 + index * 218
        text(x, 88, f"{count:,}", 25, palette["text"], 400, "s")
        text(x, 109, label.upper(), 10, None, 600, "l")
    # A fixed pitch keeps all 52–54-week calendars inside the same viewBox.
    grid_x, grid_y, pitch = 80, 156, 14
    for weekday, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        text(33, grid_y + weekday * pitch + 10, label, 11)
    previous_month = None
    last_label_x = -100
    for column, week in enumerate(calendar["weeks"]):
        first_day = date.fromisoformat(week["contributionDays"][0]["date"])
        month = (first_day.year, first_day.month)
        x = grid_x + column * pitch
        if month != previous_month:
            if x - last_label_x >= 35 and x < 825:
                text(x, 145, first_day.strftime("%b"), 11)
                last_label_x = x
            previous_month = month
        for day in week["contributionDays"]:
            y = grid_y + day["weekday"] * pitch
            color = palette["cells"][LEVELS.index(day["contributionLevel"])]
            label = f'{day["date"]}: {day["contributionCount"]} contributions'
            parts.append(f'<rect x="{x}" y="{y}" width="11" height="11" rx="2" fill="{color}">'
                         f'<title>{escape(label)}</title></rect>')
    text(32, 281, f"Updated {updated}", 11)
    text(704, 281, "Less", 10)
    for index, color in enumerate(palette["cells"]):
        parts.append(f'<rect x="{735 + index * 14}" y="271" width="11" height="11" rx="2" fill="{color}"/>')
    text(811, 281, "More", 10)
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def repository_section(activity, login):
    repos = [item for item in activity["commitContributionsByRepository"]
             if not item["repository"]["isPrivate"]
             and item["repository"]["nameWithOwner"].lower() != f"{login}/{login}".lower()
             and item["contributions"]["totalCount"] > 0]
    repos.sort(key=lambda item: (-item["contributions"]["totalCount"], item["repository"]["nameWithOwner"].lower()))
    period = f'{activity["startedAt"][:10]} to {activity["endedAt"][:10]}'
    lines = [f"Public repositories ranked by commit contributions, {period}. Profile automation is excluded.", ""]
    if not repos:
        lines.append("No public repository commit contributions were returned for this period.")
    else:
        lines += ["| Repository | Commit contributions |", "| :--- | ---: |"]
        for item in repos[:6]:
            repo = item["repository"]
            lines.append(f'| [{repo["nameWithOwner"]}]({repo["url"]}) | {item["contributions"]["totalCount"]:,} |')
    return "\n".join(lines)


def replace_section(readme, section):
    return replace_named_section(readme, "activity", section)


def replace_named_section(readme, name, section):
    start, end = f"<!--START_SECTION:{name}-->", f"<!--END_SECTION:{name}-->"
    if readme.count(start) != 1 or readme.count(end) != 1 or readme.index(start) > readme.index(end):
        raise ValueError("README must contain one correctly ordered activity marker pair.")
    before, remainder = readme.split(start)
    _, after = remainder.split(end)
    return f"{before}{start}\n\n{section}\n\n{end}{after}"


def project_stats(repo, label=None):
    prefix = f"<b>{escape(label)}</b> · " if label else ""
    branch = repo["defaultBranchRef"]
    if branch is None:
        return f"<p>{prefix}<b>0 commits</b> · No commits yet<br><sub>★ {repo['stargazerCount']:,} stars</sub></p>"
    target = branch["target"]
    committed = datetime.fromisoformat(target["committedDate"].replace("Z", "+00:00")).astimezone(timezone.utc)
    commit_date = committed.strftime("%d %b %Y")
    count = target["history"]["totalCount"]
    history_url = repo["url"] + "/commits/" + quote(branch["name"], safe="") + "/"
    return (f'<p>{prefix}<a href="{escape(history_url)}"><b>{count:,} commits</b></a> · '
            f'<a href="{escape(repo["url"] + "/stargazers")}">★ {repo["stargazerCount"]:,}</a><br>'
            f'<sub>Last commit: <a href="{escape(target["url"])}" title="{committed.isoformat()}">{commit_date}</a>'
            f' · <code>{escape(branch["name"])}</code></sub></p>')


def update(root, login):
    activity = fetch_activity(login)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    readme_path = root / "README.md"
    # Render and validate everything before touching any tracked file.
    readme = replace_section(readme_path.read_text(encoding="utf-8"), repository_section(activity, login))
    projects = fetch_projects(login)
    for key in PROJECTS:
        if key == "nextstopDesktop":
            continue
        stats = project_stats(projects[key], "Web" if key == "nextstop" else None)
        if key == "nextstop":
            stats += "\n" + project_stats(projects["nextstopDesktop"], "Desktop")
        readme = replace_named_section(readme, f"project-{key}", stats)
    readme = replace_named_section(readme, "updated", f"<sub>Repository data refreshed {updated}. Commit counts include all authors on each default branch. Last commit dates link to the changes.</sub>")
    outputs = {root / "assets/contributions.svg": render_svg(activity, "light", updated)}
    outputs[readme_path] = readme
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)
    print("Updated one contribution chart, all six project cards, and repository activity.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="krishna0605")
    args = parser.parse_args()
    try:
        update(ROOT, args.username)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        print(f"Activity update failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
