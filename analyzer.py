"""Copilot CLI call, JSON extraction, sidecar creation, and file move."""
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from categories import format_tree
from utils import sanitize_name

PROMPT_TEMPLATE = """\
You are a screenshot classifier. Read the image at: {image_path}

IMPORTANT: If the screenshot contains red boxes, red arrows, or red highlights, those
mark the most important content. Focus your classification and description on what
is highlighted.

Classify the screenshot using the category tree below. If a category fits, use it.
Only propose a new one when nothing in the tree fits.

EXISTING CATEGORIES:
{category_tree}

RULES:
1. Category names must be lowercase with hyphens, no spaces (e.g. "ai-tools", "social-media").
2. sub_category is JSON null — not the string "null" — when no subcategory applies.
3. Use "others" / null when the image is too cropped, too vague, ambiguous, or shows
   conflicting concepts with no clear dominant intent.
4. Write the description in English, even if the screenshot contains Japanese text.
5. Description: 2-3 sentences covering (a) the application or platform shown,
   (b) the key content visible, (c) what the red-highlighted area draws attention to
   (if any highlights are present).

OUTPUT: Respond with ONLY the JSON object on a single line.
No explanation. No code fences. No text before or after.

{{"main_category": "...", "sub_category": "...", "description": "..."}}"""


# Keep old name as alias so existing tests that import _sanitize_name still pass
_sanitize_name = sanitize_name


def _extract_json(text: str) -> dict | None:
    """Extract the first valid JSON object from LLM output."""
    # 1. Direct parse (ideal — prompt produced clean output)
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Strip markdown code fences then retry
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        pass

    # 3. Anchor-based extraction — immune to {placeholder} in description values
    m = re.search(r'(\{"main_category"\s*:.*\})', cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _unique_dest(directory: Path, filename: str) -> Path:
    """Return a non-colliding destination path, appending _1, _2, … as needed."""
    dest = directory / filename
    if not dest.exists():
        return dest
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    i = 1
    while True:
        dest = directory / f"{stem}_{i}{suffix}"
        if not dest.exists():
            return dest
        i += 1


def process_image(
    image_path: Path,
    config: dict,
    cats: dict,
    log: logging.Logger,
) -> dict | None:
    """Analyze one image via Copilot CLI, create sidecar, move image+sidecar.

    Returns a result dict on success, None on any failure (image stays in
    watch_dir and will be retried on the next run).
    """
    image_path = Path(image_path)
    output_dir = Path(config["output_dir"]).resolve()

    # ── 1. Build prompt ───────────────────────────────────────────────────────
    prompt = PROMPT_TEMPLATE.format(
        image_path=str(image_path),
        category_tree=format_tree(cats),
    )

    # ── 2. Call Copilot CLI ───────────────────────────────────────────────────
    cmd = [
        "node",
        config["copilot_loader"],
        "-p", prompt,
        "--allow-all-tools",
        "--allow-all-paths",
        "--output-format", "text",
        "--model", config["copilot_model"],
    ]
    try:
        with tempfile.TemporaryDirectory() as tmp_cwd:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=config.get("copilot_timeout", 60),
                creationflags=subprocess.CREATE_NO_WINDOW,
                cwd=tmp_cwd,
            )
    except subprocess.TimeoutExpired:
        log.warning("analyzer: timeout processing %s", image_path.name)
        return None

    if result.returncode != 0:
        log.error("analyzer: copilot returned %d for %s — %s",
                  result.returncode, image_path.name, result.stderr.strip())
        return None

    # ── 3. Extract and validate JSON ─────────────────────────────────────────
    parsed = _extract_json(result.stdout)
    if parsed is None:
        log.error("analyzer: could not extract JSON from copilot output for %s\nraw: %s",
                  image_path.name, result.stdout[:500])
        return None

    main_cat = sanitize_name(parsed.get("main_category") or "others")
    raw_sub = parsed.get("sub_category")
    sub_cat = sanitize_name(raw_sub) if raw_sub else None
    description = str(parsed.get("description", "")).strip()

    # ── 4. Determine target directory ─────────────────────────────────────────
    if main_cat == "others":
        target_dir = output_dir / "others"
        sub_cat = None
    elif sub_cat:
        target_dir = output_dir / main_cat / sub_cat
    else:
        target_dir = output_dir / main_cat

    target_dir.mkdir(parents=True, exist_ok=True)

    # ── 4b. Confinement check — defence in depth against path traversal ───────
    if not str(target_dir.resolve()).startswith(str(output_dir) + os.sep):
        log.error("analyzer: path traversal blocked — %s outside output_dir", target_dir)
        return None

    # ── 5. Resolve filename collisions ────────────────────────────────────────
    dest_image = _unique_dest(target_dir, image_path.name)
    dest_sidecar = _unique_dest(target_dir, image_path.stem + ".md")

    # ── 6. Move image ─────────────────────────────────────────────────────────
    # Move before writing the sidecar so a failed move leaves nothing behind.
    shutil.move(str(image_path), str(dest_image))

    # ── 7. Write sidecar .md ──────────────────────────────────────────────────
    sub_yaml = f'"{sub_cat}"' if sub_cat is not None else "null"
    sidecar_content = (
        f"---\n"
        f'source: "{image_path.name}"\n'
        f"analyzed_at: {datetime.now(timezone.utc).isoformat()}\n"
        f'main_category: "{main_cat}"\n'
        f"sub_category: {sub_yaml}\n"
        f'model: "{config["copilot_model"]}"\n'
        f"---\n\n"
        f"![{image_path.stem}]({image_path.name})\n\n"
        f"## Description\n\n"
        f"{description}\n"
    )
    dest_sidecar.write_text(sidecar_content, encoding="utf-8")

    log.info("analyzer: %s → %s/%s", image_path.name, main_cat,
             sub_cat or "(no sub)")

    return {
        "main_category": main_cat,
        "sub_category":  sub_cat,
        "dest_image":    dest_image,
        "dest_sidecar":  dest_sidecar,
    }
