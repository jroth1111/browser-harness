"""Browser-based artifact content capture for HTTP-synced ChatGPT threads.

Reads threads from SQLite that have metadata-only artifacts, opens each in the
browser, and captures the actual content (deep research reports, canvas docs,
generated images, agent reports).

Usage via browser-harness:
    browser-harness <<'PY'
    exec(open("domain-skills/ai-chat-archive/scripts/chatgpt_artifact_capture.py").read())
    PY

Usage with stealth browser (bypasses Cloudflare Turnstile):
    STEALTH_CAPTURE=1 python3 domain-skills/ai-chat-archive/scripts/chatgpt_artifact_capture.py

Env vars:
    ARTIFACT_THREADS=id1,id2,...   Specific thread keys (default: auto-detect)
    ARTIFACT_TYPES=deep_research_report,canvas_document  Filter by type
    ARTIFACT_LIMIT=5               Max threads to process (0 = all)
    STEALTH_CAPTURE=1              Use Patchright stealth browser instead of CDP
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.schema import init_db
from lib.archive_db import (
    connect, upsert_artifact, store_artifact_blob, upsert_citation,
    compute_content_hash, generate_run_id, generate_capture_id,
    new_run, finish_run,
)

STEALTH_CAPTURE = os.environ.get("STEALTH_CAPTURE", "")
from lib.chatgpt_dom import ChatGPTDOMExtractor
from lib.chatgpt_deep_research import DeepResearchCapture
from lib.render import render_thread_markdown

ARCHIVE_ROOT = Path(__file__).parent.parent / ".private-data" / "archive"
conn = connect(ARCHIVE_ROOT / "archive.sqlite3")

run_id = generate_run_id()
new_run(conn, run_id, {"script": "chatgpt_artifact_capture"})

# --- Discover threads needing artifact capture ---

thread_filter = os.environ.get("ARTIFACT_THREADS", "")
type_filter = os.environ.get("ARTIFACT_TYPES", "")
limit = int(os.environ.get("ARTIFACT_LIMIT", "0"))

if thread_filter:
    thread_keys = [t.strip() for t in thread_filter.split(",") if t.strip()]
    rows = conn.execute(
        "SELECT DISTINCT a.thread_key, a.artifact_type, a.artifact_key, "
        "t.canonical_url, t.title "
        "FROM artifacts a JOIN threads t ON a.thread_key = t.thread_key "
        "WHERE a.thread_key IN ({}) AND a.storage_kind = 'metadata' "
        "AND a.deleted_at IS NULL".format(",".join("?" * len(thread_keys))),
        thread_keys,
    ).fetchall()
else:
    query = (
        "SELECT DISTINCT a.thread_key, a.artifact_type, a.artifact_key, "
        "t.canonical_url, t.title "
        "FROM artifacts a JOIN threads t ON a.thread_key = t.thread_key "
        "WHERE a.storage_kind = 'metadata' AND a.deleted_at IS NULL"
    )
    params = []
    if type_filter:
        types = [t.strip() for t in type_filter.split(",")]
        placeholders = ",".join("?" * len(types))
        query += f" AND a.artifact_type IN ({placeholders})"
        params = types
    query += " ORDER BY t.title"
    rows = conn.fetchall() if False else conn.execute(query, params).fetchall()

# Group by thread
threads_by_key: dict[str, dict] = {}
for row in rows:
    tk = row["thread_key"]
    if tk not in threads_by_key:
        threads_by_key[tk] = {
            "url": row["canonical_url"],
            "title": row["title"],
            "artifact_types": set(),
            "artifact_keys": [],
        }
    threads_by_key[tk]["artifact_types"].add(row["artifact_type"])
    threads_by_key[tk]["artifact_keys"].append(row["artifact_key"])

thread_list = list(threads_by_key.items())
if limit > 0:
    thread_list = thread_list[:limit]

print(f"ARTIFACT_CAPTURE: {len(thread_list)} threads with metadata-only artifacts")

if not thread_list:
    finish_run(conn, run_id, "complete", {"threads": 0})
    conn.close()
    print("NOTHING_TO_DO")
    sys.exit(0)

# --- Browser helpers ---

captured_artifacts = 0
failed_artifacts = 0

if STEALTH_CAPTURE == "1":
    from stealth_helpers import stealth_session

    stealth = stealth_session(headless=False)

    for tk, info in thread_list:
        url = info["url"]
        title = (info["title"] or tk)[:60]
        art_types = info["artifact_types"]

        print(f"\nTHREAD: {title}")
        print(f"  URL: {url}")
        print(f"  TYPES: {', '.join(sorted(art_types))}")

        stealth.goto(url)
        time.sleep(4)

        try:
            # --- Generated image capture ---
            if "generated_image" in art_types:
                images = stealth.js("""(() => {
                    const results = [];
                    document.querySelectorAll('img[src]').forEach(el => {
                        const src = el.src || '';
                        const alt = el.alt || '';
                        if (src.includes('dall') || src.includes('oaidalle') ||
                            src.includes('generation') || alt.toLowerCase().includes('generated')) {
                            results.push({src, alt, width: el.naturalWidth, height: el.naturalHeight});
                        }
                    });
                    return results;
                })()""") or []

                for img in images:
                    src = img.get("src", "")
                    if src:
                        try:
                            data = stealth.page.evaluate(f"""
                                (async () => {{
                                    try {{
                                        const resp = await fetch("{src}", {{credentials: "include"}});
                                        const buf = await resp.arrayBuffer();
                                        return Array.from(new Uint8Array(buf));
                                    }} catch(e) {{ return null; }}
                                }})()
                            """)
                            if data:
                                data = bytes(data)
                                content_hash = compute_content_hash(data)
                                capture_id = generate_capture_id()
                                art_key = upsert_artifact(conn, {
                                    "thread_key": tk,
                                    "label": img.get("alt", "Generated Image"),
                                    "artifact_type": "generated_image",
                                    "capture_id": capture_id,
                                    "content_hash": content_hash,
                                    "storage_kind": "binary",
                                    "byte_length": len(data),
                                }, run_id=run_id, provider_id="chatgpt", account_key="")
                                store_artifact_blob(conn, art_key, content_hash, data)
                                captured_artifacts += 1
                                print(f"  IMAGE: {len(data) // 1024}KB captured")
                            else:
                                failed_artifacts += 1
                                print(f"  IMAGE: download failed")
                        except Exception as e:
                            failed_artifacts += 1
                            print(f"  IMAGE: error — {e}")

        except Exception as e:
            print(f"  ERROR: {e}")

        time.sleep(1)

    stealth.close()

else:
    # --- Standard browser-harness CDP path ---
    dom = ChatGPTDOMExtractor(js, ax_snapshot, click_ref, scroll)
    dr_capture = DeepResearchCapture(js, ax_snapshot, click_ref)

    for tk, info in thread_list:
        url = info["url"]
        title = (info["title"] or tk)[:60]
        art_types = info["artifact_types"]

        print(f"\nTHREAD: {title}")
        print(f"  URL: {url}")
        print(f"  TYPES: {', '.join(sorted(art_types))}")

        tid = new_tab(url)
        wait_for_load_js(10)
        time.sleep(4)

        try:
            # Scroll to load everything
            dom.scroll_to_load_all()
            dom.expand_all_show_more()
            time.sleep(1)

        # --- Deep research report capture ---
        if "deep_research_report" in art_types:
            dr_result = dr_capture.full_research_capture()
            report = dr_result.get("report")

            if report and report.get("report_text"):
                report_text = report["report_text"]
                report_hash = compute_content_hash(report_text)
                capture_id = generate_capture_id()

                art_key = upsert_artifact(conn, {
                    "thread_key": tk,
                    "label": "Deep Research Report",
                    "artifact_type": "deep_research_report",
                    "capture_id": capture_id,
                    "content_hash": report_hash,
                    "storage_kind": "text",
                    "byte_length": len(report_text.encode("utf-8")),
                }, run_id=run_id, provider_id="chatgpt", account_key="")
                store_artifact_blob(conn, art_key, report_hash, report_text.encode("utf-8"))
                captured_artifacts += 1
                words = len(report_text.split())
                print(f"  DR_REPORT: {words} words captured")
            else:
                failed_artifacts += 1
                print(f"  DR_REPORT: no report text found")

            # Store deep research citations
            for cit in dr_result.get("citations", []):
                upsert_citation(conn, {
                    "thread_key": tk,
                    "capture_id": generate_capture_id(),
                    "label": cit.get("label", ""),
                    "url": cit.get("url", ""),
                    "source_json": {"source": "deep_research"},
                })

        # --- Canvas document capture ---
        if "canvas_document" in art_types:
            canvas_data = js(r"""
            (() => {
                const results = [];
                // Canvas elements and iframes
                document.querySelectorAll(
                    'iframe[src*="canvas"], [data-testid*="canvas"], [class*="canvas"]'
                ).forEach(el => {
                    results.push({
                        tag: el.tagName,
                        src: el.src || el.getAttribute('src') || '',
                        text: (el.textContent || '').slice(0, 500),
                        testid: el.getAttribute('data-testid') || '',
                    });
                });
                return results;
            })()
            """) or []

            if canvas_data:
                for cv in canvas_data:
                    text = cv.get("text", "")
                    if text and len(text) > 50:
                        capture_id = generate_capture_id()
                        content_hash = compute_content_hash(text)
                        art_key = upsert_artifact(conn, {
                            "thread_key": tk,
                            "label": f"Canvas: {cv.get('testid', 'document')}",
                            "artifact_type": "canvas_document",
                            "capture_id": capture_id,
                            "content_hash": content_hash,
                            "storage_kind": "text",
                            "byte_length": len(text.encode("utf-8")),
                        }, run_id=run_id, provider_id="chatgpt", account_key="")
                        store_artifact_blob(conn, art_key, content_hash, text.encode("utf-8"))
                        captured_artifacts += 1
                        print(f"  CANVAS: {len(text)} chars captured")
                    else:
                        failed_artifacts += 1
                        print(f"  CANVAS: no text content found")
            else:
                failed_artifacts += 1
                print(f"  CANVAS: no canvas elements found")

        # --- Generated image capture ---
        if "generated_image" in art_types:
            images = js(r"""
            (() => {
                const results = [];
                document.querySelectorAll('img[src]').forEach(el => {
                    const src = el.src || '';
                    const alt = el.alt || '';
                    // DALL-E images typically have specific src patterns
                    if (src.includes('dall') || src.includes('oaidalle') ||
                        src.includes('generation') || alt.toLowerCase().includes('generated')) {
                        results.push({
                            src: src,
                            alt: alt,
                            width: el.naturalWidth,
                            height: el.naturalHeight,
                        });
                    }
                });
                return results;
            })()
            """) or []

            if images:
                for img in images:
                    src = img.get("src", "")
                    if src:
                        try:
                            # Download the image via the browser
                            blob = js(f"""
                            (async () => {{
                                try {{
                                    const resp = await fetch("{src}", {{credentials: "include"}});
                                    const buf = await resp.arrayBuffer();
                                    return Array.from(new Uint8Array(buf));
                                }} catch(e) {{
                                    return null;
                                }}
                            }})()
                            """)
                            if blob:
                                data = bytes(blob)
                                content_hash = compute_content_hash(data)
                                capture_id = generate_capture_id()
                                art_key = upsert_artifact(conn, {
                                    "thread_key": tk,
                                    "label": img.get("alt", "Generated Image"),
                                    "artifact_type": "generated_image",
                                    "capture_id": capture_id,
                                    "content_hash": content_hash,
                                    "storage_kind": "binary",
                                    "byte_length": len(data),
                                }, run_id=run_id, provider_id="chatgpt", account_key="")
                                store_artifact_blob(conn, art_key, content_hash, data)
                                captured_artifacts += 1
                                size_kb = len(data) // 1024
                                print(f"  IMAGE: {size_kb}KB captured")
                            else:
                                failed_artifacts += 1
                                print(f"  IMAGE: download failed")
                        except Exception as e:
                            failed_artifacts += 1
                            print(f"  IMAGE: error — {e}")
            else:
                failed_artifacts += 1
                print(f"  IMAGE: no generated images found")

        # --- Agent report capture ---
        if "agent_report" in art_types:
            agent_data = js(r"""
            (() => {
                const results = [];
                document.querySelectorAll(
                    '[data-testid*="agent"], [data-testid*="operator"], ' +
                    '[class*="agent"], [class*="operator"]'
                ).forEach(el => {
                    results.push({
                        text: (el.textContent || '').slice(0, 500),
                        tag: el.tagName,
                        testid: el.getAttribute('data-testid') || '',
                    });
                });
                return results;
            })()
            """) or []

            if agent_data:
                for ag in agent_data:
                    text = ag.get("text", "")
                    if text and len(text) > 100:
                        capture_id = generate_capture_id()
                        content_hash = compute_content_hash(text)
                        art_key = upsert_artifact(conn, {
                            "thread_key": tk,
                            "label": f"Agent Report: {ag.get('testid', 'report')}",
                            "artifact_type": "agent_report",
                            "capture_id": capture_id,
                            "content_hash": content_hash,
                            "storage_kind": "text",
                            "byte_length": len(text.encode("utf-8")),
                        }, run_id=run_id, provider_id="chatgpt", account_key="")
                        store_artifact_blob(conn, art_key, content_hash, text.encode("utf-8"))
                        captured_artifacts += 1
                        print(f"  AGENT: {len(text)} chars captured")
            else:
                failed_artifacts += 1
                print(f"  AGENT: no agent content found")

        # --- Generated file capture ---
        if "generated_file" in art_types:
            files = dom.extract_artifacts_from_page()
            file_arts = [f for f in files if f.get("artifact_type") in ("file", "download")]
            for f in file_arts:
                src = f.get("source_url", "")
                if src and f.get("action_available"):
                    try:
                        blob = js(f"""
                        (async () => {{
                            try {{
                                const resp = await fetch("{src}", {{credentials: "include"}});
                                const buf = await resp.arrayBuffer();
                                return Array.from(new Uint8Array(buf));
                            }} catch(e) {{
                                return null;
                            }}
                        }})()
                        """)
                        if blob:
                            data = bytes(blob)
                            content_hash = compute_content_hash(data)
                            capture_id = generate_capture_id()
                            art_key = upsert_artifact(conn, {
                                "thread_key": tk,
                                "label": f.get("label", "Generated File"),
                                "artifact_type": "generated_file",
                                "source_url": src,
                                "capture_id": capture_id,
                                "content_hash": content_hash,
                                "storage_kind": "binary",
                                "byte_length": len(data),
                            }, run_id=run_id, provider_id="chatgpt", account_key="")
                            store_artifact_blob(conn, art_key, content_hash, data)
                            captured_artifacts += 1
                            size_kb = len(data) // 1024
                            print(f"  FILE: {f.get('label')} ({size_kb}KB)")
                    except Exception as e:
                        failed_artifacts += 1
                        print(f"  FILE: {f.get('label')} — {e}")

        except Exception as e:
            print(f"  ERROR: {e}")

        close_tab(tid)
        time.sleep(1)

finish_run(conn, run_id, "complete" if failed_artifacts == 0 else "partial", {
    "threads": len(thread_list),
    "captured_artifacts": captured_artifacts,
    "failed_artifacts": failed_artifacts,
})
conn.close()

print(f"\nARTIFACT_CAPTURE_COMPLETE: captured={captured_artifacts} failed={failed_artifacts}")
