"""
Deploy generated HTML to GitHub Pages by committing and pushing to the mapper repo.

The docs/ directory is committed to the main branch.
GitHub Pages is configured to serve from /docs on the main branch.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import git
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False

REPO_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = REPO_ROOT / 'docs'
GITHUB_USER = 'robhummel'
GITHUB_REPO = 'mapper'
PAGES_BASE_URL = f'https://{GITHUB_USER}.github.io/{GITHUB_REPO}'


def _regenerate_index(output_dir: Path) -> None:
    """Regenerate output/index.html listing all report HTML files."""
    reports = sorted(
        p for p in output_dir.glob('*.html')
        if p.name != 'index.html'
    )

    items_html = ''
    for r in reports:
        # Try to extract title from <title> tag
        try:
            content = r.read_text(encoding='utf-8')
            import re
            m = re.search(r'<title>(.*?)</title>', content)
            title = m.group(1) if m else r.stem
        except Exception:
            title = r.stem

        url = f'{PAGES_BASE_URL}/{r.name}'
        items_html += f'<li><a href="{r.name}">{title}</a></li>\n'

    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Trail Hazard Reports</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 600px; margin: 40px auto; padding: 0 20px; }}
    h1 {{ color: #e63946; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ margin: 12px 0; }}
    a {{ color: #333; font-size: 1.05rem; text-decoration: none; border-bottom: 1px solid #ddd; padding-bottom: 2px; }}
    a:hover {{ color: #e63946; border-color: #e63946; }}
    .updated {{ color: #aaa; font-size: 0.8rem; margin-top: 24px; }}
  </style>
</head>
<body>
  <h1>⚠️ Trail Hazard Reports</h1>
  <ul>
{items_html}  </ul>
  <p class="updated">Last updated: {datetime.now().strftime('%-d %B %Y')}</p>
</body>
</html>"""

    (output_dir / 'index.html').write_text(index_html, encoding='utf-8')


def deploy(html_path: Path, report_name: str, dry_run: bool = False) -> Optional[str]:
    """
    Commit the HTML file to the repo and push to GitHub Pages.

    Args:
        html_path: Path to the generated HTML file (inside output/).
        report_name: Human-readable report name for the commit message.
        dry_run: If True, skip the git push.

    Returns:
        The GitHub Pages URL for the report, or None on failure.
    """
    if not GIT_AVAILABLE:
        print("  ⚠ gitpython not installed — skipping GitHub Pages deploy")
        return None

    try:
        repo = git.Repo(REPO_ROOT)
    except git.InvalidGitRepositoryError:
        print(f"  ✗ Not a git repo: {REPO_ROOT}")
        return None

    # Regenerate index
    _regenerate_index(OUTPUT_DIR)

    # Stage output/ directory
    repo.index.add([
        str(html_path.relative_to(REPO_ROOT)),
        'output/index.html',
    ])

    if not repo.index.diff('HEAD') and not repo.untracked_files:
        # Nothing actually changed
        pass

    date_str = datetime.now().strftime('%Y-%m-%d')
    commit_msg = f"Add report: {report_name} ({date_str})\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

    try:
        repo.index.commit(commit_msg)
    except Exception as e:
        print(f"  ⚠ Git commit issue: {e}")

    page_url = f"{PAGES_BASE_URL}/{html_path.name}"

    if dry_run:
        print(f"  (dry run — skipping git push)")
        print(f"  Would be available at: {page_url}")
        return page_url

    try:
        origin = repo.remote(name='origin')
        push_result = origin.push()
        for info in push_result:
            if info.flags & info.ERROR:
                print(f"  ✗ Push error: {info.summary}")
                return None
        print(f"  ✓ Pushed to GitHub")
    except Exception as e:
        print(f"  ✗ Git push failed: {e}")
        print(f"    Run manually: git push origin main")
        return None

    return page_url
