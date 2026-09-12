# Profile maintenance

The README uses native GitHub Markdown/HTML and repository-hosted SVGs. It has no weekly time tracking, pie charts, remote analytics cards, or trophy-service dependencies.

It does use animation, which reverses an earlier decision in this file. The objection to animated profile READMEs is that they are usually remote-hosted, uncacheable and decorative; these are none of those. `assets/hero.svg` and `assets/journey.svg` animate with CSS keyframes declared inside the file itself, served from this repository, and every animated asset wraps its keyframes in `@media (prefers-reduced-motion: reduce)` so a reader who has asked their system for less motion sees a still image. No GIFs: a GIF cannot switch palettes for dark mode, cannot honour that preference, and costs two orders of magnitude more bytes for the same result.

## Contribution data

`scripts/contributions.graphql` queries GitHub's `user.contributionsCollection` for the past year. `scripts/update_activity.py` creates one green contribution heatmap (`assets/contributions.svg`) with light/dark colors inside the SVG. The README also embeds `assets/hero.svg`, `assets/journey.svg`, nine section glyphs under `assets/icons/` and six project marks under `assets/marks/`. Those carry no live data, so they are committed once rather than rewritten on every refresh, which keeps the scheduled commit diff to the chart and the marker blocks.

Colour tokens for every generated asset live in `scripts/theme.py`, so the chart, the hero and the journey profile resolve the same palette. Two rules that file encodes: the accent stays GitHub's contribution green so the calendar belongs to the page, and amber means risk and nothing else. Embedded SVGs cannot fetch a webfont, so all text uses the system stacks pinned in that module.

`scripts/projects.graphql` fetches seven public repositories for six project cards. NextStop.ai has separate web and desktop statistics. Each displays default-branch history counts, stars, the default branch, and a linked head commit date in UTC. Counts include all authors and are not limited to the profile's contribution year. The global refresh timestamp is separate from each project's last commit date; metadata changes and stars do not make a project appear recently coded.

The contribution chart displays contributions, commits, active days, and the maximum contributions in a day. It does not display pull request or review metrics. The chart links to GitHub's native interactive calendar; embedded SVG images in a README do not provide dependable per-square hover tooltips.

- Each square is a day, colored using GitHub's contribution level. Contributions include more than commits, so the total is not labeled as a commit count.
- The repository table ranks public repositories by commit contributions in the same period. It excludes this profile repository so refresh commits do not crowd out project work. GitHub returns up to 100 repository groups; the table displays the top six public entries from those results.
- No API token or raw API response is saved. Private repository names are excluded from the published table. Aggregate counts reflect what GitHub exposes to the authenticating token.
- API errors, partial GraphQL responses, invalid calendar data, or missing/private project repositories fail the update before changing files. On GitHub, assets and README changes are published together in one commit; failed runs preserve the last successful version.

## Automatic refresh

`.github/workflows/profile-activity.yml` runs at 00:23, 06:23, 12:23, and 18:23 UTC, on relevant pushes to `main`, and on manual dispatch. Pull requests only run tests. It uses the built-in `GITHUB_TOKEN` with `contents: write` in the update job; no WakaTime account, external hosting, or personal access token is needed for public activity.

The workflow becomes active when these files reach the default branch on GitHub and Actions is enabled. GitHub schedules and image caching can delay the visible refresh; this is a periodically updated chart, not a browser-live API connection. The image includes the last successful update time. GitHub may disable scheduled workflows after 60 days of repository inactivity.

Run **Actions → Update profile activity → Run workflow** for an immediate refresh. If it fails, inspect the run: GraphQL needs an authenticated token, repository policy must permit Actions, and branch rules must allow the bot's update commit. A rejected push fails safely; it never force-pushes over someone else's edits.

## Local commands

Authenticate once with `gh auth login`, then run from the repository root:

```sh
python -m unittest discover -s tests -v
python scripts/update_activity.py --username krishna0605
```

The script requires Python 3.11+ and GitHub CLI, with no Python packages to install. Keep edits outside paired `START_SECTION:*` / `END_SECTION:*` markers. The `activity`, `updated`, and six `project-*` blocks are generated. Edit project descriptions, titles, and demo links outside those blocks.

## References

- [GitHub GraphQL contributions schema](https://docs.github.com/en/graphql/reference/users#contributionscollection)
- [Authenticating Actions with GITHUB_TOKEN](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)
- [Scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
