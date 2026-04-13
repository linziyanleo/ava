"""Download a skill from a GitHub repo subdirectory using gh CLI.

Supports URL formats:
  - https://github.com/owner/repo/tree/ref/path/to/skill     (directory)
  - https://github.com/owner/repo/blob/ref/path/to/SKILL.md  (file → parent dir)
  - https://github.com/owner/repo                             (whole repo root)
  - https://github.com/owner/repo.git                         (whole repo root)

Uses `gh api` to fetch the directory tree and download files individually,
avoiding full repo clones.
"""

from __future__ import annotations

import json
import subprocess
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger

_DEFAULT_SKILLS_DIR = Path.home() / ".agents" / "skills"


def parse_github_url(url: str) -> dict:
    """Parse a GitHub URL into owner, repo, ref, and subpath.

    Returns:
        dict with keys: owner, repo, ref, subpath, skill_name
    """
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    parsed = urlparse(url)
    if parsed.hostname not in ("github.com", "www.github.com"):
        raise ValueError(f"Not a GitHub URL: {url}")

    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2:
        raise ValueError(f"Cannot parse owner/repo from: {url}")

    owner, repo = parts[0], parts[1]
    ref = "main"
    subpath = ""

    if len(parts) > 3 and parts[2] in ("blob", "tree"):
        ref = parts[3]
        subpath = "/".join(parts[4:])

        # If pointing to a file (e.g. SKILL.md), use parent directory
        if subpath.endswith(".md") or "." in subpath.split("/")[-1]:
            subpath = "/".join(subpath.split("/")[:-1])

    # Derive skill name from last path segment or repo name
    skill_name = subpath.rstrip("/").split("/")[-1] if subpath else repo

    return {
        "owner": owner,
        "repo": repo,
        "ref": ref,
        "subpath": subpath,
        "skill_name": skill_name,
    }


def _gh_api(endpoint: str) -> dict | list:
    """Call gh api and return parsed JSON."""
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _gh_api_raw(url: str, retries: int = 3) -> bytes:
    """Download raw file content via gh api with retry.

    Uses Contents API path (``/repos/…/contents/…``) instead of
    ``raw.githubusercontent.com`` URLs for reliability.
    """
    for attempt in range(1, retries + 1):
        result = subprocess.run(
            ["gh", "api", url, "-H", "Accept: application/vnd.github.raw+json"],
            capture_output=True,
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout
        err = result.stderr.decode().strip()
        if attempt < retries and ("EOF" in err or "timeout" in err.lower()):
            wait = attempt * 2
            logger.warning("Download attempt {}/{} failed ({}), retrying in {}s…", attempt, retries, err, wait)
            time.sleep(wait)
            continue
        raise RuntimeError(f"gh api download failed: {err}")
    # unreachable, but keeps mypy happy
    raise RuntimeError("gh api download failed after retries")


def download_skill_from_github(
    url: str,
    name: str | None = None,
    target_dir: Path | None = None,
) -> dict:
    """Download a skill from GitHub into target_dir.

    Args:
        url: GitHub URL (repo root, tree, or blob)
        name: Override skill directory name (default: auto-detect from URL)
        target_dir: Where to install (default: ~/.agents/skills/)

    Returns:
        dict with ok, name, path keys
    """
    info = parse_github_url(url)
    skill_name = name or info["skill_name"]
    dest_root = target_dir or _DEFAULT_SKILLS_DIR
    dest = dest_root / skill_name

    if dest.exists():
        raise ValueError(f"Skill '{skill_name}' already exists at {dest}")

    owner = info["owner"]
    repo = info["repo"]
    ref = info["ref"]
    subpath = info["subpath"]

    logger.info("Installing skill '{}' from {}/{} ref={} subpath='{}'", skill_name, owner, repo, ref, subpath)

    try:
        # Get directory tree from GitHub API
        api_path = f"/repos/{owner}/{repo}/contents/{subpath}" if subpath else f"/repos/{owner}/{repo}/contents"
        api_path += f"?ref={ref}"

        items = _list_tree_recursive(owner, repo, ref, subpath)

        if not items:
            raise ValueError(f"No files found at {owner}/{repo}/{subpath}")

        # Check for SKILL.md
        has_skill_md = any(i["name"] == "SKILL.md" for i in items if i["type"] == "file")
        if not has_skill_md:
            raise ValueError(f"No SKILL.md found in {owner}/{repo}/{subpath}")

        # Download all files
        dest.mkdir(parents=True, exist_ok=True)
        file_count = 0
        for item in items:
            if item["type"] != "file":
                continue
            rel = item["rel_path"]
            file_dest = dest / rel
            file_dest.parent.mkdir(parents=True, exist_ok=True)

            content = _gh_api_raw(item["download_url"])
            file_dest.write_bytes(content)
            file_count += 1

        logger.info("Downloaded {} files for skill '{}'", file_count, skill_name)
        return {"ok": True, "name": skill_name, "path": str(dest), "files": file_count}

    except Exception:
        # Cleanup on failure
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        raise


def _list_tree_recursive(
    owner: str, repo: str, ref: str, subpath: str
) -> list[dict]:
    """Recursively list all files under a GitHub directory.

    Returns list of dicts: {name, type, rel_path, download_url}
    """
    results: list[dict] = []
    _walk(owner, repo, ref, subpath, "", results)
    return results


def _walk(
    owner: str, repo: str, ref: str, base_path: str, rel_prefix: str,
    results: list[dict],
) -> None:
    """Walk GitHub directory tree recursively."""
    api_path = f"/repos/{owner}/{repo}/contents/{base_path}?ref={ref}" if base_path else f"/repos/{owner}/{repo}/contents?ref={ref}"

    items = _gh_api(api_path)
    if not isinstance(items, list):
        # Single file
        items = [items]

    for item in items:
        name = item["name"]
        item_type = item["type"]
        rel = f"{rel_prefix}{name}" if rel_prefix else name

        if item_type == "file":
            # Always use Contents API path — raw.githubusercontent.com is unreliable
            # for bulk downloads (EOF errors on sequential requests)
            api_dl = f"/repos/{owner}/{repo}/contents/{item['path']}?ref={ref}"
            results.append({
                "name": name,
                "type": "file",
                "rel_path": rel,
                "download_url": api_dl,
            })
        elif item_type == "dir":
            _walk(owner, repo, ref, item["path"], f"{rel}/", results)
