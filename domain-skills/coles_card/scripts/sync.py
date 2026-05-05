#!/usr/bin/env python3
"""Sync visible Coles credit card balances and transactions to SQLite.

This script intentionally uses the official browser login flow through
browser-harness. It never reads credentials, cookies, localStorage,
sessionStorage, or auth tokens.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DEFAULT_START_URL = "https://secure.coles.com.au/login"
DEFAULT_DB = (
    Path("domain-skills")
    / "coles_card"
    / ".private-data"
    / "coles_card.sqlite3"
)
RESULT_MARKER = "__COLES_CARD_RESULT__"
SENSITIVE_QUERY_KEYS = {
    "access_token",
    "client_assertion",
    "code",
    "code_challenge",
    "id_token",
    "nonce",
    "refresh_token",
    "session",
    "state",
    "token",
    "x-state",
}


BROWSER_PROBE = r'''
import json
import re
import time

START_URL = __START_URL__
INTERACTIVE_LOGIN = __INTERACTIVE_LOGIN__
LOGIN_TIMEOUT = __LOGIN_TIMEOUT__
USE_CURRENT_TAB = __USE_CURRENT_TAB__

def _all_text_payload():
    return js(r"""
(() => {
  function roots() {
    const out = [document];
    const seen = new Set(out);
    for (let i = 0; i < out.length; i++) {
      const root = out[i];
      const nodes = root.querySelectorAll ? root.querySelectorAll("*") : [];
      for (const node of nodes) {
        if (node.shadowRoot && !seen.has(node.shadowRoot)) {
          seen.add(node.shadowRoot);
          out.push(node.shadowRoot);
        }
      }
    }
    return out;
  }
	  function rawText(el) {
	    const target = el && el.nodeType === Node.DOCUMENT_NODE ? (el.body || el.documentElement) : el;
	    return (target && (target.innerText || target.textContent)) || "";
	  }
	  function text(el) {
	    return rawText(el).replace(/\s+/g, " ").trim();
	  }
  function linesFromText(s) {
    return String(s || "")
      .split(/\n|(?<=\d{2})\s{2,}/)
      .map(x => x.replace(/\s+/g, " ").trim())
      .filter(Boolean);
  }
  const allRoots = roots();
	  const rootText = allRoots.map(r => rawText(r)).join("\n");
	  const lines = linesFromText(rootText);
	  const moneySource = String.raw`(?:[-−+]\s*)?\$ ?\d[\d,]*(?:\.\d{2})?|\$ ?[-−+]?\d[\d,]*(?:\.\d{2})?|\(\$ ?\d[\d,]*(?:\.\d{2})?\)`;
	  const moneyRe = new RegExp(moneySource, "g");
  const dateRe = /\b(?:\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4}|\d{1,2}\s+(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{2,4})\b/i;
  const balanceMatchers = [
    ["current_balance", /current balance/i],
    ["available_credit", /available credit/i],
    ["credit_limit", /credit limit/i],
    ["minimum_payment", /minimum payment/i],
    ["payment_due", /payment due/i],
    ["closing_balance", /closing balance/i]
  ];
  const balances = [];
  for (let i = 0; i < lines.length; i++) {
    for (const [kind, rx] of balanceMatchers) {
	      if (!rx.test(lines[i])) continue;
	      const windowText = lines.slice(i, i + 3).join(" ");
	      const direct = windowText.match(new RegExp(rx.source + String.raw`\s*(` + moneySource + `)`, "i"));
	      const money = direct ? [direct[1]] : windowText.match(moneyRe);
	      if (money && money.length) {
	        balances.push({
          balance_type: kind,
          label: lines[i],
          amount_text: money[0],
          currency: "AUD",
          raw_text: windowText.slice(0, 500)
        });
      }
    }
  }
	  const elements = [];
	  function nearbyDate(el) {
	    let node = el;
	    while (node) {
	      let sib = node.previousElementSibling;
	      while (sib) {
	        const found = text(sib).match(dateRe);
	        if (found) return found[0];
	        sib = sib.previousElementSibling;
	      }
	      node = node.parentElement || (node.getRootNode && node.getRootNode().host);
	    }
	    return null;
	  }
	  for (const root of allRoots) {
	    if (!root.querySelectorAll) continue;
	    for (const el of root.querySelectorAll("tr,[role='row'],li,div")) {
	      if (el.tagName !== "LI" && el.querySelector && el.querySelector("li")) continue;
	      const rowText = text(el);
	      if (rowText.length < 16 || rowText.length > 500) continue;
	      moneyRe.lastIndex = 0;
	      const date = (rowText.match(dateRe) || [nearbyDate(el)])[0];
	      if (!date || !moneyRe.test(rowText)) {
	        moneyRe.lastIndex = 0;
	        continue;
	      }
	      moneyRe.lastIndex = 0;
	      if (/current balance|available credit|credit limit|minimum payment|payment due/i.test(rowText)) continue;
	      elements.push(dateRe.test(rowText) ? rowText : date + " " + rowText);
	    }
	  }
	  const seenRows = new Set();
	  const transactions = [];
	  let currentDate = null;
	  for (const line of lines) {
	    const date = (line.match(dateRe) || [null])[0];
	    if (date) currentDate = date;
	    if (!moneyRe.test(line)) {
	      moneyRe.lastIndex = 0;
	      continue;
	    }
	    moneyRe.lastIndex = 0;
	    if (/current balance|available balance|available credit|credit limit|minimum payment|payment due/i.test(line)) continue;
	    const rowText = date ? line : (currentDate ? currentDate + " " + line : line);
	    elements.push(rowText);
	  }
	  for (const rowText of elements) {
    const compact = rowText.replace(/\s+/g, " ").trim();
    if (seenRows.has(compact)) continue;
    seenRows.add(compact);
    const date = (compact.match(dateRe) || [null])[0];
    const monies = compact.match(moneyRe) || [];
    if (!date || !monies.length) continue;
    const amountText = monies[monies.length - 1];
    const runningBalanceText = monies.length > 1 ? monies[0] : null;
    let description = compact
      .replace(date, " ")
      .replace(moneyRe, " ")
      .replace(/\bPending\b|\bTransaction date\b|\bAmount\b|\bDescription\b/ig, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (!description || description.length < 2) description = compact.slice(0, 160);
    transactions.push({
      posted_date_text: date,
      description,
      amount_text: amountText,
      running_balance_text: runningBalanceText,
      currency: "AUD",
      raw_text: compact
    });
  }
  let accountLabel = "";
  for (const line of lines) {
    if (/coles/i.test(line) && /(card|account)/i.test(line) && /\d{2,4}/.test(line)) {
      accountLabel = line.slice(0, 160);
      break;
    }
  }
  if (!accountLabel) accountLabel = document.title || location.host;
  return {
    url: location.href,
    title: document.title,
    body_excerpt: rootText.slice(0, 1200),
    account_label: accountLabel,
    balances,
    transactions: transactions.slice(0, 300)
  };
})()
""")

def _is_auth_surface(payload):
    text = (payload.get("body_excerpt") or "") + " " + (payload.get("title") or "") + " " + (payload.get("url") or "")
    return bool(re.search(r"id\.colesgroupprofile|auth\.colesgroupprofile|secure\.coles\.com\.au/login|Login - Coles Credit Cards|Log in with your Coles account|Log in or create account|Email Password|Your old credit card login|Complete application", text, re.I))

def _click_authorize_button():
    return js(r"""
(() => {
  function roots() {
    const out = [document];
    const seen = new Set(out);
    for (let i = 0; i < out.length; i++) {
      const root = out[i];
      const nodes = root.querySelectorAll ? root.querySelectorAll("*") : [];
      for (const node of nodes) {
        if (node.shadowRoot && !seen.has(node.shadowRoot)) {
          seen.add(node.shadowRoot);
          out.push(node.shadowRoot);
        }
      }
    }
    return out;
  }
  for (const root of roots()) {
    const buttons = root.querySelectorAll ? root.querySelectorAll("button,a") : [];
    for (const btn of buttons) {
      const txt = (btn.innerText || btn.textContent || "").replace(/\s+/g, " ").trim();
      if (/^Log in with your Coles account$/i.test(txt)) {
        btn.click();
        return {clicked: true, text: txt};
      }
    }
  }
  return {clicked: false};
})()
""")

def _click_transactions():
    return js(r"""
(() => {
  function roots() {
    const out = [document];
    const seen = new Set(out);
    for (let i = 0; i < out.length; i++) {
      const root = out[i];
      const nodes = root.querySelectorAll ? root.querySelectorAll("*") : [];
      for (const node of nodes) {
        if (node.shadowRoot && !seen.has(node.shadowRoot)) {
          seen.add(node.shadowRoot);
          out.push(node.shadowRoot);
        }
      }
    }
    return out;
  }
  const candidates = [];
  for (const root of roots()) {
    const controls = root.querySelectorAll ? root.querySelectorAll("a,button,[role='button'],[role='tab']") : [];
    for (const el of controls) {
      const txt = (el.innerText || el.textContent || el.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
      if (!txt || /dispute/i.test(txt)) continue;
      if (/^transactions?$/i.test(txt) || /\btransactions?\b/i.test(txt)) {
        candidates.push({el, score: /^transactions?$/i.test(txt) ? 0 : 1, text: txt});
      }
    }
  }
  candidates.sort((a, b) => a.score - b.score);
  if (!candidates.length) return {clicked: false};
  candidates[0].el.click();
  return {clicked: true, text: candidates[0].text};
})()
""")

def _result(status, **extra):
    payload = {"status": status, **extra}
    print("__COLES_CARD_RESULT__" + json.dumps(payload, ensure_ascii=False, sort_keys=True))

try:
    if USE_CURRENT_TAB:
        tabs = list_tabs(include_chrome=False)
        target = next((tab for tab in tabs if "secure.coles.com.au/home" in (tab.get("url") or "")), None)
        if not target:
            target = next((tab for tab in tabs if "secure.coles.com.au" in (tab.get("url") or "")), None)
        if not target:
            target = next((tab for tab in tabs if "colesgroupprofile.com.au" in (tab.get("url") or "")), None)
        if target:
            switch_tab(target)
        else:
            new_tab(START_URL)
    else:
        new_tab(START_URL)
    wait_for_load()
    time.sleep(4)
    initial = _all_text_payload()
    if _is_auth_surface(initial):
        if not INTERACTIVE_LOGIN:
            _result("blocked", reason="not_logged_in", page=initial)
            raise SystemExit(0)
        _click_authorize_button()
        deadline = time.time() + LOGIN_TIMEOUT
        while time.time() < deadline:
            time.sleep(3)
            payload = _all_text_payload()
            if not _is_auth_surface(payload):
                break
        else:
            _result("blocked", reason="login_timeout", page=_all_text_payload())
            raise SystemExit(0)
    dashboard = _all_text_payload()
    tx_click = _click_transactions()
    if tx_click.get("clicked"):
        time.sleep(4)
    tx_page = _all_text_payload()
    balances = dashboard.get("balances") or tx_page.get("balances") or []
    transactions = tx_page.get("transactions") or dashboard.get("transactions") or []
    if _is_auth_surface(tx_page) and not balances and not transactions:
        _result("blocked", reason="still_on_login", page=tx_page)
        raise SystemExit(0)
    _result(
        "ok",
        url=tx_page.get("url") or dashboard.get("url"),
        account_label=dashboard.get("account_label") or tx_page.get("account_label"),
        balances=balances,
        transactions=transactions,
        extraction={
            "dashboard_url": dashboard.get("url"),
            "transactions_url": tx_page.get("url"),
            "transactions_click": tx_click,
            "balance_count": len(balances),
            "transaction_count": len(transactions),
        },
    )
except SystemExit:
    raise
except Exception as exc:
    _result("error", reason=str(exc), page=_all_text_payload() if 'js' in globals() else {})
'''


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def redact_text(value: str) -> str:
    value = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[redacted-email]", value, flags=re.I)
    return re.sub(r"\b[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[redacted-jwt]", value)


def sanitize_url(value: str | None) -> str | None:
    if not value:
        return value
    try:
        parts = urlsplit(value)
    except ValueError:
        return redact_text(value)
    query = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in SENSITIVE_QUERY_KEYS:
            query.append((key, "[redacted]"))
        else:
            query.append((key, redact_text(val)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def sanitize_payload(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {k: sanitize_payload(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_payload(item, key) for item in value]
    if isinstance(value, str):
        if key.lower().endswith("url") or value.startswith(("http://", "https://")):
            return sanitize_url(value)
        return redact_text(value)
    return value


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sync_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            source_url TEXT,
            account_key TEXT,
            summary_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS accounts (
            account_key TEXT PRIMARY KEY,
            account_label TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            source_context_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS balance_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES sync_runs(run_id),
            account_key TEXT NOT NULL REFERENCES accounts(account_key),
            observed_at TEXT NOT NULL,
            balance_type TEXT NOT NULL,
            raw_label TEXT,
            amount_cents INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'AUD',
            source_url TEXT,
            raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS transactions (
            transaction_key TEXT PRIMARY KEY,
            account_key TEXT NOT NULL REFERENCES accounts(account_key),
            posted_date TEXT,
            description TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'AUD',
            running_balance_cents INTEGER,
            source_url TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_run_id TEXT NOT NULL REFERENCES sync_runs(run_id),
            raw_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_transactions_seen
            ON transactions(account_key, posted_date, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_balance_snapshots_run
            ON balance_snapshots(run_id, account_key, balance_type);
        """
    )
    return conn


def parse_money_to_cents(value: str | None) -> int | None:
    if not value:
        return None
    text = value.strip()
    negative = text.startswith(("-", "−", "(")) or "$ -" in text or "$-" in text or "$ −" in text or "$−" in text
    cleaned = re.sub(r"[^0-9.]", "", text)
    if not cleaned:
        return None
    dollars, _, cents = cleaned.partition(".")
    cents = (cents + "00")[:2]
    amount = int(dollars or "0") * 100 + int(cents)
    return -amount if negative else amount


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value.strip())
    month_map = {
        "jan": "01", "january": "01",
        "feb": "02", "february": "02",
        "mar": "03", "march": "03",
        "apr": "04", "april": "04",
        "may": "05",
        "jun": "06", "june": "06",
        "jul": "07", "july": "07",
        "aug": "08", "august": "08",
        "sep": "09", "sept": "09", "september": "09",
        "oct": "10", "october": "10",
        "nov": "11", "november": "11",
        "dec": "12", "december": "12",
    }
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", text)
    if m:
        day, month, year = m.groups()
        if len(year) == 2:
            year = "20" + year
        return f"{year.zfill(4)}-{month.zfill(2)}-{day.zfill(2)}"
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{2,4})$", text)
    if m:
        day, month_name, year = m.groups()
        month = month_map.get(month_name.lower())
        if month:
            if len(year) == 2:
                year = "20" + year
            return f"{year.zfill(4)}-{month}-{day.zfill(2)}"
    return text


