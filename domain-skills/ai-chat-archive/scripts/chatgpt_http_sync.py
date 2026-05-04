"""Full ChatGPT archive sync via HTTP using extracted browser cookies.

No browser automation needed. Extracts cookies from a Chromium-based browser,
authenticates to ChatGPT's backend API, and stores everything in SQLite.

Usage:
    python3 domain-skills/ai-chat-archive/scripts/chatgpt_http_sync.py
    BROWSER=comet python3 domain-skills/ai-chat-archive/scripts/chatgpt_http_sync.py
    SYNC_LIMIT=5 python3 domain-skills/ai-chat-archive/scripts/chatgpt_http_sync.py
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.schema import init_db
from lib.archive_db import (
    connect, ensure_provider, ensure_account, upsert_thread, upsert_message,
    upsert_artifact, insert_capture, set_sync_state,
    compute_account_key, compute_content_hash,
    generate_run_id, generate_capture_id, new_run, finish_run,
    thread_last_capture, known_thread_keys,
)
from lib.cookie_extract import extract_cookies
from lib.chatgpt_http import ChatGPTHTTPAPI
from lib.render import render_thread_markdown

BROWSER = os.environ.get("BROWSER", "comet")
SYNC_LIMIT = int(os.environ.get("SYNC_LIMIT", "0"))  # 0 = all
DOMAIN_FILTER = os.environ.get("DOMAIN_FILTER", "chatgpt")

ARCHIVE_ROOT = Path(__file__).parent.parent / ".private-data" / "archive"
ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
db_path = ARCHIVE_ROOT / "archive.sqlite3"
if not db_path.exists():
    init_db(db_path)

conn = connect(db_path)
run_id = generate_run_id()
new_run(conn, run_id, {"script": "chatgpt_http_sync", "browser": BROWSER})

ensure_provider(conn, "chatgpt", "ChatGPT")

# Step 1: Extract cookies from browser
print(f"EXTRACT: cookies from {BROWSER}")
cookies_by_domain = extract_cookies(BROWSER, DOMAIN_FILTER)
total_cookies = sum(len(v) for v in cookies_by_domain.values())
print(f"COOKIES: {total_cookies} decrypted across {len(cookies_by_domain)} domains")

# Step 2: Authenticate
api = ChatGPTHTTPAPI(cookies_by_domain)
auth = api.authenticate()
if not auth.get("authenticated"):
    print(f"AUTH_FAILED: {auth.get('error')}")
    finish_run(conn, run_id, "blocked", {"reason": "auth_failed"})
    conn.close()
    sys.exit(1)

account_label = auth.get("email") or auth.get("name") or "unknown"
account_key = compute_account_key("chatgpt", account_label)
ensure_account(conn, "chatgpt", account_key, account_label)
print(f"ACCOUNT: {account_label}")

# Step 3: Inventory
all_convs = api.all_conversations()
print(f"INVENTORY: {len(all_convs)} conversations")

now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
existing = known_thread_keys(conn, "chatgpt", account_key)

for conv in all_convs:
    thread_key = conv["id"]  # ChatGPT IDs are stable, used directly
    upsert_thread(conn, {
        "thread_key": thread_key,
        "provider_id": "chatgpt",
        "account_key": account_key,
        "provider_thread_id": conv["id"],
        "canonical_url": f"https://chatgpt.com/c/{conv['id']}",
        "title": conv.get("title", ""),
        "status": "listed",
        "first_observed_at": now,
        "last_observed_at": now,
    })

# Step 4: Select candidates
candidates = []
for conv in all_convs:
    thread_key = conv["id"]

    if thread_key not in existing:
        candidates.append(conv)
        continue

    last = thread_last_capture(conn, thread_key)
    if last is None:
        candidates.append(conv)
        continue
    if last["completion_state"] in ("partial", "blocked"):
        candidates.append(conv)
        continue

    conv_update = conv.get("update_time")
    if conv_update:
        import datetime
        try:
            conv_dt = datetime.datetime.fromisoformat(conv_update.replace("Z", "+00:00"))
            cap_dt = datetime.datetime.fromisoformat(last["captured_at"].replace("Z", "+00:00"))
            if conv_dt > cap_dt:
                candidates.append(conv)
        except (ValueError, TypeError):
            pass

if SYNC_LIMIT > 0:
    candidates = candidates[:SYNC_LIMIT]

print(f"CANDIDATES: {len(candidates)} threads to capture")

# Step 5: Capture each candidate
captured = 0
skipped = 0
failed = 0

for conv in candidates:
    thread_key = conv["id"]
    title = conv.get("title", "")[:60]

    try:
        detail = api.conversation_detail(conv["id"])
        if not detail:
            failed += 1
            print(f"  FAILED: {title} — no API data")
            continue

        messages = ChatGPTHTTPAPI.extract_messages_from_mapping(detail)
        conv_title = detail.get("title", "") or conv.get("title", "Untitled")
        artifacts = ChatGPTHTTPAPI.extract_artifacts_from_mapping(detail)

        structured = {
            "title": conv_title,
            "canonical_url": f"https://chatgpt.com/c/{conv['id']}",
            "messages": messages,
            "artifacts": artifacts,
            "citations": [],
        }

        markdown = render_thread_markdown(structured)
        content_hash = compute_content_hash(markdown)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        last = thread_last_capture(conn, thread_key)
        if last and last.get("content_hash") == content_hash:
            upsert_thread(conn, {
                "thread_key": thread_key, "provider_id": "chatgpt",
                "account_key": account_key, "status": "unchanged",
                "last_observed_at": now,
            })
            skipped += 1
            print(f"  UNCHANGED: {title}")
            continue

        capture_id = generate_capture_id()
        insert_capture(conn, {
            "capture_id": capture_id,
            "run_id": run_id,
            "thread_key": thread_key,
            "captured_at": now,
            "source_context": json.dumps({
                "method": "http-api",
                "url": f"https://chatgpt.com/backend-api/conversation/{conv['id']}",
                "browser": BROWSER,
            }),
            "completion_state": "complete",
            "normalized_json": json.dumps(structured, ensure_ascii=False),
            "rendered_markdown": markdown,
            "content_hash": content_hash,
            "previous_capture_id": last["capture_id"] if last else None,
        })

        artifact_types = sorted(set(a["artifact_type"] for a in artifacts))
        upsert_thread(conn, {
            "thread_key": thread_key,
            "provider_id": "chatgpt",
            "account_key": account_key,
            "provider_thread_id": conv["id"],
            "canonical_url": f"https://chatgpt.com/c/{conv['id']}",
            "title": conv_title,
            "status": "complete",
            "content_hash": content_hash,
            "artifact_count": len(artifacts),
            "last_observed_at": now,
            "capture_id": capture_id,
        })

        for msg in messages:
            upsert_message(conn, {
                "thread_key": thread_key,
                "role": msg["role"],
                "ordinal": msg["ordinal"],
                "current_content": msg["content"],
                "capture_id": capture_id,
                "provider_message_id": msg.get("provider_message_id"),
            }, run_id=run_id, provider_id="chatgpt", account_key=account_key)

        for art in artifacts:
            upsert_artifact(conn, {
                "thread_key": thread_key,
                "artifact_type": art["artifact_type"],
                "label": art.get("label", ""),
                "provider_artifact_id": art.get("provider_artifact_id"),
                "storage_kind": "metadata",
                "capture_id": capture_id,
            }, run_id=run_id, provider_id="chatgpt", account_key=account_key)

        art_summary = f", {len(artifacts)} artifacts" if artifacts else ""
        captured += 1
        print(f"  CAPTURED: {title} ({len(messages)} msgs{art_summary})")
        time.sleep(0.5)

    except Exception as e:
        failed += 1
        print(f"  FAILED: {title} — {e}")

set_sync_state(conn, "chatgpt", account_key, "last_sync", now, {
    "candidates": len(candidates),
    "captured": captured,
    "skipped": skipped,
    "failed": failed,
})

finish_run(conn, run_id, "complete" if failed == 0 else "partial", {
    "inventory": len(all_convs),
    "candidates": len(candidates),
    "captured": captured,
    "skipped": skipped,
    "failed": failed,
})
conn.close()

print(f"\nSYNC_COMPLETE: captured={captured} skipped={skipped} failed={failed}")
