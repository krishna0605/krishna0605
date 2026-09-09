from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from scripts import update_activity as activity


def fixture(start=date(2024, 2, 28), length=4):
    weeks = []
    for offset in range(length):
        current = start + timedelta(days=offset)
        weekday = (current.weekday() + 1) % 7
        if not weeks or weekday == 0:
            weeks.append({"contributionDays": []})
        weeks[-1]["contributionDays"].append({
            "date": current.isoformat(), "weekday": weekday,
            "contributionCount": offset % 5, "contributionLevel": activity.LEVELS[offset % 5],
        })
    collection = {
        "startedAt": start.isoformat() + "T00:00:00Z",
        "endedAt": (start + timedelta(days=length - 1)).isoformat() + "T23:59:59Z",
        "totalCommitContributions": 3,
        "contributionCalendar": {"totalContributions": sum(i % 5 for i in range(length)), "weeks": weeks},
        "commitContributionsByRepository": [],
    }
    return {"data": {"user": {"login": "krishna0605", "contributionsCollection": collection}}}


class ActivityTests(unittest.TestCase):
    def test_leap_day_and_partial_week_positions_in_both_themes(self):
        data = activity.validate_response(fixture(), "krishna0605")
        for theme in activity.THEMES:
            svg = activity.render_svg(data, theme, "2024-03-02 12:00 UTC")
            root = ET.fromstring(svg)
            ns = {"svg": "http://www.w3.org/2000/svg"}
            days = [rect for rect in root.findall("svg:rect", ns) if rect.find("svg:title", ns) is not None]
            self.assertEqual(len(days), 4)
            self.assertEqual(days[0].get("y"), str(156 + 3 * 14))
            self.assertIn("2024-02-29", svg)
            self.assertNotIn("<script", svg)

    def test_full_54_week_calendar_fits_viewbox(self):
        data = activity.validate_response(fixture(date(2028, 1, 1), 371), "krishna0605")
        root = ET.fromstring(activity.render_svg(data, "light", "test"))
        for rect in root.findall("{http://www.w3.org/2000/svg}rect"):
            self.assertLessEqual(float(rect.get("x")) + float(rect.get("width")), 900)
            self.assertLessEqual(float(rect.get("y")) + float(rect.get("height")), 306)

    def test_partial_graphql_errors_are_rejected(self):
        payload = fixture()
        payload["errors"] = [{"message": "rate limit"}]
        with self.assertRaises(ValueError):
            activity.validate_response(payload, "krishna0605")

    def test_invalid_dates_counts_and_missing_users_are_rejected(self):
        for field, value in (("weekday", 0), ("date", "invalid"), ("contributionCount", -1), ("contributionLevel", "unknown")):
            payload = fixture()
            payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"][0]["contributionDays"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                activity.validate_response(payload, "krishna0605")
        with self.assertRaises(ValueError):
            activity.validate_response({"data": {"user": None}}, "krishna0605")

    def test_private_repositories_and_profile_automation_are_excluded(self):
        data = activity.validate_response(fixture(), "krishna0605")
        for name, count, private in (("secret", 999, True), ("krishna0605", 500, False), ("second", 4, False), ("first", 8, False)):
            data["commitContributionsByRepository"].append({
                "repository": {"nameWithOwner": f"krishna0605/{name}", "url": f"https://github.com/krishna0605/{name}", "isPrivate": private},
                "contributions": {"totalCount": count},
            })
        rendered = activity.repository_section(data, "krishna0605")
        self.assertNotIn("secret", rendered)
        self.assertNotIn("krishna0605/krishna0605", rendered)
        self.assertLess(rendered.index("/first"), rendered.index("/second"))

    def test_empty_activity_is_honest_and_renders(self):
        data = activity.validate_response(fixture(length=1), "krishna0605")
        self.assertIn("No public repository", activity.repository_section(data, "krishna0605"))
        self.assertIn("0 contributions", activity.render_svg(data, "dark", "test"))

    def test_only_marker_block_changes_and_ambiguous_markers_fail(self):
        readme = f"Before\n{activity.START}\nold\n{activity.END}\nAfter"
        self.assertEqual(activity.replace_section(readme, "new"), f"Before\n{activity.START}\n\nnew\n\n{activity.END}\nAfter")
        for invalid in ("no markers", readme + activity.START, activity.END + activity.START):
            with self.assertRaises(ValueError):
                activity.replace_section(invalid, "new")

    def test_api_failure_keeps_existing_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "assets").mkdir()
            (root / "README.md").write_text("original README", encoding="utf-8")
            (root / "assets/contributions.svg").write_text("original SVG", encoding="utf-8")
            with patch.object(activity, "fetch_activity", side_effect=RuntimeError("API unavailable")):
                with self.assertRaises(RuntimeError):
                    activity.update(root, "krishna0605")
            self.assertEqual((root / "README.md").read_text(), "original README")
            self.assertEqual((root / "assets/contributions.svg").read_text(), "original SVG")

    def test_bad_markers_keep_existing_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("missing markers", encoding="utf-8")
            data = activity.validate_response(fixture(), "krishna0605")
            with patch.object(activity, "fetch_activity", return_value=data):
                with self.assertRaises(ValueError):
                    activity.update(root, "krishna0605")
            self.assertFalse((root / "assets").exists())

    def test_repository_urls_cannot_inject_markup(self):
        payload = fixture()
        data = payload["data"]["user"]["contributionsCollection"]
        data["commitContributionsByRepository"] = [{
            "repository": {"nameWithOwner": "krishna0605/project", "url": "javascript:alert(1)", "isPrivate": False},
            "contributions": {"totalCount": 1},
        }]
        with self.assertRaises(ValueError):
            activity.validate_response(payload, "krishna0605")

    def test_chart_has_green_colors_and_no_pr_or_review_metrics(self):
        data = activity.validate_response(fixture(), "krishna0605")
        svg = activity.render_svg(data, "light", "test")
        self.assertIn("#40c463", svg)
        self.assertIn("#39d353", svg)
        self.assertIn("Active days", svg)
        self.assertIn("Most in one day", svg)
        self.assertNotIn("Pull requests", svg)
        self.assertNotIn("Reviews", svg)