def stable_hash(*parts: Any, length: int = 24) -> str:
    raw = "\x1f".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def account_key(account_label: str) -> str:
    return "coles_card:" + stable_hash(account_label, length=16)


def transaction_key(account: str, tx: dict[str, Any]) -> str:
    amount = parse_money_to_cents(tx.get("amount_text")) or 0
    posted = normalize_date(tx.get("posted_date_text"))
    description = re.sub(r"\s+", " ", tx.get("description") or "").strip().lower()
    return stable_hash(account, posted, amount, description, length=32)


def insert_run(conn: sqlite3.Connection, run_id: str, status: str = "running") -> None:
    conn.execute(
        "INSERT INTO sync_runs(run_id, started_at, status) VALUES (?, ?, ?)",
        (run_id, utc_now(), status),
    )
    conn.commit()


def finish_run(
    conn: sqlite3.Connection,
    run_id: str,
    status: str,
    summary: dict[str, Any],
    source_url: str | None = None,
    acct_key: str | None = None,
) -> None:
    conn.execute(
        """UPDATE sync_runs
           SET finished_at=?, status=?, source_url=?, account_key=?, summary_json=?
           WHERE run_id=?""",
        (utc_now(), status, source_url, acct_key, json.dumps(summary, sort_keys=True), run_id),
    )
    conn.commit()


