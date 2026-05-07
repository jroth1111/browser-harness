#!/usr/bin/env python3
"""Sync visible Coles credit card balances and transactions to SQLite.

This script intentionally uses the official browser login flow through
browser-harness. It never reads credentials, cookies, localStorage,
sessionStorage, or auth tokens.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DEFAULT_START_URL = "https://secure.coles.com.au/home/account_dashboard"
DEFAULT_AUTH_MAX_AGE = 20
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
    "code_verifier",
    "id_token",
    "nonce",
    "refresh_token",
    "session",
    "session_state",
    "state",
    "token",
    "x-state",
}


BROWSER_PROBE = r'''
import json
import csv
import io
import os
import re
import tempfile
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

START_URL = __START_URL__
INTERACTIVE_LOGIN = __INTERACTIVE_LOGIN__
LOGIN_TIMEOUT = __LOGIN_TIMEOUT__
USE_CURRENT_TAB = __USE_CURRENT_TAB__
EXPORT_CSV = __EXPORT_CSV__
AUTH_MAX_AGE = __AUTH_MAX_AGE__

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
    return bool(re.search(r"id\.colesgroupprofile|auth\.colesgroupprofile|secure\.coles\.com\.au/login\b|Login - Coles Credit Cards|Log in with your Coles account|Log in or create account|Email Password|Your old credit card login|Complete application", text, re.I))

def _rewrite_url_max_age(url, max_age):
    if max_age is None or max_age < 0:
        return url
    parts = urlsplit(url)
    if not re.search(r"(^|\.)colesgroupprofile\.com\.au$", parts.netloc):
        return url
    query = parse_qsl(parts.query, keep_blank_values=True)
    changed = False
    found = False
    out = []
    for key, value in query:
        if key == "max_age":
            found = True
            new_value = str(max_age)
            changed = changed or value != new_value
            out.append((key, new_value))
        else:
            out.append((key, value))
    if not found:
        out.append(("max_age", str(max_age)))
        changed = True
    if not changed:
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(out), parts.fragment))

def _apply_auth_max_age():
    if AUTH_MAX_AGE is None or AUTH_MAX_AGE < 0:
        return {"changed": False, "reason": "disabled"}
    payload = _all_text_payload()
    current = payload.get("url") or ""
    rewritten = _rewrite_url_max_age(current, AUTH_MAX_AGE)
    if rewritten == current:
        return {"changed": False, "url": current}
    js("location.replace(%s)" % json.dumps(rewritten))
    return {"changed": True, "url": rewritten}

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

def _ensure_transactions_page():
    payload = _all_text_payload()
    if "/transactions" in (payload.get("url") or "") and re.search(r"Transaction history|transactions for", payload.get("body_excerpt") or "", re.I):
        return payload
    clicked = _click_transactions()
    if clicked.get("clicked"):
        deadline = time.time() + 20
        while time.time() < deadline:
            time.sleep(1)
            payload = _all_text_payload()
            if "/transactions" in (payload.get("url") or "") and re.search(r"Transaction history|transactions for", payload.get("body_excerpt") or "", re.I):
                return payload
    js("location.href = 'https://secure.coles.com.au/transactions'")
    deadline = time.time() + 20
    while time.time() < deadline:
        time.sleep(1)
        payload = _all_text_payload()
        if "/transactions" in (payload.get("url") or "") and re.search(r"Transaction history|transactions for", payload.get("body_excerpt") or "", re.I):
            return payload
    return payload

def _download_csv_export():
    download_dir = tempfile.mkdtemp(prefix="coles-card-export-")
    try:
        cdp("Browser.setDownloadBehavior", behavior="allow", downloadPath=download_dir)
        try:
            clicked = js(r"""
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
  function find(selector) {
    for (const root of roots()) {
      if (!root.querySelector) continue;
      const el = root.querySelector(selector);
      if (el) return el;
    }
    return null;
  }
  const exportButton = find("#export");
  if (!exportButton) return {clicked: false, reason: "export_button_missing"};
  exportButton.click();
  const started = Date.now();
  return new Promise(resolve => {
    const tick = () => {
      const csvButton = find("#ExportAsCSV");
      if (csvButton) {
        csvButton.click();
        resolve({clicked: true});
        return;
      }
      if (Date.now() - started > 5000) {
        resolve({clicked: false, reason: "csv_menu_missing"});
        return;
      }
      setTimeout(tick, 100);
    };
    tick();
  });
})()
""")
            if not clicked.get("clicked"):
                return {"clicked": clicked, "rows": [], "fieldnames": [], "downloaded": False}
            deadline = time.time() + 30
            csv_path = None
            while time.time() < deadline:
                for name in os.listdir(download_dir):
                    if name.endswith(".crdownload"):
                        continue
                    if name.lower().endswith(".csv"):
                        csv_path = os.path.join(download_dir, name)
                        break
                if csv_path:
                    break
                time.sleep(0.25)
            if not csv_path:
                return {"clicked": clicked, "rows": [], "fieldnames": [], "downloaded": False}
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                text = f.read()
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
            return {
                "clicked": clicked,
                "downloaded": True,
                "fieldnames": reader.fieldnames or [],
                "rows": rows,
            }
        finally:
            try:
                cdp("Browser.setDownloadBehavior", behavior="default")
            except Exception:
                pass
    finally:
        for name in os.listdir(download_dir):
            try:
                os.remove(os.path.join(download_dir, name))
            except OSError:
                pass
        try:
            os.rmdir(download_dir)
        except OSError:
            pass

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
        _apply_auth_max_age()
        _click_authorize_button()
        deadline = time.time() + LOGIN_TIMEOUT
        while time.time() < deadline:
            time.sleep(3)
            _apply_auth_max_age()
            payload = _all_text_payload()
            if not _is_auth_surface(payload):
                break
        else:
            _result("blocked", reason="login_timeout", page=_all_text_payload())
            raise SystemExit(0)
    dashboard = _all_text_payload()
    tx_click = {"clicked": False}
    if EXPORT_CSV:
        tx_page = _ensure_transactions_page()
        if _is_auth_surface(tx_page):
            _result("blocked", reason="not_logged_in", page=tx_page)
            raise SystemExit(0)
        tx_click = {"clicked": "/transactions" in (tx_page.get("url") or ""), "via": "export_csv"}
        csv_export = _download_csv_export()
    else:
        csv_export = None
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
        transactions_csv=(csv_export or {}).get("rows") if csv_export else [],
        csv_export={
            "downloaded": (csv_export or {}).get("downloaded", False),
            "fieldnames": (csv_export or {}).get("fieldnames", []),
            "row_count": len((csv_export or {}).get("rows", [])) if csv_export else 0,
        },
        extraction={
            "dashboard_url": dashboard.get("url"),
            "transactions_url": tx_page.get("url"),
            "transactions_click": tx_click,
            "balance_count": len(balances),
            "dom_transaction_count": len(transactions),
            "csv_transaction_count": len((csv_export or {}).get("rows", [])) if csv_export else 0,
        },
    )
except SystemExit:
    raise
except Exception as exc:
    fallback_page = {}
    if 'js' in globals():
        try:
            fallback_page = _all_text_payload()
        except Exception:
            fallback_page = {}
    _result("error", reason=str(exc), page=fallback_page)
'''


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def redact_text(value: str) -> str:
    value = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[redacted-email]", value, flags=re.I)
    return re.sub(r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b", "[redacted-jwt]", value)


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
            processed_on TEXT,
            description TEXT NOT NULL,
            merchant_name TEXT,
            transaction_type TEXT,
            category TEXT,
            account_number TEXT,
            card_ending TEXT,
            status TEXT,
            amount_cents INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'AUD',
            running_balance_cents INTEGER,
            source_url TEXT,
            source_method TEXT NOT NULL DEFAULT 'dom',
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
    ensure_transaction_columns(conn)
    return conn


def ensure_transaction_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()}
    additions = {
        "processed_on": "TEXT",
        "merchant_name": "TEXT",
        "transaction_type": "TEXT",
        "category": "TEXT",
        "account_number": "TEXT",
        "card_ending": "TEXT",
        "status": "TEXT",
        "source_method": "TEXT NOT NULL DEFAULT 'dom'",
    }
    for column, ddl in additions.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE transactions ADD COLUMN {column} {ddl}")
    conn.commit()


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
        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            if len(year) == 2:
                year = "20" + year
            return f"{year.zfill(4)}-{month.zfill(2)}-{day.zfill(2)}"
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{2,4})$", text)
    if m:
        day, month_name, year = m.groups()
        month = month_map.get(month_name.lower())
        if month and 1 <= int(day) <= 31:
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
    account_number = re.sub(r"\s+", "", tx.get("account_number") or "")
    processed = normalize_date(tx.get("processed_on"))
    return stable_hash(account, account_number, posted, processed, amount, description, length=32)


def dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def normalize_csv_transaction(row: dict[str, Any]) -> dict[str, Any]:
    details = re.sub(r"\s+", " ", row.get("Transaction Details") or "").strip()
    transaction_type = re.sub(r"\s+", " ", row.get("Transaction Type") or "").strip()
    account_number = re.sub(r"\s+", " ", row.get("Account Number") or "").strip()
    card_match = re.search(r"(\d{4})\s*$", account_number) or re.search(r"Card ending\s+(\d{4})", details, re.I)
    status = "pending" if re.search(r"\bpending\b", transaction_type + " " + details, re.I) else "posted"
    description = re.sub(r"\bPending:\s*", "", details, flags=re.I)
    description = re.sub(r"\s*Card ending\s+\d{4}\b", "", description, flags=re.I).strip()
    return {
        "posted_date_text": row.get("Date"),
        "processed_on": normalize_date(row.get("Processed On")),
        "description": description or details or row.get("Merchant Name") or transaction_type or "Transaction",
        "merchant_name": re.sub(r"\s+", " ", row.get("Merchant Name") or "").strip() or None,
        "transaction_type": transaction_type or None,
        "category": re.sub(r"\s+", " ", row.get("Category") or "").strip() or None,
        "account_number": account_number or None,
        "card_ending": card_match.group(1) if card_match else None,
        "status": status,
        "amount_text": row.get("Amount"),
        "currency": "AUD",
        "raw_text": " | ".join(f"{key}={value}" for key, value in row.items() if value),
        "raw_csv": row,
        "source_method": "csv_export",
    }


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


def payload_source_url(payload: dict[str, Any]) -> str | None:
    page = payload.get("page") if isinstance(payload.get("page"), dict) else {}
    return payload.get("url") or page.get("url")


def upsert_payload(
    conn: sqlite3.Connection,
    run_id: str,
    payload: dict[str, Any],
    account_label_override: str | None = None,
) -> dict[str, int | str]:
    now = utc_now()
    label = (account_label_override or payload.get("account_label") or "Coles Credit Card").strip()
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
    for balance in dict_rows(payload.get("balances")):
        amount = parse_money_to_cents(balance.get("amount_text"))
        if amount is None:
            continue
        snapshot_id = stable_hash(run_id, acct, balance.get("balance_type") or "unknown", length=32)
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
    inserted_count = 0
    csv_rows = [normalize_csv_transaction(row) for row in dict_rows(payload.get("transactions_csv"))]
    dom_rows = [] if csv_rows else dict_rows(payload.get("transactions"))
    for tx in csv_rows + dom_rows:
        amount = parse_money_to_cents(tx.get("amount_text"))
        if amount is None:
            continue
        key = transaction_key(acct, tx)
        existed = conn.execute(
            "SELECT 1 FROM transactions WHERE transaction_key=?",
            (key,),
        ).fetchone() is not None
        running_balance = parse_money_to_cents(tx.get("running_balance_text"))
        conn.execute(
            """INSERT INTO transactions(
                 transaction_key, account_key, posted_date, processed_on, description,
                 merchant_name, transaction_type, category, account_number, card_ending,
                 status, amount_cents, currency, running_balance_cents, source_url,
                 source_method, first_seen_at, last_seen_at, last_run_id, raw_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(transaction_key) DO UPDATE SET
                 description=excluded.description,
                 merchant_name=COALESCE(excluded.merchant_name, transactions.merchant_name),
                 transaction_type=COALESCE(excluded.transaction_type, transactions.transaction_type),
                 category=COALESCE(excluded.category, transactions.category),
                 account_number=COALESCE(excluded.account_number, transactions.account_number),
                 card_ending=COALESCE(excluded.card_ending, transactions.card_ending),
                 status=COALESCE(excluded.status, transactions.status),
                 running_balance_cents=COALESCE(excluded.running_balance_cents, transactions.running_balance_cents),
                 source_url=excluded.source_url,
                 source_method=CASE
                   WHEN excluded.source_method='csv_export' THEN 'csv_export'
                   WHEN transactions.source_method='csv_export' THEN 'csv_export'
                   ELSE excluded.source_method
                 END,
                 last_seen_at=excluded.last_seen_at,
                 last_run_id=excluded.last_run_id,
                 raw_json=CASE
                   WHEN excluded.source_method='csv_export' THEN excluded.raw_json
                   WHEN transactions.source_method='csv_export' THEN transactions.raw_json
                   ELSE excluded.raw_json
                 END""",
            (
                key,
                acct,
                normalize_date(tx.get("posted_date_text")),
                tx.get("processed_on"),
                re.sub(r"\s+", " ", tx.get("description") or "").strip(),
                tx.get("merchant_name"),
                tx.get("transaction_type"),
                tx.get("category"),
                tx.get("account_number"),
                tx.get("card_ending"),
                tx.get("status"),
                amount,
                tx.get("currency") or "AUD",
                running_balance,
                source_url,
                tx.get("source_method") or "dom",
                now,
                now,
                run_id,
                json.dumps(tx, sort_keys=True),
            ),
        )
        tx_count += 1
        if not existed:
            inserted_count += 1

    conn.commit()
    return {
        "account_key": acct,
        "balances": balance_count,
        "transactions": tx_count,
        "transactions_inserted": inserted_count,
        "transactions_csv": len(csv_rows),
        "transactions_dom": len(dom_rows),
    }


def run_browser_probe(
    start_url: str,
    interactive_login: bool,
    login_timeout: int,
    use_current_tab: bool = False,
    export_csv: bool = False,
    auth_max_age: int = DEFAULT_AUTH_MAX_AGE,
) -> dict[str, Any]:
    code = (
        BROWSER_PROBE
        .replace("__START_URL__", json.dumps(start_url))
        .replace("__INTERACTIVE_LOGIN__", "True" if interactive_login else "False")
        .replace("__LOGIN_TIMEOUT__", str(login_timeout))
        .replace("__USE_CURRENT_TAB__", "True" if use_current_tab else "False")
        .replace("__EXPORT_CSV__", "True" if export_csv else "False")
        .replace("__AUTH_MAX_AGE__", str(auth_max_age))
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
    parser.add_argument("--auth-max-age", type=int, default=DEFAULT_AUTH_MAX_AGE)
    parser.add_argument("--interactive-login", action="store_true")
    parser.add_argument("--login-timeout", type=int, default=180)
    parser.add_argument("--current-tab", action="store_true")
    parser.add_argument("--export-csv", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--require-transactions", action="store_true")
    parser.add_argument(
        "--account-label",
        default=None,
        help="Override the page-derived account label; stabilises account_key across runs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + stable_hash(time.time(), length=8)
    payload = run_browser_probe(
        args.start_url,
        args.interactive_login,
        args.login_timeout,
        args.current_tab,
        args.export_csv,
        args.auth_max_age,
    )

    if args.dry_run:
        print(json.dumps(payload, indent=2, sort_keys=True))
        if payload.get("status") != "ok":
            return 2
        if args.require_transactions and not (payload.get("transactions") or payload.get("transactions_csv")):
            return 3
        return 0

    conn = init_db(args.db)
    insert_run(conn, run_id)
    try:
        if payload.get("status") != "ok":
            finish_run(conn, run_id, "blocked", payload, payload_source_url(payload))
            print(json.dumps({
                "run_id": run_id,
                "status": "blocked",
                "reason": payload.get("reason"),
            }, sort_keys=True))
            return 2
        counts = upsert_payload(conn, run_id, payload, account_label_override=args.account_label)
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