def project_fixture():
    return {"data": {key: {
        "nameWithOwner": f"krishna0605/{name}", "url": f"https://github.com/krishna0605/{name}",
        "isPrivate": False, "stargazerCount": 3,
        "defaultBranchRef": {"name": "main", "target": {
            "committedDate": "2026-09-08T22:00:00Z", "url": f"https://github.com/krishna0605/{name}/commit/" + "a" * 40,
            "history": {"totalCount": 1234},
        }},
    } for key, name in activity.PROJECTS.items()}}


class ProjectStatsTests(unittest.TestCase):
    def test_project_count_date_and_history_are_linked(self):
        repo = activity.validate_projects(project_fixture(), "krishna0605")["netra"]
        html = activity.project_stats(repo)
        self.assertIn("1,234 commits", html)
        self.assertIn("08 Sep 2026", html)
        self.assertIn("/Netra/commits/main/", html)
        self.assertIn("/Netra/commit/" + "a" * 40, html)

    def test_empty_repository_and_special_branch_name(self):
        payload = project_fixture()
        payload["data"]["netra"]["defaultBranchRef"] = None
        repo = activity.validate_projects(payload, "krishna0605")["netra"]
        self.assertIn("0 commits", activity.project_stats(repo))
        self.assertIn("No commits yet", activity.project_stats(repo))
        repo = project_fixture()["data"]["netra"]
        repo["defaultBranchRef"]["name"] = "release/security&review"
        html = activity.project_stats(repo)
        self.assertIn("release%2Fsecurity%26review", html)
        self.assertIn("security&amp;review", html)

    def test_private_missing_or_partial_projects_fail(self):
        for change in ("private", "missing", "errors"):
            payload = project_fixture()
            if change == "private":
                payload["data"]["netra"]["isPrivate"] = True
            elif change == "missing":
                payload["data"]["netra"] = None
            else:
                payload["errors"] = [{"message": "Unavailable"}]
            with self.subTest(change=change), self.assertRaises(ValueError):
                activity.validate_projects(payload, "krishna0605")

    def test_project_failure_preserves_all_files(self):
        names = ["activity", "updated"] + [f"project-{key}" for key in activity.PROJECTS if key != "nextstopDesktop"]
        readme = "\n".join(f"<!--START_SECTION:{name}-->old<!--END_SECTION:{name}-->" for name in names)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text(readme, encoding="utf-8")
            (root / "assets").mkdir()
            (root / "assets/contributions.svg").write_text("previous chart", encoding="utf-8")
            data = activity.validate_response(fixture(), "krishna0605")
            with patch.object(activity, "fetch_activity", return_value=data), patch.object(activity, "fetch_projects", side_effect=ValueError("failed")):
                with self.assertRaises(ValueError):
                    activity.update(root, "krishna0605")
            self.assertEqual((root / "README.md").read_text(), readme)
            self.assertEqual((root / "assets/contributions.svg").read_text(), "previous chart")

    def test_full_refresh_keeps_one_chart_and_updates_six_cards(self):
        names = ["activity", "updated"] + [f"project-{key}" for key in activity.PROJECTS if key != "nextstopDesktop"]
        readme = '<img src="assets/contributions.svg">\n' + "\n".join(f"<!--START_SECTION:{name}-->old<!--END_SECTION:{name}-->" for name in names)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text(readme, encoding="utf-8")
            data = activity.validate_response(fixture(), "krishna0605")
            projects = activity.validate_projects(project_fixture(), "krishna0605")
            with patch.object(activity, "fetch_activity", return_value=data), patch.object(activity, "fetch_projects", return_value=projects):
                activity.update(root, "krishna0605")
            result = (root / "README.md").read_text(encoding="utf-8")
            self.assertEqual(result.count("assets/contributions.svg"), 1)
            self.assertEqual(result.count("1,234 commits"), 7)
            self.assertIn("<b>Web</b>", result)
            self.assertIn("<b>Desktop</b>", result)
            self.assertNotIn("START_SECTION:days", result)
            self.assertEqual(len(list((root / "assets").glob("*.svg"))), 1)


if __name__ == "__main__":
    unittest.main()