def upsert_payload(conn: sqlite3.Connection, run_id: str, payload: dict[str, Any]) -> dict[str, int | str]:
    now = utc_now()
    label = (payload.get("account_label") or "Coles Credit Card").strip()
    acct = account_key(label)
    source_url = payload.get("url")
    conn.execute(
        """INSERT INTO accounts(account_key, account_label, first_seen_at, last_seen_at, source_context_json)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(account_key) DO UPDATE SET
             account_label=excluded.account_label,
             last_seen_at=excluded.last_seen_at,
             source_context_json=excluded.source_context_json""",
        (acct, label, now, now, json.dumps({"source_url": source_url}, sort_keys=True)),
    )

    balance_count = 0
    for balance in payload.get("balances") or []:
        amount = parse_money_to_cents(balance.get("amount_text"))
        if amount is None:
            continue
        snapshot_id = stable_hash(run_id, acct, balance.get("balance_type"), balance.get("raw_text"), amount, length=32)
        conn.execute(
            """INSERT OR REPLACE INTO balance_snapshots(
                 snapshot_id, run_id, account_key, observed_at, balance_type,
                 raw_label, amount_cents, currency, source_url, raw_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                run_id,
                acct,
                now,
                balance.get("balance_type") or "unknown",
                balance.get("label"),
                amount,
                balance.get("currency") or "AUD",
                source_url,
                json.dumps(balance, sort_keys=True),
            ),
        )
        balance_count += 1

    tx_count = 0
    for tx in payload.get("transactions") or []:
        amount = parse_money_to_cents(tx.get("amount_text"))
        if amount is None:
            continue
        key = transaction_key(acct, tx)
        running_balance = parse_money_to_cents(tx.get("running_balance_text"))
        conn.execute(
            """INSERT INTO transactions(
                 transaction_key, account_key, posted_date, description, amount_cents,
                 currency, running_balance_cents, source_url, first_seen_at,
                 last_seen_at, last_run_id, raw_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(transaction_key) DO UPDATE SET
                 description=excluded.description,
                 running_balance_cents=COALESCE(excluded.running_balance_cents, transactions.running_balance_cents),
                 source_url=excluded.source_url,
                 last_seen_at=excluded.last_seen_at,
                 last_run_id=excluded.last_run_id,
                 raw_json=excluded.raw_json""",
            (
                key,
                acct,
                normalize_date(tx.get("posted_date_text")),
                re.sub(r"\s+", " ", tx.get("description") or "").strip(),
                amount,
                tx.get("currency") or "AUD",
                running_balance,
                source_url,
                now,
                now,
                run_id,
                json.dumps(tx, sort_keys=True),
            ),
        )
        tx_count += 1

    conn.commit()
    return {"account_key": acct, "balances": balance_count, "transactions": tx_count}


def run_browser_probe(
    start_url: str,
    interactive_login: bool,
    login_timeout: int,
    use_current_tab: bool = False,
) -> dict[str, Any]:
    code = (
        BROWSER_PROBE
        .replace("__START_URL__", json.dumps(start_url))
        .replace("__INTERACTIVE_LOGIN__", "True" if interactive_login else "False")
        .replace("__LOGIN_TIMEOUT__", str(login_timeout))
        .replace("__USE_CURRENT_TAB__", "True" if use_current_tab else "False")
    )
    proc = subprocess.run(
        ["browser-harness", "-c", code],
        text=True,
        capture_output=True,
        timeout=max(login_timeout + 60, 120),
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    result_line = None
    for line in combined.splitlines():
        if line.startswith(RESULT_MARKER):
            result_line = line[len(RESULT_MARKER):]
    if not result_line:
        raise RuntimeError(
            "browser probe did not emit a result marker; "
            f"exit={proc.returncode}; output={redact_text(combined[-2000:])}"
        )
    payload = sanitize_payload(json.loads(result_line))
    payload["_browser_exit_code"] = proc.returncode
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--start-url", default=DEFAULT_START_URL)
    parser.add_argument("--interactive-login", action="store_true")
    parser.add_argument("--login-timeout", type=int, default=180)
    parser.add_argument("--current-tab", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--require-transactions", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + stable_hash(time.time(), length=8)
    payload = run_browser_probe(args.start_url, args.interactive_login, args.login_timeout, args.current_tab)

    if args.dry_run:
        print(json.dumps(payload, indent=2, sort_keys=True))
        if payload.get("status") != "ok":
            return 2
        if args.require_transactions and not payload.get("transactions"):
            return 3
        return 0

    conn = init_db(args.db)
    insert_run(conn, run_id)
    try:
        if payload.get("status") != "ok":
            finish_run(conn, run_id, "blocked", payload, payload.get("url") or payload.get("page", {}).get("url"))
            return 2
        counts = upsert_payload(conn, run_id, payload)
        status = "ok"
        if args.require_transactions and counts["transactions"] == 0:
            status = "partial"
        finish_run(
            conn,
            run_id,
            status,
            {"counts": counts, "extraction": payload.get("extraction", {})},
            payload.get("url"),
            str(counts["account_key"]),
        )
        print(json.dumps({"run_id": run_id, "status": status, **counts}, sort_keys=True))
        return 3 if status == "partial" else 0
    except Exception as exc:
        finish_run(conn, run_id, "error", {"error": str(exc), "payload_status": payload.get("status")})
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
