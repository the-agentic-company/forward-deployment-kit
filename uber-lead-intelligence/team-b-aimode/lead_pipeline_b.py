#!/usr/bin/env python3
"""Uber Eats Lead Intelligence, EXTRA build (Team B, Google AI Mode): the fixed pipeline.

Places research is shared with the Places-only build (`lead_pipeline.py`, same folder). This
script adds the web layer: in fast mode, each restaurant gets Google AI Mode research through the
`ai_mode_research` tool of google-places-oauth (two AI Mode questions per lead via DataForSEO:
the twelve points, and delivery storefronts), run with `bap-mcp batch`. Results go to files, and
only compact excerpts reach the model. Exa and Firecrawl remain for the non-fast mode.

Usage (one command per step, in this order):
  python lead_pipeline_b.py run <input.csv|input.xlsx>   Places research -> /tmp/work/review.json
  python lead_pipeline_b.py web                          apply overrides.json, run all web searches,
                                                         write /tmp/work/web/digest_NN.json
  python lead_pipeline_b.py render                       read /tmp/work/web/extract_NN.json, write
                                                         leads.csv, output.html, engine-analysis.pdf,
                                                         then check
  python lead_pipeline_b.py check                        validation only
"""

import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lead_pipeline as core  # noqa: E402
import research_sales as sales  # noqa: E402

WORK, APP, TEMPLATE = core.WORK, core.APP, core.TEMPLATE
WEB = WORK / "web"
PDF_PATH = APP / "engine-analysis.pdf"
BUILD = "Places + Google AI Mode (Extra)"
CHUNK = 12
# No total Firecrawl request cap. Cadence is measured and adapted during the real workload.

EXTRA_COLUMNS = (
    "On Uber Eats, On DoorDash, On Grubhub, Platform Source, Extra Contact Person, Extra Contact Phone, "
    "Public Email, Extra Contact Source, Tenure, Other Locations, Tenure Source, Best Seller Dish, "
    "Best Seller Source, Avg Order Count, Avg Order Value, Avg Order Source, Peak Hours, Peak Hours Source, "
    "City Population, City Population Source, City Delivery Restaurants, City Delivery Restaurants Source, "
    "City Uber Couriers, City Uber Couriers Source, City Uber Eats Users, City Uber Eats Users Source, "
    "Same Cuisine On Uber Eats, Same Cuisine Source, Delivery vs Onsite Benchmark, Delivery vs Onsite Source, "
    "Engagement Score, Engagement Band, Engagement Rationale, Field Engines, Fields From Exa, "
    "Fields From Firecrawl, Exa Calls, Firecrawl Calls, Extra Not Found"
).split(", ") + ["Status Reason", "Next Action", "Review Flags", "Google Type", "About Merchant", "About Source", "Menu Note", "Menu Source",
                 "Research Brief", "Sales Playbook", "Outreach Email Subject", "Outreach Email Body", "Outreach Personalization Sources"]

FIELD_KEYS = [
    "Contact person", "Public email", "Tenure & other locations", "Best-seller dish",
    "Average order volume", "Peak order hours", "Population", "Restaurants on delivery platforms",
    "Uber couriers in the area", "Uber Eats users in the area", "Same-cuisine on Uber Eats",
    "Delivery vs on-site volume",
]
FIELD_SCOPE = {k: "lead" for k in FIELD_KEYS[:6]}
FIELD_SCOPE.update({k: "city" for k in FIELD_KEYS[6:11]})
FIELD_SCOPE["Delivery vs on-site volume"] = "market"
LEAD_QUERY_FOR = {
    "Contact person": "operator", "Public email": "operator", "Tenure & other locations": "operator",
    "Best-seller dish": "reputation", "Average order volume": "reputation", "Peak order hours": "reputation",
}
PLATFORMS = {
    "uberEats": ("ubereats.com", "Uber Eats"),
    "doorDash": ("doordash.com", "DoorDash"),
    "grubhub": ("grubhub.com", "Grubhub"),
}
AGGREGATOR_HINTS = ("yelp.", "tripadvisor.", "restaurantji.", "menupix.", "checkle.", "allmenus.",
                    "zmenu.", "menuweb.", "sirved.", "restaurantguru.", "wanderlog.", "mapquest.",
                    "yellowpages.", "zoominfo.", "opencorporates.", "bizapedia.", "facebook.",
                    "instagram.", "reddit.", "tiktok.")
CONTEXT_WORDS = re.compile(
    r"owner|owned|founder|founded|since|opened|years|family|chef|manager|best|popular|favorite|"
    r"famous|signature|must[- ]try|busy|rush|crowd|wait|line|lunch|dinner|order|delivery|"
    r"location|locations|email|@", re.I)


# ---------------------------------------------------------------- web results


def parse_exa(result):
    """Exa returns text blocks: Title/URL/Published/Author/Highlights, separated by ---."""
    if not isinstance(result, str):
        return []
    items = []
    for block in re.split(r"\n---\n", result):
        url = re.search(r"^URL:\s*(\S+)", block, re.M)
        if not url:
            continue
        title = re.search(r"^Title:\s*(.*)$", block, re.M)
        text = block.split("Highlights:", 1)[1] if "Highlights:" in block else block
        items.append({"url": url.group(1), "title": title.group(1).strip() if title else "",
                      "text": text.strip()})
    return items


def parse_firecrawl(result):
    if not isinstance(result, dict):
        return []
    web = (result.get("data") or {}).get("web") or []
    return [{"url": w.get("url", ""), "title": w.get("title", ""),
             "text": " ".join(str(w.get(k) or "") for k in ("description", "markdown"))}
            for w in web if isinstance(w, dict) and w.get("url")]


def domain(url):
    host = urllib.parse.urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def host_is(host, expected):
    return host == expected or host.endswith("." + expected)


def digits(text):
    return re.sub(r"\D", "", text or "")


def gate(place, item):
    """Identity gate: the page must match the Places anchor on at least two of name, street
    address, phone, website domain."""
    blob = f"{item['title']} {item['text']}"
    hits = []
    if core.name_score(place["name"], item["title"]) >= 0.75 or (
            core.norm(place["name"]) and f" {core.norm(place['name'])} " in f" {core.norm(blob)} "):
        hits.append("name")
    street = place["address"].split(",")[0]
    number = re.match(r"\s*(\d+)\s+(\S+)", street)
    if number and re.search(rf"\b{number.group(1)}\s+{re.escape(number.group(2))}", blob, re.I):
        hits.append("street")
    phone = digits(place["phone"])[-10:]
    if len(phone) == 10 and phone in digits(blob):
        hits.append("phone")
    site = domain(place["website"])
    if site and site not in ("facebook.com", "instagram.com") and host_is(domain(item["url"]), site):
        hits.append("domain")
    return hits


def source_state(place, url):
    """Own website or platform storefront = VERIFIED; everything else ASSUMED."""
    host = domain(url)
    site = domain(place["website"]) if place else ""
    if site and host_is(host, site):
        return "VERIFIED"
    if any(host_is(host, p[0]) for p in PLATFORMS.values()):
        return "VERIFIED"
    return "ASSUMED"


def excerpt(text, limit=1100):
    """Keeps the sentences that can answer the lead questions."""
    lines = [l.strip() for l in re.split(r"\n+|(?<=[.!?])\s+", text or "") if len(l.strip()) > 3]
    keep = [l for l in lines if CONTEXT_WORDS.search(l)] or lines
    out = ""
    for line in keep:
        if len(out) + len(line) > limit:
            if not out:
                out = line[:limit]
            break
        out += line + " "
    return out.strip()


# ---------------------------------------------------------------- web step


def exa_args(query, objective):
    return {"query": query, "numResults": 5, "objective": objective}


def fc_args(query, objective):
    return {"query": query, "limit": 5, "sources": ["web"], "objective": objective}


# Normal runs use the measured cadence below. Explicit probe mode tests higher concurrency.
# Both modes back off on actual throttling; all unresolved eligible queries stay queued.
# Production experiment b3fa6e14-f576-441a-9112-43b6b865b015: first ten calls
# accepted, next four minute-rate limited. Two-call waves then held the measured cadence.
ENGINE_CONCURRENCY = {"exa": "4", "firecrawl-uber": "2"}
FIRECRAWL_REQUESTS_PER_MINUTE = 9.0  # headroom below the observed minute quota; no total cap
FIRECRAWL_PROBE = os.environ.get("FIRECRAWL_PROBE", "0") == "1"
FAST_MODE = not FIRECRAWL_PROBE
TARGET_RUN_SECONDS = 150
FAST_WEB_SECONDS = 60  # Exa owner searches only start after AI Mode; 25 s covered 13 of 51 leads on 28/10/2026
FIRECRAWL_OBSERVED_MINUTE_QUOTA = 10


def fast_deadline():
    """Persist the web deadline so a second command cannot restart the allowance."""
    path = WEB / "speed-budget.json"
    budget = core.load_json(path, {}) or {}
    if not budget:
        run_start = WORK / "start"
        started = float(run_start.read_text()) if run_start.exists() else time.time()
        budget = {"targetRunSeconds": TARGET_RUN_SECONDS,
                  "deadline": time.time() + FAST_WEB_SECONDS,
                  "webSeconds": FAST_WEB_SECONDS}
        core.save_json(path, budget)
    return budget["deadline"]


def bounded_batch(tool, calls, out_dir, deadline):
    previous = getattr(core, "BATCH_TIMEOUT", None)
    core.BATCH_TIMEOUT = max(.1, min(10, deadline-time.time()))
    try:
        return core.batch(tool, calls, out_dir)
    finally:
        core.BATCH_TIMEOUT = previous


def fast_lead_order(leads):
    """One restaurant per search, reachable/high-value first, round-robin across reps."""
    groups, seen = {}, set()
    ordered = sorted(leads, key=lambda l: (not bool(l["place"].get("phone")),
                     -core.pre_score(l["place"]), l.get("row", 0)))
    for lead in ordered:
        key = lead["place"].get("id") or lead["id"]
        if key in seen:
            continue
        seen.add(key)
        groups.setdefault(lead.get("rep", ""), []).append(lead)
    result = []
    while any(groups.values()):
        for group in groups.values():
            if group:
                result.append(group.pop(0))
    return result


# The platform stops a run when one command shows no progress for 180 s, so `web` works in
# slices and exits after WEB_BUDGET seconds; the next `web` call resumes where it stopped.
WEB_BUDGET = 120
SLICE = 150


class WebPartial(Exception):
    pass


SLICES_RUN = 0


def firecrawl_error_kind(error):
    text = str(error)
    if re.search(r"\b402\b|exceeded (?:your )?credits|insufficient credits|credit.{0,30}(?:exhaust|limit)|payment required|invalid api key|\b401\b", text, re.I):
        return "unavailable"
    if re.search(r"\b429\b|rate.?limit|too many requests|concurren.{0,20}(?:limit|exceed)", text, re.I):
        return "throttled"
    return "transient"


def firecrawl_retry_after(error):
    match = re.search(r"(?:retry[- ]after[\s:=]*|retry (?:in|after)\s+|try again in\s+|resets? in\s+)(\d+(?:\.\d+)?)\s*(ms|milliseconds?|m(?:in(?:ute)?s?)?|s(?:ec(?:ond)?s?)?)?", str(error), re.I)
    if not match:
        return 60.0
    value, unit = float(match[1]), (match[2] or "s").lower()
    return max(1.0, value / 1000 if unit.startswith("ms") or unit.startswith("mill") else value * 60 if unit.startswith("m") else value)


def firecrawl_capacity_report():
    telemetry = core.load_json(WEB / "firecrawl-telemetry.json", {}) or {}
    waves = telemetry.get("waves", [])
    if not waves:
        report = {"totalRequestCap": None, "waves": 0, "logicalAttempts": 0,
                "deferredQueries": telemetry.get("deferredQueries", 0),
                "stopReason": telemetry.get("stopReason", ""), "mode": "fast" if FAST_MODE else "probe"}
        core.save_json(APP / "firecrawl-capacity.json", report)
        return report
    active_seconds = sum(w["durationSeconds"] for w in waves)
    elapsed = max(0.001, waves[-1]["finishedAt"] - waves[0]["startedAt"])
    clean = [w for w in waves if w["succeeded"] == w["attempted"] and not w["errors"]]
    first_throttle = next((w for w in waves if w["throttled"]), None)
    report = {
        "totalRequestCap": None, "logicalAttempts": sum(w["attempted"] for w in waves),
        "successfulLogicalAttempts": sum(w["succeeded"] for w in waves),
        "failedLogicalAttempts": sum(w["attempted"] - w["succeeded"] for w in waves),
        "throttledLogicalAttempts": sum(w["throttled"] for w in waves),
        "waves": len(waves), "activeSeconds": round(active_seconds, 3),
        "wallSeconds": round(elapsed, 3),
        "successfulCallsPerMinuteIncludingPauses": round(sum(w["succeeded"] for w in waves) * 60 / elapsed, 2),
        "highestCleanConcurrency": max((min(w["concurrency"], w["attempted"]) for w in clean), default=0),
        "firstThrottle": first_throttle,
        "currentConcurrency": telemetry.get("concurrency"),
        "learnedIntervalSecondsPerCall": telemetry.get("intervalSeconds", 0),
        "unavailableReason": telemetry.get("unavailableReason", ""),
        "exhaustedQueries": len(telemetry.get("terminalFailures", {})),
        "deferredQueries": telemetry.get("deferredQueries", 0),
        "stopReason": telemetry.get("stopReason", ""), "mode": "fast" if FAST_MODE else "probe",
        "qualification": "Logical bap-mcp calls; transport retries are not separately observable. Fast mode uses a time budget and the observed 10/minute ceiling, not a fixed number of enriched leads. Account capacity may be shared.",
        "waveMeasurements": waves,
    }
    APP.mkdir(parents=True, exist_ok=True)
    core.save_json(APP / "firecrawl-capacity.json", report)
    return report


def run_firecrawl_fast(tool, calls, out_dir):
    """Use a short burst; finish with partial coverage instead of waiting for a quota reset."""
    folder = WORK / out_dir
    folder.mkdir(parents=True, exist_ok=True)
    path = WEB / "firecrawl-telemetry.json"
    t = core.load_json(path, {}) or {"waves": [], "attempts": {}, "terminalFailures": {},
                                    "concurrency": 4, "intervalSeconds": 0}
    deadline = fast_deadline()
    blocked = WEB / "firecrawl-uber-unavailable.json"
    saved = core.SERVER, core.CONCURRENCY
    core.SERVER = "firecrawl-uber"
    try:
        while not blocked.exists():
            pending = [c for c in calls if not (folder / f"{c['id']}.json").exists()
                       and not t["attempts"].get(c["id"])]
            if not pending:
                break
            if deadline-time.time() < 3:
                t["stopReason"] = "Web time budget reached; remaining searches deferred"
                break
            used = sum(w["attempted"] for w in t["waves"] if w["startedAt"] > time.time()-60)
            room = FIRECRAWL_OBSERVED_MINUTE_QUOTA-used
            if room <= 0:
                t["stopReason"] = "Observed minute quota reached; no reset wait in fast mode"
                break
            part = pending[:min(4, room)]
            core.CONCURRENCY = str(len(part))
            started = time.time()
            answers = bounded_batch(tool, part, out_dir, deadline)
            finished = time.time()
            errors = []
            for call in part:
                key = call["id"]
                t["attempts"][key] = t["attempts"].get(key, 0)+1
                if answers.get(key) is not None:
                    core.save_json(folder / f"{key}.json", answers[key])
                else:
                    detail = core.load_json(folder / f"{key}.error.json", {}) or {}
                    error = detail.get("error") or next((e.get("error") for e in core.LAST_BATCH_ERRORS
                              if e.get("id") == key), "No result received")
                    error = str(error).split("\n\nFirecrawl API agent_hints", 1)[0]
                    errors.append({"id": key, "error": error, "kind": firecrawl_error_kind(error)})
                    t["terminalFailures"][key] = error
            wave = {"startedAt": started, "finishedAt": finished, "durationSeconds": round(finished-started, 3),
                    "concurrency": len(part), "attempted": len(part), "succeeded": len(part)-len(errors),
                    "throttled": sum(e["kind"] == "throttled" for e in errors),
                    "errors": errors, "queryIds": [c["id"] for c in part]}
            t["waves"].append(wave)
            usage = core.load_json(WEB / "engine-usage.json", {}) or {}
            usage["firecrawl-uber"] = usage.get("firecrawl-uber", 0)+len(part)
            core.save_json(WEB / "engine-usage.json", usage)
            core.log(f"Firecrawl fast wave: {wave['succeeded']}/{len(part)} in {wave['durationSeconds']}s")
            fatal = next((e for e in errors if e["kind"] == "unavailable"), None)
            if fatal:
                t["unavailableReason"] = fatal["error"]
                core.save_json(blocked, {"reason": fatal["error"]})
            if fatal or wave["throttled"]:
                t["stopReason"] = "Provider unavailable or throttled; no cooldown wait in fast mode"
                break
    finally:
        core.SERVER, core.CONCURRENCY = saved
    t["deferredQueries"] = sum(not (folder / f"{c['id']}.json").exists()
                               and not t["attempts"].get(c["id"]) for c in calls)
    core.save_json(path, t)
    firecrawl_capacity_report()
    return {c["id"]: core.load_json(folder / f"{c['id']}.json") for c in calls}


def run_firecrawl(tool, calls, out_dir):
    """Drain the whole eligible queue in resumable waves; measure actual provider saturation."""
    global SLICES_RUN
    folder = WORK / out_dir
    folder.mkdir(parents=True, exist_ok=True)
    WEB.mkdir(parents=True, exist_ok=True)
    path = WEB / "firecrawl-telemetry.json"
    t = core.load_json(path, {}) or {"concurrency": 3 if FIRECRAWL_PROBE else int(ENGINE_CONCURRENCY["firecrawl-uber"]), "cleanStreak": 0, "intervalSeconds": 0 if FIRECRAWL_PROBE else 60 / FIRECRAWL_REQUESTS_PER_MINUTE, "probe": FIRECRAWL_PROBE,
                                    "nextReadyAt": 0, "attempts": {}, "terminalFailures": {}, "waves": []}
    blocked = WEB / "firecrawl-uber-unavailable.json"
    saved = core.SERVER, core.CONCURRENCY
    core.SERVER = "firecrawl-uber"
    def done(c):
        return (folder / f"{c['id']}.json").exists()
    def persist():
        core.save_json(path, t)
        firecrawl_capacity_report()
    try:
        while not blocked.exists():
            pending = [c for c in calls if not done(c) and c["id"] not in t["terminalFailures"]]
            if not pending:
                break
            if SLICES_RUN and time.time() - WEB_STARTED >= WEB_BUDGET:
                persist()
                raise WebPartial()
            wait = max(0, t.get("nextReadyAt", 0) - time.time())
            if wait:
                remaining = WEB_BUDGET - (time.time() - WEB_STARTED)
                if remaining <= 5:
                    persist()
                    core.log(f"Firecrawl cooldown: {wait:.1f}s remaining; queue preserved for next web slice.")
                    raise WebPartial()
                core.log(f"Firecrawl measured cooldown: waiting {wait:.1f}s, {len(pending)} queries still queued.")
                stop_wait = min(t["nextReadyAt"], time.time() + remaining - 5)
                while time.time() < stop_wait:
                    time.sleep(min(5, stop_wait - time.time()))
                if time.time() < t["nextReadyAt"]:
                    persist()
                    raise WebPartial()
            concurrency = max(1, int(t["concurrency"]))
            part = pending[:concurrency]
            core.CONCURRENCY = str(concurrency)
            started = time.time()
            answers = core.batch(tool, part, out_dir)
            finished = time.time()
            errors, completions = [], []
            for call in part:
                key = call["id"]
                t["attempts"][key] = t["attempts"].get(key, 0) + 1
                result_path = folder / f"{key}.json"
                error_path = folder / f"{key}.error.json"
                measured = result_path if answers.get(key) is not None else error_path
                completed_at = measured.stat().st_mtime if measured.exists() else finished
                completions.append({"id": key, "success": answers.get(key) is not None,
                                    "clientCompletionSeconds": round(max(0, completed_at-started), 3)})
                if answers.get(key) is not None:
                    # The real CLI already writes this; keep identical semantics for recovery/tests.
                    if not result_path.exists():
                        core.save_json(result_path, answers[key])
                    continue
                detail = core.load_json(folder / f"{key}.error.json", {})
                message = detail.get("error") or next((e.get("error", str(e)) for e in core.LAST_BATCH_ERRORS if e.get("id") == key), "No result returned by bap-mcp")
                message = str(message).split("\n\nFirecrawl API agent_hints", 1)[0]
                errors.append({"id": key, "error": message, "kind": firecrawl_error_kind(message)})
            throttled = [e for e in errors if e["kind"] == "throttled"]
            unavailable = next((e for e in errors if e["kind"] == "unavailable"), None)
            wave = {"startedAt": started, "finishedAt": finished, "durationSeconds": round(finished-started, 3),
                    "concurrency": concurrency, "attempted": len(part), "succeeded": len(part)-len(errors),
                    "throttled": len(throttled), "queryIds": [c["id"] for c in part], "errors": errors,
                    "clientCompletions": completions}
            t["waves"].append(wave)
            usage = core.load_json(WEB / "engine-usage.json", {}) or {}
            usage["firecrawl-uber"] = usage.get("firecrawl-uber", 0) + len(part)
            core.save_json(WEB / "engine-usage.json", usage)
            SLICES_RUN += 1
            core.log(f"Firecrawl wave {len(t['waves'])}: concurrency={concurrency}, {wave['succeeded']}/{len(part)} successful, {len(throttled)} throttled, {wave['durationSeconds']}s; {len(pending)-wave['succeeded']} queries remain.")
            if unavailable:
                t["unavailableReason"] = unavailable["error"]
                core.save_json(blocked, {"reason": unavailable["error"], "at": dt.datetime.now(dt.timezone.utc).isoformat()})
                core.log(f"RESEARCH INCOMPLETE: Firecrawl provider unavailable: {unavailable['error'][:240]}")
            elif throttled:
                pause = max(firecrawl_retry_after(e["error"]) for e in throttled)
                accepted_last_minute = sum(w["succeeded"] for w in t["waves"] if w["finishedAt"] >= finished - 60)
                t["intervalSeconds"] = max(t["intervalSeconds"] * 1.5, 60 / max(1, accepted_last_minute))
                t["concurrency"] = max(1, concurrency // 2)
                t["cleanStreak"] = 0
                t["nextReadyAt"] = finished + pause + 1
            elif errors:
                for error in errors:
                    if t["attempts"][error["id"]] >= 3:
                        t["terminalFailures"][error["id"]] = error["error"]
                t["cleanStreak"] = 0
                t["nextReadyAt"] = finished + 2
            else:
                t["cleanStreak"] += 1
                if t.get("probe", True) and t["cleanStreak"] >= 2 and not any(w["throttled"] for w in t["waves"]):
                    t["concurrency"] = concurrency + 1
                    t["cleanStreak"] = 0
                # Once throttling is observed, keep the measured cadence through the remaining run.
                t["nextReadyAt"] = max(finished, started + len(part) * t["intervalSeconds"])
            persist()
    finally:
        core.SERVER, core.CONCURRENCY = saved
    persist()
    return {c["id"]: core.load_json(folder / f"{c['id']}.json") for c in calls}


def run_engine(tool_server, tool, calls, out_dir):
    """Resume successful calls, retry transient failures, stop immediately on exhausted credits."""
    if tool_server == "firecrawl-uber":
        return run_firecrawl_fast(tool, calls, out_dir) if FAST_MODE else run_firecrawl(tool, calls, out_dir)
    folder = WORK / out_dir
    blocked = WEB / f"{tool_server}-unavailable.json"
    done = lambda c: (folder / f"{c['id']}.json").exists()
    saved = core.SERVER, core.CONCURRENCY
    core.SERVER = tool_server
    passes = [ENGINE_CONCURRENCY.get(tool_server, "3")] + (["2", "2"] if tool_server == "exa" else [])
    global SLICES_RUN
    try:
        for index, concurrency in enumerate(passes):
            pending = [c for c in calls if not done(c)]
            if not pending or blocked.exists():
                break
            if index:
                time.sleep(2)
            core.CONCURRENCY = concurrency
            # One cheap health check before scheduling hundreds of billable searches.
            while pending:
                if FAST_MODE and fast_deadline()-time.time() < 13:
                    break  # Reserve a short burst for Firecrawl and time for extraction/rendering.
                # The slice budget belongs to the resumable `web` command; prepare's fast mode is bounded by fast_deadline().
                if not FAST_MODE and SLICES_RUN and time.time() - WEB_STARTED > WEB_BUDGET:
                    raise WebPartial()
                width = 1 if tool_server == "exa" and not (WEB / "exa-healthy.json").exists() else (12 if FAST_MODE else SLICE)
                part, pending = pending[:width], pending[width:]
                answers = bounded_batch(tool, part, out_dir, fast_deadline()-10) if FAST_MODE else core.batch(tool, part, out_dir)
                usage = core.load_json(WEB / "engine-usage.json", {}) or {}
                usage[tool_server] = usage.get(tool_server, 0) + len(part)
                core.save_json(WEB / "engine-usage.json", usage)
                attempts = core.load_json(WEB / "engine-attempts.json", {}) or {}
                ledger = attempts.setdefault(tool_server, {})
                for call in part:
                    ledger[call["id"]] = ledger.get(call["id"], 0)+1
                core.save_json(WEB / "engine-attempts.json", attempts)
                SLICES_RUN += 1
                errors = core.LAST_BATCH_ERRORS
                fatal = next((e for e in errors if re.search(r"\b402\b|exceeded your credits|payment required|invalid api key|\b401\b", str(e), re.I)), None)
                if fatal:
                    core.save_json(blocked, {"reason": str(fatal), "at": dt.datetime.now(dt.timezone.utc).isoformat()})
                    core.log(f"RESEARCH INCOMPLETE: {tool_server} unavailable; no further retries: {str(fatal)[:220]}")
                    pending = []
                    break
                if tool_server == "exa" and any(v is not None for v in answers.values()):
                    core.save_json(WEB / "exa-healthy.json", {"ok": True})
    finally:
        core.SERVER, core.CONCURRENCY = saved
    return {c["id"]: core.load_json(folder / f"{c['id']}.json") for c in calls}


AI_MODE_TOOL = "ai_mode_research"
AI_MODE_CHUNK = 10  # the tool's maximum per call
AI_MODE_TIMEOUT = 150  # 100 leads took 45 s on 25/10/2026; the platform stops a silent command at 180 s
AI_MODE_ANSWER_CHARS = 3000
AI_MODE_REFS = 7


def ai_mode_all(leads):
    """Up to three waves: every lead, then the leads still missing the research answer or the
    storefront answer. DataForSEO fails at random (40101 on 14 to 47 leads in 100 on 25/10/2026,
    after the tool's own retry), so the parts that came back are kept across waves."""
    folder = WORK / "web" / "aimode"
    records, calls_made, cost = {}, 0, 0.0
    pending = list(leads)
    saved = core.SERVER, core.CONCURRENCY, getattr(core, "BATCH_TIMEOUT", None)
    core.SERVER, core.CONCURRENCY, core.BATCH_TIMEOUT = "google-places-oauth", "10", AI_MODE_TIMEOUT
    try:
        for wave in (1, 2, 3):
            if not pending:
                break
            calls = [{"id": f"w{wave}c{n:03d}", "arguments": {"withPlaces": False, "leads": [
                {"id": l["id"], "name": l["place"]["name"], "address": l["place"]["address"],
                 "city": core.parse_address(l["place"]["address"])[0], "state": core.parse_address(l["place"]["address"])[1]}
                for l in pending[i:i + AI_MODE_CHUNK]]}} for n, i in enumerate(range(0, len(pending), AI_MODE_CHUNK))]
            answers = core.batch(AI_MODE_TOOL, calls, f"web/aimode/wave{wave}")
            calls_made += len(calls)
            for result in answers.values():
                if not isinstance(result, dict):
                    continue
                cost += float(result.get("costUsd") or 0)
                for record in result.get("records") or []:
                    kept = records.setdefault(record["id"], record)
                    for part in ("aiMode", "storefronts"):
                        kept[part] = kept.get(part) or record.get(part)
                    kept["dataForSeoCallCount"] = (kept.get("dataForSeoCallCount") or 0) + (record.get("dataForSeoCallCount") or 0) * (kept is not record)
                    kept["error"] = None if kept.get("aiMode") and kept.get("storefronts") else record.get("error") or kept.get("error")
            pending = [l for l in pending if not records.get(l["id"]) or records[l["id"]].get("error")]
    finally:
        core.SERVER, core.CONCURRENCY, core.BATCH_TIMEOUT = saved
    core.save_json(folder / "usage.json", {"calls": calls_made, "costUsd": round(cost, 4), "unresolved": len(pending)})
    return records, calls_made, round(cost, 4)


NOT_PUBLIC = re.compile(r"not publicly (available|listed)", re.I)


def clean_ai_text(text):
    """Plain lines for the digest: links and citation markers out, Markdown out. Every answer line
    stays, including "Not publicly available (...)" ones, whose parenthesis is often the only lead."""
    text = re.sub(r"\[\[\d+\]\]\([^)]*\)|\[\d+\]", "", text or "")
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    lines = []
    for line in text.splitlines():
        bullet = re.match(r"\s*[*-]\s+\S", line)
        line = re.sub(r"\s+", " ", re.sub(r"^\s*#+|\*", "", line)).strip().lstrip("- ").strip()
        if not line:
            continue
        lines.append(f"- {line}" if bullet else line)
    return "\n".join(lines)


PREFILL_LABELS = [("owner", re.compile(r"owner|manager", re.I)), ("menuUSP", re.compile(r"menu style|signature", re.I)),
                  ("facts", re.compile(r"interesting facts?", re.I)), ("bestSeller", re.compile(r"best[- ]sell", re.I)),
                  ("publicEmail", re.compile(r"catering|inquiry email", re.I))]


def prefill_research(answer):
    """Reads AI Mode's numbered answer to the twelve questions into the Research schema. Value and
    evidence are the answer's own line, so the evidence check passes and the agent only corrects."""
    research, current = {}, None
    # "1) Owner or Manager Full Name" then "- Joyce ..." on the next line becomes one "label: value" line.
    answer = re.sub(r"(?mi)^(\d+[.)]\s*[^:\n]*?(?:owner|manager)[^:\n]{0,60}?):?\s*\n- ", r"\1: ", answer or "")
    for line in answer.splitlines():
        # "label: value", or a numbered heading without colon ("3) 3 Interesting Facts") whose bullets follow.
        head = re.match(r"(?:\d+[.)]\s*|-\s*\d*[.)]?\s*)?([^:]{3,80}):\s*(.*)$", line) or re.match(r"\d+[.)]\s*([^:]{3,80})()$", line)
        label = next((key for key, pattern in PREFILL_LABELS if head and pattern.search(head.group(1))), None)
        if label:
            current, value = label, head.group(2).strip()
            if label == "facts":
                continue
            if not value or NOT_PUBLIC.match(value):
                current = None
                continue
            if label == "owner":
                value = re.split(r"\s+\(|;|\s+-\s+|,\s+(?:who|the|a|an)\b", value)[0].strip(" .")
                value = re.sub(r"^(?:owned|run|operated|managed) by\s+", "", value, flags=re.I)
            if label == "publicEmail":
                email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", value)
                if not email:
                    continue
                value = email.group(0).rstrip(".")
            if label == "menuUSP" and research.get("menuUSP"):
                # "Menu style: ..." then "Signature dishes: ...": adjacent lines, one quote.
                previous = research["menuUSP"]
                research[label] = {"value": f"{previous['value']} Signature dishes: {value}", "ref": "r1",
                                   "evidence": f"{previous['evidence']}\n{line}"}
                continue
            research[label] = {"value": value, "ref": "r1", "evidence": line}
        elif current == "facts" and line.startswith("- ") and len(research.get("facts", [])) < 3:
            research.setdefault("facts", []).append({"value": line[2:], "ref": "r1", "evidence": line[2:]})
        elif re.match(r"\d+[.)]\s", line):
            current = None
    return research


def ai_mode_items(place, record):
    """The AI Mode answer becomes one excerpt, its references the others. The identity gate is not
    applied: the question is anchored on the Places name and address, so the answer is about it."""
    ai = (record or {}).get("aiMode") or {}
    items = []
    if ai.get("answer"):
        query = urllib.parse.quote_plus(f"{place['name']} {place['address']}")
        items.append({"url": f"https://www.google.com/search?udm=50&q={query}", "engine": "aimode",
                      "title": f"Google AI Mode answer about {place['name']} (via DataForSEO)",
                      "text": clean_ai_text(ai["answer"])[:AI_MODE_ANSWER_CHARS]})
    for reference in (ai.get("references") or [])[:AI_MODE_REFS]:
        items.append({"url": reference.get("url", ""), "engine": "aimode", "title": reference.get("title") or "",
                      "text": reference.get("snippet") or ""})
    platforms = (record or {}).get("storefronts") or {}
    if platforms.get("answer"):
        items.append({"url": next((platforms[k][0] for k in ("ubereats", "doordash", "grubhub") if platforms.get(k)),
                                  f"https://www.google.com/search?udm=50&q={urllib.parse.quote_plus(place['name'] + ' Uber Eats DoorDash Grubhub')}"),
                      "engine": "aimode", "title": "Google AI Mode answer on delivery platforms", "text": clean_ai_text(platforms["answer"])[:300]})
    return items


def search_all(queries, out_dir):
    """queries: {id: (query, objective)}. Exa first; Firecrawl gets the same query once when Exa
    returned nothing usable (decided by `usable(id, items)`)."""
    exa = run_engine("exa", "web_search_exa",
                     [{"id": k, "arguments": exa_args(q, o)} for k, (q, o) in queries.items()],
                     f"web/{out_dir}_exa")
    return {k: parse_exa(v) for k, v in exa.items()}, {k: v is not None for k, v in exa.items()}


def firecrawl_all(queries, out_dir):
    fc = run_engine("firecrawl-uber", "firecrawl_search",
                    [{"id": k, "arguments": fc_args(q, o)} for k, (q, o) in queries.items()],
                    f"web/{out_dir}_fc")
    return {k: parse_firecrawl(v) for k, v in fc.items()}, {k: v is not None for k, v in fc.items()}


CITY_PATTERNS = {
    "Population": re.compile(
        r"[^.\n]{0,80}\bpopulation\b[^.\n]{0,60}?\b\d{1,3}(?:,\d{3})+\b[^.\n]{0,40}", re.I),
    "Restaurants on delivery platforms": re.compile(
        r"[^.\n]{0,60}\b\d{1,3}(?:,\d{3})*\+?\s+(?:\w+\s){0,2}restaurants?\b[^.\n]{0,40}"
        r"(?:deliver|on uber eats|on doordash|on grubhub)[^.\n]{0,40}", re.I),
    "Uber couriers in the area": re.compile(
        r"[^.\n]{0,60}\b\d{1,3}(?:,\d{3})*\+?\s+(?:uber\s+(?:eats\s+)?)?(?:couriers|delivery (?:drivers|partners))\b"
        r"[^.\n]{0,60}", re.I),
    "Uber Eats users in the area": re.compile(
        r"(?:audience size\s*\d{1,3}(?:,\d{3})+|\b\d{1,3}(?:,\d{3})+\s+uber eats users\b|"
        r"\b\d{1,2}(?:\.\d)?%\s+of\s+(?:residents|adults|consumers|people)[^.\n]{0,40}uber eats)[^.\n]{0,40}", re.I),
    "Same-cuisine on Uber Eats": re.compile(
        r"[^.\n]{0,60}\b\d{1,3}(?:,\d{3})*\+?\s+(?:\w+\s){0,3}(?:restaurants|places|spots)\b[^.\n]{0,60}", re.I),
}


def city_answer(key, items, city):
    for item in items:
        blob = f"{item['title']}\n{item['text']}"
        if core.norm(city) not in core.norm(blob):
            continue
        for match in CITY_PATTERNS[key].finditer(blob):
            sentence = " ".join(match.group(0).split())
            if key == "Population" and "population" not in sentence.lower():
                continue
            return {"value": sentence[:220], "source": item["url"]}
    return None


def platform_hits(place, items):
    found = {}
    for item in items:
        host = domain(item["url"])
        for key, (dom, _label) in PLATFORMS.items():
            if key in found or not host_is(host, dom):
                continue
            path = urllib.parse.urlparse(item["url"]).path
            if not re.search(r"/store/|/restaurant/|/menu/", path):
                continue
            if len(gate(place, item)) >= 2:
                found[key] = item["url"]
    return found


def emails_in(place, items):
    for item in items:
        if len(gate(place, item)) < 2:
            continue
        for email in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", item["text"]):
            if not email.lower().endswith((".png", ".jpg", ".webp")) and "example" not in email:
                return {"value": email.rstrip("."), "source": item["url"]}
    return None


WEB_STARTED = time.time()


def web():
    try:
        web_steps()
    except WebPartial:
        core.log("WEB PARTIAL: time budget reached, progress saved. Run `web` again to continue.")
        sys.exit(3)


def is_non_restaurant(place):
    place = place or {}
    kinds = set(place.get("types") or []) | {place.get("primaryType") or ""}
    wrong = {"car_repair", "car_wash", "gas_station", "bank", "dentist", "insurance_agency", "real_estate_agency", "storage", "parking", "lawyer",
             "beauty_salon", "hair_salon", "hair_care", "barber_shop", "nail_salon",
             "doctor", "hospital", "physiotherapist", "veterinary_care"}
    food = {"restaurant", "food", "cafe", "meal_takeaway", "bakery", "meal_delivery",
            "bar", "brewery", "brewpub", "cafeteria", "coffee_shop", "deli", "food_court",
            "food_truck", "ice_cream_shop", "dessert_shop", "juice_shop", "tea_house",
            "convenience_store", "grocery_store", "supermarket"}
    food_signal = bool(kinds & food) or any(k.endswith("_restaurant") for k in kinds)
    food_signal = food_signal or any(place.get(k) is True for k in ("takeout", "delivery", "dineIn"))
    return bool(kinds & wrong) and not food_signal


def recover_platform_only(leads):
    rejected = [l for l in leads if not l["skip"] and l.get("decision") == "REJECTED"
                and not is_non_restaurant(l.get("place"))
                and (not l.get("place") or l["place"].get("status") not in {"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"})]
    queries = {l["id"]: (f'"{l["merchant"]}" {l["city"]} {l["state"]} site:ubereats.com/store OR site:doordash.com/store OR site:grubhub.com/restaurant',
                            "Find this restaurant on a delivery platform, in the stated state. Return the storefront address and phone.") for l in rejected}
    if not queries:
        return
    found, ok = search_all(queries, "fallback")
    for lead in rejected:
        for it in found.get(lead["id"], []):
            if not any(host_is(domain(it["url"]), dom) for dom, _ in PLATFORMS.values()):
                continue
            if not re.search(r"/store/|/restaurant/|/menu/", urllib.parse.urlparse(it["url"]).path):
                continue
            if core.name_score(lead["merchant"], it["title"]) < .75:
                continue
            blob = it["title"] + " " + it["text"]
            st = lead.get("state")
            geography = bool(st and (re.search(r"\b" + re.escape(st) + r"\b", blob) or any(code == st and name in core.norm(blob) for name, code in core.STATES.items())))
            if not st and lead.get("city"):
                geography = core.norm(lead["city"].split(",")[0]) in core.norm(blob)
            phone = digits(lead.get("inputPhone", ""))[-10:]
            if not geography and not (len(phone) == 10 and phone in digits(blob)):
                continue
            place = core.compact_place({"id": "platform:" + lead["id"], "displayName": {"text": lead["merchant"]}})
            place.update({"types": [], "primaryType": "", "address": "", "status": ""})
            lead.update(place=place, decision="ACCEPTED", confidence="Low", platformOnly=True,
                        platformOnlySource=it["url"], platformOnlyItem=it,
                        identityNote="Unverified, platform only: a delivery storefront matches the restaurant name and input location; Google has not confirmed it.")
            break


def web_steps():
    state = core.load_json(WORK / "state.json")
    if not state:
        raise SystemExit("Run `lead_pipeline_b.py run <file>` first.")
    leads = state["leads"]
    core.apply_overrides(leads)
    for lead in leads:
        if lead.get("decision") == "REVIEW":
            lead["decision"] = "REJECTED"
    WEB.mkdir(parents=True, exist_ok=True)
    if not FAST_MODE:
        recover_platform_only(leads)
    worked = [l for l in leads if not l["skip"] and l.get("decision") in ("ACCEPTED", "RETRIED")
              and l.get("place") and l["place"]["status"] not in {"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"} and not is_non_restaurant(l["place"])]
    WEB.mkdir(parents=True, exist_ok=True)
    started = time.time()
    core.log(f"Web layer for {len(worked)} leads")

    # Lead level: three searches per lead.
    lead_q = {}
    for lead in worked:
        p = lead["place"]
        if lead.get("platformOnly"):
            continue
        name, where = p["name"], ", ".join(core.parse_address(p["address"]))
        street = p["address"].split(",")[0]
        anchor = f"Must match {name} at {street} or phone {p['phone']}."
        lead_q[f"{lead['id']}.platform"] = (f"\"{name}\" {where} official menu signature dishes delivery Uber Eats DoorDash Grubhub",
                                            "Culinary style, 2-3 signature dishes, delivery methods including in-house; actual storefront links. " + anchor)
        lead_q[f"{lead['id']}.operator"] = (f"\"{name}\" {where} owner founder manager contact email about history other locations",
                                            "Search official site, Facebook, LinkedIn, registries and trusted directories. Named owner/founder/general manager; primary and alternative phones and emails; public catering email; history; other branches and their individual addresses, contacts, hours and menu. " + anchor)
        lead_q[f"{lead['id']}.reputation"] = (f"\"{name}\" {where} best seller popular dishes reviews history neighborhood",
                                              "Explicitly most popular/reviewed dish; 3 distinct facts about menu/history/restaurant; sourced urban/suburban/rural setting and named timezone; busy hours, order volume and delivery demand only if published. " + anchor)

    # City level: four searches per distinct city; city+cuisine: one; market: two.
    cities, cuisines = {}, {}
    raw_rows = core.load_json(WORK / "raw.json")["rows"]
    for lead in worked:
        city, st = core.parse_address(lead["place"]["address"])
        ckey = core.norm(f"{city} {st}").replace(" ", "-")
        if city and st:
            cities.setdefault(ckey, (city, st))
        lead["cityKey"] = ckey
        cuisine = (raw_rows[lead["row"]].get("Cuisine Type") or "").strip()
        lead["cuisine"] = cuisine
        if cuisine and city and st:
            cuisines.setdefault(f"{ckey}.{core.norm(cuisine).replace(' ', '-')}", (city, st, cuisine))
            lead["cuisineKey"] = f"{ckey}.{core.norm(cuisine).replace(' ', '-')}"
    city_q = {}
    for ckey, (city, st) in cities.items():
        where = f"{city} {st}".strip()
        city_q[f"{ckey}.pop"] = (f"{where} population", "Latest population figure for this city, with year.")
        city_q[f"{ckey}.rest"] = (f"{where} number of restaurants on Uber Eats DoorDash delivery",
                                  "Count of restaurants offering delivery on platforms in this city.")
        city_q[f"{ckey}.couriers"] = (f"{where} number of Uber Eats delivery couriers drivers",
                                      "Count of Uber or Uber Eats couriers active in this city.")
        city_q[f"{ckey}.users"] = (f"{where} Uber Eats users population share number",
                                   "Count or share of residents using Uber Eats in this city.")
    for key, (city, st, cuisine) in cuisines.items():
        city_q[f"{key}.cuisine"] = (f"best {cuisine} delivery {city} {st} Uber Eats restaurants",
                                    f"How many {cuisine} restaurants deliver on Uber Eats in this city.")
    market_q = {
        "market.1": ("US restaurant delivery versus dine-in order volume share benchmark 2025 2026",
                     "Industry benchmark: share of restaurant orders that are delivery vs on-site."),
        "market.2": ("restaurant off-premise delivery share of sales statistics United States",
                     "Industry benchmark: delivery or off-premise share of restaurant sales."),
    }

    all_q = {**lead_q, **city_q, **market_q}
    if FAST_MODE:
        # One broad restaurant query instead of spending three calls on the same lead.
        # Keep every historical field in the output; city/market searches are deferred.
        lead_q = {f"{l['id']}.platform": (
            f'"{l["place"]["name"]}" {l["place"]["address"]} menu signature dishes owner contact email delivery Uber Eats DoorDash Grubhub',
            'Find official menu, named owner/manager, public business email, best seller only when explicit, restaurant history and actual delivery storefronts. '
            f'Must match {l["place"]["name"]} at {l["place"]["address"]} or phone {l["place"].get("phone", "")}.')
            for l in fast_lead_order(worked) if not l.get("platformOnly")}
        all_q = {**all_q, **lead_q}
    ai_records, ai_calls, ai_cost = {}, 0, 0.0
    if FAST_MODE:
        ai_leads = [l for l in fast_lead_order(worked) if not l.get("platformOnly")]
        ai_records, ai_calls, ai_cost = ai_mode_all(ai_leads)
        exa_items = {f"{l['id']}.platform": ai_mode_items(l["place"], ai_records.get(l["id"])) for l in ai_leads}
        exa_ok = {f"{l['id']}.platform": bool(ai_records.get(l["id"], {}).get("aiMode")) for l in ai_leads}
        lead_q = {f"{l['id']}.platform": (f"Google AI Mode: {l['place']['name']}, {l['place']['address']}", "") for l in ai_leads}
        no_owner = [l for l in ai_leads if not prefill_research(clean_ai_text(((ai_records.get(l["id"]) or {}).get("aiMode") or {}).get("answer"))).get("owner")]
        core.log(f"Owner missing after AI Mode on {len(no_owner)} leads: operator web search")
        operator_items, operator_ok = search_all({f"{l['id']}.operator": all_q[f"{l['id']}.operator"] for l in no_owner}, "search") if no_owner else ({}, {})
        exa_items.update(operator_items)
        exa_ok.update(operator_ok)
    else:
        exa_items, exa_ok = search_all(all_q, "search")

    # Second attempt: same query on Firecrawl when Exa returned nothing usable.
    city_kind_key = {"pop": "Population", "rest": "Restaurants on delivery platforms",
                     "couriers": "Uber couriers in the area", "users": "Uber Eats users in the area"}

    def usable(qid, items):
        owner, kind = qid.rsplit(".", 1)
        if owner == "market":
            return bool(items)
        if owner in by_id:
            return any(len(gate(by_id[owner]["place"], i)) >= 2 for i in items)
        if kind == "cuisine":
            city = cuisines[owner][0]
            return bool(city_answer("Same-cuisine on Uber Eats",
                                    [i for i in items if "ubereats.com" in domain(i["url"])], city))
        return bool(city_answer(city_kind_key[kind], items, cities[owner][0]))

    by_id = {l["id"]: l for l in worked}
    # Prioritize lead questions, population and market; drain the entire eligible fallback queue.
    retry = {qid: all_q[qid] for qid in all_q
             if qid.rsplit(".", 1)[1] in ("platform", "operator", "reputation", "pop", "1", "2")
             and not usable(qid, exa_items.get(qid) or [])}
    priority = {"platform": 0, "operator": 1, "reputation": 2, "1": 3, "pop": 4}
    retry = dict(sorted(retry.items(), key=lambda kv: priority.get(kv[0].rsplit(".", 1)[1], 9)))
    if FAST_MODE:
        retry = {}  # AI Mode retries its own failures; no Firecrawl second attempt
    else:
        core.log(f"Firecrawl second attempt on {len(retry)} empty searches")
    fc_items, fc_ok = firecrawl_all(retry, "search") if retry else ({}, {})

    def items_for(qid):
        exa_list = [{"engine": "exa", **i} for i in exa_items.get(qid) or []]
        fc_list = [{**i, "engine": "firecrawl"} for i in fc_items.get(qid) or []]
        return exa_list + fc_list

    # Deterministic answers: platforms, email, city figures.
    city_answers = {}
    for ckey, (city, st) in cities.items():
        for key, qkind in [("Population", "pop"), ("Restaurants on delivery platforms", "rest"),
                           ("Uber couriers in the area", "couriers"), ("Uber Eats users in the area", "users")]:
            qid = f"{ckey}.{qkind}"
            ans = None
            for engine in ("exa", "firecrawl"):
                pool = [i for i in items_for(qid) if i["engine"] == engine]
                ans = city_answer(key, pool, city)
                if ans:
                    ans["engine"] = engine
                    break
            city_answers[(ckey, key)] = {"answer": ans, "search": "Deferred: fast run time budget" if FAST_MODE else all_q[qid][0]}
    for key, (city, st, cuisine) in cuisines.items():
        qid = f"{key}.cuisine"
        ans = None
        for engine in ("exa", "firecrawl"):
            pool = [i for i in items_for(qid) if i["engine"] == engine and "ubereats.com" in domain(i["url"])]
            ans = city_answer("Same-cuisine on Uber Eats", pool, city)
            if ans:
                ans["engine"] = engine
                break
        city_answers[(key, "Same-cuisine on Uber Eats")] = {"answer": ans, "search": "Deferred: fast run time budget" if FAST_MODE else all_q[qid][0]}

    digests, n = [], 0
    for lead in worked:
        place = lead["place"]
        pool = ([{**lead["platformOnlyItem"], "engine": "exa", "query": "platform"}] if lead.get("platformOnly") else [])
        for kind in ("platform", "operator", "reputation"):
            qid = f"{lead['id']}.{kind}"
            for item in items_for(qid):
                pool.append({**item, "query": kind})
        platform = platform_hits(place, pool)
        searched_platform = lead.get("platformOnly") or exa_ok.get(f"{lead['id']}.platform") or fc_ok.get(f"{lead['id']}.platform")
        storefronts = (ai_records.get(lead["id"]) or {}).get("storefronts")
        if storefronts is not None:
            # The tool kept only store pages whose slug carries the restaurant's name.
            platform = {key: storefronts.get(name)[0] for key, name in (("uberEats", "ubereats"), ("doorDash", "doordash"), ("grubhub", "grubhub")) if storefronts.get(name)}
        searched_platform = searched_platform and storefronts is not None if lead["id"] in ai_records else searched_platform
        if lead.get("platformOnly"):
            platform = {k: lead["platformOnlySource"] for k, (dom, _) in PLATFORMS.items() if host_is(domain(lead["platformOnlySource"]), dom)}
        lead["platforms"] = {k: platform.get(k) for k in PLATFORMS}
        lead["platformSearched"] = bool(searched_platform)
        lead["emailFound"] = emails_in(place, pool) or next(({"value": e.rstrip("."), "source": i["url"]}
            for i in pool if i.get("engine") == "aimode" for e in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", i["text"])
            if not e.lower().endswith((".png", ".jpg", ".webp")) and "example" not in e), None)
        refs = []
        for item in pool:
            hits = gate(place, item)
            if len(hits) < 2 and not lead.get("platformOnly") and item.get("engine") != "aimode":
                continue
            if any(r["url"] == item["url"] for r in refs):
                continue
            refs.append({"ref": f"r{len(refs) + 1}", "url": item["url"], "engine": item["engine"],
                         "query": item["query"], "title": item["title"][:120],
                         "text": item["text"] if item.get("engine") == "aimode" else excerpt(item["text"])})
            if len(refs) >= (AI_MODE_REFS + 5 if lead["id"] in ai_records else 6):
                break
        lead["refs"] = refs
        lead["searches"] = {k: all_q.get(f"{lead['id']}.{k}", ("Platform-only fallback", ""))[0] for k in ("platform", "operator", "reputation")}
        exa_attempts = core.load_json(WEB / "engine-attempts.json", {}).get("exa", {})
        fc_attempts = core.load_json(WEB / "firecrawl-telemetry.json", {}).get("attempts", {})
        lead["webCalls"] = {
            "exa": exa_attempts.get(lead['id'], 0) + sum(exa_attempts.get(f"{lead['id']}.{k}", 0) for k in ("platform", "operator", "reputation")),
            "firecrawl": sum(fc_attempts.get(f"{lead['id']}.{k}", 0) for k in ("platform", "operator", "reputation")),
            "aimode": (ai_records.get(lead["id"]) or {}).get("dataForSeoCallCount", 0),
        }
        if (ai_records.get(lead["id"]) or {}).get("error"):
            lead["aiModeError"] = ai_records[lead["id"]]["error"]
        if FAST_MODE:
            lead["searches"] = {k: lead_q.get(f"{lead['id']}.platform", ("", ""))[0]
                if lead["platformSearched"] else "Deferred or unavailable: fast run time budget / provider failure"
                for k in ("platform", "operator", "reputation")}
            if f"{lead['id']}.operator" in exa_ok:
                lead["searches"]["operator"] = all_q[f"{lead['id']}.operator"][0]
        if refs:
            digests.append({"leadId": lead["id"], "name": place["name"], "address": place["address"],
                            "refs": [{k: r[k] for k in ("ref", "url", "title", "text")} for r in refs]})

    prefill = {}
    for lead in worked:
        first = next((r for r in lead.get("refs") or [] if r["ref"] == "r1" and r["engine"] == "aimode"), None)
        research = prefill_research(first["text"]) if first else {}
        if research:
            prefill[lead["id"]] = {"Research": research}
    core.save_json(WEB / "prefill.json", prefill)
    for digest in digests:
        filled = (prefill.get(digest["leadId"]) or {}).get("Research") or {}
        if filled:
            digest["prefilled"] = {k: (v["value"] if isinstance(v, dict) else [f["value"] for f in v]) for k, v in filled.items()}
    for i in range(0, len(digests), CHUNK):
        n += 1
        core.save_json(WEB / f"digest_{n:02d}.json", digests[i:i + CHUNK])
    market_items = items_for("market.1") + items_for("market.2")
    core.save_json(WEB / "market.json", [{"ref": f"m{i + 1}", "url": it["url"], "title": it["title"][:120],
                                          "text": excerpt(it["text"], 600)} for i, it in enumerate(market_items[:6])])
    state["web"] = {
        "cityAnswers": {f"{k[0]}|{k[1]}": v for k, v in city_answers.items()},
        "marketRefs": [{"ref": f"m{i + 1}", "url": it["url"], "engine": it["engine"]}
                       for i, it in enumerate(market_items[:6])],
        "marketSearch": "Deferred: fast run time budget" if FAST_MODE else market_q["market.1"][0],
        "exaCalls": core.load_json(WEB / "engine-usage.json", {}).get("exa", 0), "firecrawlCalls": core.load_json(WEB / "engine-usage.json", {}).get("firecrawl-uber", 0),
        "aiModeCalls": ai_calls, "aiModeCostUsd": ai_cost,
        "aiModeUnresolvedLeads": sum(bool((ai_records.get(l["id"]) or {}).get("error")) or l["id"] not in ai_records for l in worked if not l.get("platformOnly")) if FAST_MODE else 0,
        "researchWarning": ("Restaurant research comes from Google AI Mode (owner, menu, email and platform answers are sourced research leads to confirm on the call); city/market searches are deferred, not evidence of absence. "
            + (f"Google AI Mode failed for {sum(bool((ai_records.get(l['id']) or {}).get('error')) or l['id'] not in ai_records for l in worked if not l.get('platformOnly'))} restaurants after three attempts; their research is missing, not absent. "
               if any((ai_records.get(l["id"]) or {}).get("error") or l["id"] not in ai_records for l in worked if not l.get("platformOnly")) else "")) if FAST_MODE else ("Web research incomplete: a search provider is unavailable, out of credits, or has unresolved failures. Missing web information must be confirmed on the call." if list(WEB.glob("*-unavailable.json")) or core.load_json(WEB / "firecrawl-telemetry.json", {}).get("terminalFailures") else ""),
        "webResearchedLeads": sum(bool(l.get("refs")) for l in worked),
        "webEligibleLeads": len(worked), "speedTargetSeconds": TARGET_RUN_SECONDS if FAST_MODE else None,
        "firecrawlRetried": len(retry), "digests": n,
        "firecrawlCapacity": firecrawl_capacity_report(),
        "firecrawlSucceededQueries": sum(bool(v) for v in fc_ok.values()),
        "firecrawlUnresolvedQueries": sum(not v for v in fc_ok.values()),
    }
    core.save_json(WORK / "state.json", state)
    core.log(f"Web done in {time.time() - started:.0f} s: Google AI Mode {ai_calls} tool calls (${ai_cost:.3f}), "
             f"Exa {state['web']['exaCalls']}, Firecrawl {state['web']['firecrawlCalls']}; {len(digests)} leads with usable pages in {n} digest files "
             f"({WEB}/digest_NN.json) + {WEB}/market.json.")


# ---------------------------------------------------------------- render


def extractions():
    """The script's prefill first, then the agent's extract files on top, key by key: the agent
    only writes what it corrects or adds, and "" clears a prefilled value."""
    out = {lead_id: {**entry, "Research": dict(entry.get("Research") or {})}
           for lead_id, entry in (core.load_json(WEB / "prefill.json", {}) or {}).items()}
    for path in sorted(WEB.glob("extract_*.json")):
        data = core.load_json(path, {}) or {}
        if not isinstance(data, dict):
            continue
        for lead_id, entry in data.items():
            if not isinstance(entry, dict):
                continue
            merged = out.setdefault(lead_id, {})
            research = {**(merged.get("Research") or {}), **(entry.get("Research") or {})}
            merged.update(entry)
            merged["Research"] = {k: v for k, v in research.items() if v not in ("", None)}
    return out


def ref_lookup(lead, ref):
    for r in lead.get("refs") or []:
        if r["ref"] == ref:
            return r
    return None


def lead_fields(lead, ext, state):
    """The twelve Extra fields: [key, value, state, source, scope, search, engine]."""
    place, web_state = lead["place"], state.get("web", {})
    fields = []

    def from_model(key, value_keys, query_kind):
        e = ext.get(key) or {}
        value = " · ".join(str(e.get(k)).strip() for k in value_keys if str(e.get(k) or "").strip())
        ref = ref_lookup(lead, e.get("ref") or "")
        search = lead["searches"].get(query_kind, "")
        if value and ref:
            return {"key": key, "value": value, "state": source_state(place, ref["url"]),
                    "source": ref["url"], "scope": "lead", "search": search, "engine": ref["engine"]}
        return {"key": key, "value": "", "state": "NOT FOUND", "source": "", "scope": "lead",
                "search": search, "engine": ""}

    fields.append(from_model("Contact person", ["name", "role", "phone"], "operator"))
    email = ext.get("Public email") or {}
    ref = ref_lookup(lead, email.get("ref") or "")
    if email.get("value") and ref:
        fields.append({"key": "Public email", "value": email["value"], "state": source_state(place, ref["url"]),
                       "source": ref["url"], "scope": "lead", "search": lead["searches"]["operator"],
                       "engine": ref["engine"]})
    elif lead.get("emailFound"):
        found = lead["emailFound"]
        fields.append({"key": "Public email", "value": found["value"],
                       "state": source_state(place, found["source"]), "source": found["source"],
                       "scope": "lead", "search": lead["searches"]["operator"],
                       "engine": next((r["engine"] for r in lead["refs"] if r["url"] == found["source"]), "exa")})
    else:
        fields.append({"key": "Public email", "value": "", "state": "NOT FOUND", "source": "", "scope": "lead",
                       "search": lead["searches"]["operator"], "engine": ""})
    fields.append(from_model("Tenure & other locations", ["tenure", "otherLocations"], "operator"))
    fields.append(from_model("Best-seller dish", ["value"], "reputation"))
    fields.append(from_model("Average order volume", ["count", "value"], "reputation"))
    fields.append(from_model("Peak order hours", ["value"], "reputation"))
    answers = web_state.get("cityAnswers", {})
    for key in FIELD_KEYS[6:11]:
        akey = f"{lead.get('cuisineKey', '')}|{key}" if key == "Same-cuisine on Uber Eats" else f"{lead['cityKey']}|{key}"
        entry = answers.get(akey) or {}
        ans = entry.get("answer")
        if ans:
            fields.append({"key": key, "value": ans["value"], "state": "ASSUMED", "source": ans["source"],
                           "scope": "city", "search": entry.get("search", ""), "engine": ans["engine"]})
        else:
            fields.append({"key": key, "value": "", "state": "NOT FOUND", "source": "", "scope": "city",
                           "search": entry.get("search", "not searched: no cuisine in the input"), "engine": ""})
    bench = core.load_json(WEB / "market_extract.json", {}) or {}
    mref = next((m for m in web_state.get("marketRefs", []) if m["ref"] == bench.get("ref")), None)
    if bench.get("value") and mref:
        fields.append({"key": "Delivery vs on-site volume", "value": bench["value"], "state": "ASSUMED",
                       "source": mref["url"], "scope": "market", "search": web_state.get("marketSearch", ""),
                       "engine": mref["engine"]})
    else:
        fields.append({"key": "Delivery vs on-site volume", "value": "", "state": "NOT FOUND", "source": "",
                       "scope": "market", "search": web_state.get("marketSearch", ""), "engine": ""})
    return fields


def score_b(place, lead, fields, ext, checks):
    f = {x["key"]: x for x in fields}
    comps = {"Reachability": "", "Delivery Fit": "", "Demand Signal": "", "Competitive Position": "",
             "Zone Density": ""}
    comps["Reachability"] = str((10 if place["phone"] else 0) + (10 if f["Contact person"]["value"] else 0)
                                + (5 if f["Public email"]["value"] else 0))
    menu_read = bool(ext.get("menuTransportable") and ref_lookup(lead, ext.get("menuRef", "")))
    menu_insight = ext.get("Menu insight") or {}
    if menu_insight.get("drinkLed") is True and ref_lookup(lead, menu_insight.get("ref", "")):
        comps["Delivery Fit"] = "0"
    elif menu_read:
        comps["Delivery Fit"] = "20"
    elif place["takeout"] or place["delivery"]:
        comps["Delivery Fit"] = "15"
    elif "restaurant" in place["types"] or "food" in place["types"]:
        comps["Delivery Fit"] = "8"
    else:
        comps["Delivery Fit"] = "0"
    demand = core.components(place, None)["Demand Signal"]
    if ext.get("deliveryDemandQuote") and ref_lookup(lead, ext.get("deliveryDemandRef", "")):
        demand = "20"
    comps["Demand Signal"] = demand
    p = lead["platforms"]
    if p.get("uberEats"):
        comps["Competitive Position"] = "0"
    elif p.get("doorDash") or p.get("grubhub"):
        comps["Competitive Position"] = "20"
    elif lead.get("platformSearched"):
        comps["Competitive Position"] = "12"
    if lead.get("nearby") is not None:
        n = lead["nearby"]
        comps["Zone Density"] = str((15 if n >= 15 else 10 if n >= 8 else 5 if n >= 3 else 0) // 2)
    return comps


def engagement(place, lead, fields, ext, comps):
    f = {x["key"]: x for x in fields}
    status = place["status"]
    permanent = 25 if status == "OPERATIONAL" and place["hours"] else 15 if status == "OPERATIONAL" else 0
    menu = 25 if (ext.get("menuTransportable") and ref_lookup(lead, ext.get("menuRef", ""))) else (
        18 if place["takeout"] or place["delivery"] else 10 if "restaurant" in place["types"] else 0)
    p = lead["platforms"]
    posture = 0 if p.get("uberEats") else 25 if (p.get("doorDash") or p.get("grubhub")) else (
        15 if lead.get("platformSearched") else 5)
    demand = (5 if ext.get("deliveryDemandQuote") and ref_lookup(lead, ext.get("deliveryDemandRef", "")) else 0) + (5 if (lead.get("nearby") or 0) >= 8 else 0) + (
        5 if f["Same-cuisine on Uber Eats"]["value"] else 0)
    contact = f["Contact person"]
    reach = (10 if contact["value"] and re.search(r"\d{3}", contact["value"]) else 6 if contact["value"] else 0)
    if contact["value"] and contact["state"] == "ASSUMED":
        reach //= 2
    total = permanent + menu + posture + demand + reach
    band = "High" if total >= 70 else "Medium" if total >= 45 else "Low"
    if p.get("uberEats"):
        band = "Low"
    facts = [f"{status.lower().replace('_', ' ')}{' with published hours' if place['hours'] else ''} (Google Places)"]
    if p.get("uberEats"):
        facts.append("already live on Uber Eats")
    elif p.get("doorDash") or p.get("grubhub"):
        facts.append("on " + " and ".join(PLATFORMS[k][1] for k in ("doorDash", "grubhub") if p.get(k))
                     + " but not Uber Eats")
    elif lead.get("platformSearched"):
        facts.append("no delivery-platform storefront found")
    if contact["value"]:
        facts.append(f"named contact ({contact['state'].lower()})")
    rationale = f"{band}: " + "; ".join(facts) + "."
    sources = [place["mapsUrl"]] + [u for u in p.values() if u] + (
        [contact["source"]] if contact["source"] else [])
    return {"score": total, "band": band, "rationale": rationale[:300], "sources": sources}


def seller_fields(lead, row, ext):
    p = lead.get("place") or {}
    city, st = core.parse_address(p.get("address", ""))
    flags = []
    if lead.get("platformOnly"):
        flags.append("Unverified, platform only")
    elif p and lead.get("decision") != "REJECTED":
        if not lead["city"] or not lead["state"]:
            flags.append("Check location")
        elif not core.city_matches(lead["city"].split(",")[0], p.get("address", "")) or st != lead["state"]:
            flags.append("Different city found" if st == lead["state"] else "Check location")
        if core.name_score(lead["merchant"], p.get("name", "")) < .75:
            flags.append("Check name")
    if lead.get("severalPlaces"):
        flags.append("Several places")
    if p.get("status") == "CLOSED_PERMANENTLY":
        flags.append("Permanently closed")
    elif p.get("status") == "CLOSED_TEMPORARILY":
        flags.append("Temporarily closed")
    if is_non_restaurant(p):
        flags.append("Not a restaurant")
    types = p.get("types") or []
    if "food_truck" in types or "food_truck" in p.get("primaryType", ""):
        flags.append("Mobile")
    if p.get("delivery") and p.get("dineIn") is False:
        flags.append("Delivery only")
    if row.get("Duplicate Of"):
        flags.append("Duplicate in lead file")
    if row.get("Not on Eats") == "bloc":
        flags.append("Already on Uber Eats")
    reason, action = "", "Confirm the decision-maker and delivery setup on the call."
    if is_non_restaurant(p):
        reason, action = "Google lists a different business type rather than a restaurant.", "Skip this lead and correct the business in Salesforce."
    elif row.get("Deciding Criterion") == "Identity":
        reason = row.get("Identity Note") or "Google did not confirm this restaurant."
        action = "Check the name, city and phone in Salesforce."
        flags.append("Not found")
    elif "Permanently closed" in flags:
        reason, action = "Google marks this restaurant as permanently closed.", "Skip this lead."
    elif "Temporarily closed" in flags:
        reason, action = "Google marks this restaurant as temporarily closed; it is excluded from scoring until it reopens.", "Retry after reopening."
    elif "Not a restaurant" in flags:
        reason, action = "Google lists a different business type rather than a restaurant.", "Check the business in Salesforce."
    elif "Already on Uber Eats" in flags:
        reason, action = "A matching Uber Eats storefront was found for this restaurant.", "Check the existing Uber Eats account."
    elif lead.get("platformOnly"):
        reason, action = "A delivery-platform storefront was found, but Google has not confirmed the restaurant.", "Confirm the location and business identity on the call."
    elif "Different city found" in flags or "Check location" in flags:
        reason = row.get("Identity Note", "Google found the restaurant in a different location.")
        action = "Confirm the location on the call."
    elif row.get("Local") == "chk":
        reason = (lead.get("local") or ["", ""])[1] or "Several locations were found; confirm who makes delivery decisions."
    else:
        reason = "Google found this restaurant" + (" with takeout or delivery" if p.get("takeout") or p.get("delivery") else "") + "."
        if row.get("Not on Eats") == "ok":
            reason += " No Uber Eats listing was found in the completed searches."
        elif row.get("Not on Eats") == "chk":
            reason += " Delivery-app presence is still unknown."
    if not row.get("Deciding Criterion") == "Identity" and row.get("Verdict") != "NOT WORKABLE":
        insight = ext.get("Menu insight") or {}
        if insight.get("drinkLed") is True and ref_lookup(lead, insight.get("ref", "")):
            reason += " The sourced menu is mostly drinks, so delivery fit is low."
    def sourced(key):
        value = ext.get(key) or {}
        ref = ref_lookup(lead, value.get("ref", ""))
        return (str(value.get("value") or ""), ref["url"]) if ref else ("", "")
    about, about_url = sourced("About merchant")
    menu, menu_url = sourced("Menu insight")
    return {"Status Reason": reason, "Next Action": action, "Review Flags": json.dumps(list(dict.fromkeys(flags))),
            "Google Type": p.get("primaryType", "").replace("_", " ").capitalize(),
            "About Merchant": about, "About Source": about_url, "Menu Note": menu, "Menu Source": menu_url}


def render():
    state = core.load_json(WORK / "state.json")
    raw = core.load_json(WORK / "raw.json")
    if not state or "web" not in state:
        raise SystemExit("Run `run` then `web` first.")
    leads, run_date = state["leads"], state["runDate"]
    core.apply_overrides(leads)
    ext_all = extractions()
    ext_all = {l["id"]: sales.legacy_extraction(l, ext_all.get(l["id"], {})) for l in leads}
    template = TEMPLATE.read_text() if TEMPLATE.exists() else None
    pattern = r'(<script id="data" type="application/json">)(.*?)(</script>)'
    sample = json.loads(re.search(pattern, template, re.S).group(2)) if template else None
    lead_keys = list(sample["leads"][0]) if sample else []

    rows, dashboard, seen, engines = [], [], {}, []
    for lead in leads:
        row = {**raw["rows"][lead["row"]], **dict.fromkeys(core.EXTRA_COLUMNS + EXTRA_COLUMNS, "")}
        row["Build"], row["Run Date"] = BUILD, run_date
        if lead["skip"]:
            row.update({"Processed": "no", "Skip Reason": lead["skip"]})
            rows.append(row)
            continue
        place = lead.get("place")
        decision = lead["decision"]
        row.update({
            "Processed": "yes", "Identity Match": decision,
            "Identity Note": lead.get("identityNote") or lead["identity"][2],
            "Alternatives": " | ".join(lead.get("alternatives") or []),
            "Places API Calls": str(round(lead["calls"])), "Confidence": lead.get("confidence", "High"),
        })
        if place:
            row.update({"Place ID": place["id"], "Resolved Name": place["name"],
                        "Resolved Address": place["address"], "Resolved City": core.parse_address(place["address"])[0]})
        checks = dict.fromkeys(["Open", "Deliverable", "Local", "Unique", "Not on Eats"], "")
        comps = {"Reachability": "", "Delivery Fit": "", "Demand Signal": "", "Competitive Position": "",
                 "Zone Density": ""}
        extra = None
        if decision == "REJECTED" or not place:
            row.update({"Verdict": "NOT WORKABLE", "Deciding Criterion": "Identity", "Identity Match": "REJECTED",
                        "Read": "NOT WORKABLE (High): the Places listing is not this merchant."})
        else:
            ext = ext_all.get(lead["id"], {}) if lead.get("refs") is not None else {}
            researched = "refs" in lead
            fields = lead_fields(lead, ext, state) if researched else None
            recent = place["latestReview"] >= (dt.date.today() - dt.timedelta(days=365)).isoformat()
            status = place["status"]
            checks["Open"] = ("bloc" if status in {"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"} else "ok" if status == "OPERATIONAL" and (place["hours"] or recent) else "chk")
            menu_read = bool(ext.get("menuTransportable") and ref_lookup(lead, ext.get("menuRef", "")))
            food = "restaurant" in place["types"] or "food" in place["types"]
            if menu_read or place["takeout"] or place["delivery"]:
                checks["Deliverable"] = "ok"
            else:
                checks["Deliverable"] = "chk" if food else "chk"
            local = lead.get("local") or ("", "")
            checks["Local"] = local[0] or "chk"
            checks["Unique"] = "ok"
            platforms = lead.get("platforms") or {}
            if platforms.get("uberEats"):
                checks["Not on Eats"] = "bloc"
            elif researched and lead.get("platformSearched"):
                checks["Not on Eats"] = "ok"
            else:
                checks["Not on Eats"] = "chk"
            if place["id"] in seen:
                first = seen[place["id"]]
                checks["Unique"] = "chk"
                row["Duplicate Of"] = first["id"]
                row["Identity Note"] += f" Duplicate of {first['id']} ({' and '.join(dict.fromkeys([first['rep'], lead['rep']]))})."
            else:
                seen[place["id"]] = lead
            row.update({
                "Phone": place["phone"], "Website": place["website"], "Google Maps URL": place["mapsUrl"],
                "Business Status": status, "Takeout": core.yn(place["takeout"]), "Delivery": core.yn(place["delivery"]),
                "Dine In": core.yn(place["dineIn"]),
                "Rating": "" if place["rating"] is None else str(place["rating"]),
                "Review Count": "" if place["reviews"] is None else str(place["reviews"]),
                "Price Level": place["priceLevel"], "Opening Hours": place["hours"],
                "Restaurants Nearby": "" if lead.get("nearby") is None else str(lead["nearby"]),
            })
            row.update(core.call_window(place))
            gaps = []
            if fields:
                f = {x["key"]: x for x in fields}
                if not f["Contact person"]["value"]:
                    gaps.append("Who handles delivery-platform decisions?")
                if not f["Public email"]["value"]:
                    gaps.append("What is the best email for a follow-up?")
                if not any(platforms.values()):
                    gaps.append("Are you already on Uber Eats, DoorDash or Grubhub?")
                if not f["Best-seller dish"]["value"]:
                    gaps.append("Which dishes travel best for delivery?")
            else:
                gaps = core.BASE_GAPS[:]
            if checks["Open"] == "chk":
                gaps.insert(0, "Are you open, and what are your current hours?")
            if checks["Local"] == "chk":
                gaps.append("How many locations do you have, and who decides for all of them?")
            row["Gaps To Ask"] = " | ".join(gaps)
            if is_non_restaurant(place):
                checks["Deliverable"] = "bloc"
            blockers = [k for k, v in checks.items() if v == "bloc"]
            pending = [k for k, v in checks.items() if v == "chk"]
            if blockers:
                verdict, criterion = "NOT WORKABLE", blockers[0]
            elif pending:
                verdict, criterion = "TO VERIFY", pending[0]
            else:
                verdict, criterion = "WORKABLE", "Not on Eats"
            row.update({"Verdict": verdict, "Deciding Criterion": criterion})
            if fields:
                comps_all = score_b(place, lead, fields, ext, checks)
                eng = engagement(place, lead, fields, ext, comps_all)
            else:
                comps_all, eng = None, None
            if verdict != "NOT WORKABLE" and comps_all:
                comps = comps_all
                score = sum(int(v) for v in comps.values() if v)
                band = "P1" if score >= 70 else "P2" if score >= 45 else "P3"
                row.update({"Score": str(score), "Band": band})
                for key, value in comps.items():
                    row[key] = value
            flip = {"Not on Eats": "a live Uber Eats storefront would close it",
                    "Local": "confirming independent ownership would clear it",
                    "Open": "confirming current hours would clear it",
                    "Deliverable": "confirming takeout or delivery would clear it",
                    "Unique": "it duplicates another lead", "Identity": ""}.get(criterion, "")
            row["Read"] = f"{verdict} ({row['Confidence']}): {criterion} decides" + (f"; {flip}." if flip else ".")
            if fields:
                f = {x["key"]: x for x in fields}
                not_found = [x["key"] for x in fields if not x["value"]]
                row["Not Found Fields"] = " | ".join(not_found)
                plat_sources = [u for u in platforms.values() if u]
                contact = ext.get("Contact person") or {}
                tenure = ext.get("Tenure & other locations") or {}
                avg = ext.get("Average order volume") or {}
                row.update({
                    "On Uber Eats": "TRUE" if platforms.get("uberEats") else ("FALSE" if lead.get("platformSearched") else ""),
                    "On DoorDash": "TRUE" if platforms.get("doorDash") else ("FALSE" if lead.get("platformSearched") else ""),
                    "On Grubhub": "TRUE" if platforms.get("grubhub") else ("FALSE" if lead.get("platformSearched") else ""),
                    "Platform Source": " | ".join(plat_sources) if plat_sources else "NOT FOUND",
                    "Extra Contact Person": " ".join(str(contact.get(k) or "") for k in ("name", "role")).strip() if f["Contact person"]["value"] else "",
                    "Extra Contact Phone": str(contact.get("phone") or "") if f["Contact person"]["value"] else "",
                    "Extra Contact Source": f["Contact person"]["source"] or "NOT FOUND",
                    "Public Email": f["Public email"]["value"],
                    "Tenure": str(tenure.get("tenure") or "") if f["Tenure & other locations"]["value"] else "",
                    "Other Locations": str(tenure.get("otherLocations") or "") if f["Tenure & other locations"]["value"] else "",
                    "Tenure Source": f["Tenure & other locations"]["source"] or "NOT FOUND",
                    "Best Seller Dish": f["Best-seller dish"]["value"], "Best Seller Source": f["Best-seller dish"]["source"] or "NOT FOUND",
                    "Avg Order Count": str(avg.get("count") or "") if f["Average order volume"]["value"] else "",
                    "Avg Order Value": str(avg.get("value") or "") if f["Average order volume"]["value"] else "",
                    "Avg Order Source": f["Average order volume"]["source"] or "NOT FOUND",
                    "Peak Hours": f["Peak order hours"]["value"], "Peak Hours Source": f["Peak order hours"]["source"] or "NOT FOUND",
                    "City Population": f["Population"]["value"], "City Population Source": f["Population"]["source"] or "NOT FOUND",
                    "City Delivery Restaurants": f["Restaurants on delivery platforms"]["value"],
                    "City Delivery Restaurants Source": f["Restaurants on delivery platforms"]["source"] or "NOT FOUND",
                    "City Uber Couriers": f["Uber couriers in the area"]["value"],
                    "City Uber Couriers Source": f["Uber couriers in the area"]["source"] or "NOT FOUND",
                    "City Uber Eats Users": f["Uber Eats users in the area"]["value"],
                    "City Uber Eats Users Source": f["Uber Eats users in the area"]["source"] or "NOT FOUND",
                    "Same Cuisine On Uber Eats": f["Same-cuisine on Uber Eats"]["value"],
                    "Same Cuisine Source": f["Same-cuisine on Uber Eats"]["source"] or "NOT FOUND",
                    "Delivery vs Onsite Benchmark": f["Delivery vs on-site volume"]["value"],
                    "Delivery vs Onsite Source": f["Delivery vs on-site volume"]["source"] or "NOT FOUND",
                    "Engagement Score": str(eng["score"]), "Engagement Band": eng["band"],
                    "Engagement Rationale": eng["rationale"],
                    "Field Engines": " | ".join(f"{x['key']}={x['engine']}" for x in fields if x["value"]),
                    "Fields From Exa": str(sum(1 for x in fields if x["engine"] == "exa")),
                    "Fields From Firecrawl": str(sum(1 for x in fields if x["engine"] == "firecrawl")),
                    "Exa Calls": str(lead["webCalls"]["exa"]), "Firecrawl Calls": str(lead["webCalls"]["firecrawl"]),
                    "Extra Not Found": " | ".join(not_found),
                })
                for x in fields:
                    engines.append((x["key"], x["engine"], bool(x["value"]), x["search"]))
                extra = {
                    "engagement": eng,
                    "platforms": {k: ({"value": "Live storefront", "state": "VERIFIED", "source": platforms[k]}
                                      if platforms.get(k) else
                                      {"value": "Not listed" if lead.get("platformSearched") else "",
                                       "state": "ASSUMED" if lead.get("platformSearched") else "NOT FOUND",
                                       "source": ""}) for k in PLATFORMS},
                    "fields": fields,
                    "exaCalls": str(lead["webCalls"]["exa"]), "firecrawlCalls": str(lead["webCalls"]["firecrawl"]),
                    "notFound": " | ".join(not_found),
                }
            else:
                row["Not Found Fields"] = core.BASE_NOT_FOUND
        row.update(checks)
        rows.append(row)
        row.update(seller_fields(lead, row, ext_all.get(lead["id"], {})))
        research = sales.build_research(lead, row, ext_all.get(lead["id"], {}), core.parse_address)
        playbook, outreach = sales.build_sales(lead, row, research, run_date)
        row.update({"Research Brief": json.dumps(research, ensure_ascii=False),
                    "Sales Playbook": json.dumps(playbook, ensure_ascii=False),
                    "Outreach Email Subject": outreach["subject"] if outreach else "",
                    "Outreach Email Body": outreach["body"] if outreach else "",
                    "Outreach Personalization Sources": " | ".join(outreach["sources"]) if outreach else ""})
        if sample:
            item = core.dashboard_lead(lead, row, comps, checks, [k for k in lead_keys if k != "extra"])
            item["extra"] = extra or empty_extra()
            item.update(research=research, playbook=playbook, outreach=outreach)
            if row["Identity Match"] == "REJECTED":
                item["name"] = lead["merchant"]
                item["city"] = ", ".join(v for v in [lead["city"], lead["state"]] if v)
            item.update({"statusReason": row["Status Reason"], "action": row["Next Action"], "flags": json.loads(row["Review Flags"]),
                         "inputCity": lead["city"], "inputState": lead["state"], "googleType": row["Google Type"],
                         "localNote": (lead.get("local") or ["", ""])[1], "about": row["About Merchant"],
                         "aboutSource": row["About Source"], "cuisine": lead.get("cuisine", ""), "price": row["Price Level"],
                         "contacted": lead.get("contacted", ""), "platformOnly": bool(lead.get("platformOnly")),
                         "platformOnlySource": lead.get("platformOnlySource", ""), "menuNote": row["Menu Note"], "menuSource": row["Menu Source"]})
            dashboard.append(item)

    canonical = {}
    for item in dashboard:
        key = item["placeId"] or item["id"]
        if key in canonical:
            first = canonical[key]
            first["seller"] = " · ".join(dict.fromkeys(first["seller"].split(" · ") + [item["seller"]]))
            first.setdefault("duplicateLeadIds", [first["id"]]).append(item["id"])
            if "Duplicate in lead file" not in first["flags"]:
                first["flags"].append("Duplicate in lead file")
        else:
            canonical[key] = item
    dashboard = list(canonical.values())
    dashboard.sort(key=lambda l: (l["callWindow"] or "99", -int(l["score"] or 0), l["name"]))
    for rank, item in enumerate(dashboard, 1):
        item["rank"] = rank
    with open(APP / "leads.csv", "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=raw["header"] + core.EXTRA_COLUMNS + EXTRA_COLUMNS,
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    web_state = state["web"]
    if sample:
        meta = dict.fromkeys(sample["meta"], 0)
        meta.update(
            generatedAt=f"{run_date} (Places + Exa)", total=len(raw["rows"]), worked=len(dashboard),
            reachable=sum(bool(l["phone"]) for l in dashboard),
            workable=sum(l["verdict"] == "WORKABLE" for l in dashboard),
            toVerify=sum(l["verdict"] == "TO VERIFY" for l in dashboard),
            dropped=sum(l["verdict"] == "NOT WORKABLE" for l in dashboard),
            placesCalls=sum(int(r["Places API Calls"] or 0) for r in rows if r["Processed"] == "yes"),
            exaCalls=web_state["exaCalls"], firecrawlCalls=web_state["firecrawlCalls"],
            cities=len({l["cityKey"] for l in leads if l.get("cityKey")}),
            researchWarning=web_state.get("researchWarning", ""), processedRows=sum(r["Processed"] == "yes" for r in rows),
        )
        payload = json.dumps({"meta": meta, "leads": dashboard}, ensure_ascii=False).replace("<", "\\u003c")
        html = re.sub(pattern, lambda m: m.group(1) + payload + m.group(3), template, count=1, flags=re.S)
        (APP / "output.html").write_text(html)
    pdf_error = write_pdf(engines, web_state, run_date, len(dashboard))
    write_summary_b(rows, dashboard, engines, web_state, pdf_error)
    core.log(f"Rendered {len(rows)} rows, {len(dashboard)} processed leads." + (f" PDF ERROR: {pdf_error}" if pdf_error else ""))


def empty_extra():
    return {"engagement": {"score": "", "band": "", "rationale": "", "sources": []},
            "platforms": {k: {"value": "", "state": "NOT FOUND", "source": ""} for k in PLATFORMS},
            "fields": [{"key": k, "value": "", "state": "NOT FOUND", "source": "", "scope": FIELD_SCOPE[k],
                        "search": "not searched: lead dropped before the web layer", "engine": ""}
                       for k in FIELD_KEYS],
            "exaCalls": "0", "firecrawlCalls": "0", "notFound": ""}


def engine_stats(engines):
    per = {k: {"aimode": 0, "exa": 0, "firecrawl": 0, "neither": 0} for k in FIELD_KEYS}
    for key, engine, filled, _search in engines:
        per[key][engine if filled and engine else "neither"] += 1
    total = {e: sum(v[e] for v in per.values()) for e in ("aimode", "exa", "firecrawl", "neither")}
    return per, total


def write_pdf(engines, web_state, run_date, batch):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as error:
        return str(error)
    per, total = engine_stats(engines)
    retried = web_state.get("firecrawlRetried", 0)
    recovery = total["firecrawl"]
    rate = f"{recovery}/{retried} Exa-empty searches answered" if retried else "no Exa-empty search"
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(PDF_PATH), pagesize=A4, title="Engine analysis")
    filled = total["aimode"] + total["exa"] + total["firecrawl"]
    margin = total["exa"] - total["firecrawl"]
    verdict = (f"Google AI Mode filled {total['aimode']} of {filled} answered questions ({web_state.get('aiModeCalls', 0)} tool calls, "
               f"${web_state.get('aiModeCostUsd', 0):.2f} billed by DataForSEO, {web_state.get('aiModeUnresolvedLeads', 0)} restaurants left incomplete after three waves)."
               if web_state.get("aiModeCalls") else
               f"Exa filled {total['exa']} of {filled} answered questions and Firecrawl {total['firecrawl']}, "
               f"a margin of {margin} for Exa. Firecrawl's recovery: {rate}.")
    table = [["Question", "AI Mode", "Exa", "Firecrawl", "Neither"]] + [
        [k, str(v["aimode"]), str(v["exa"]), str(v["firecrawl"]), str(v["neither"])] for k, v in per.items()]
    t = Table(table, colWidths=[200, 60, 55, 60, 55])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.black), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    story = [
        Paragraph("Engine analysis: Google AI Mode, Exa and Firecrawl", styles["Title"]),
        Paragraph(f"Run date {run_date} · batch of {batch} processed leads", styles["Normal"]),
        Spacer(1, 10),
        Paragraph(f"Questions filled: Google AI Mode {total['aimode']} · Exa {total['exa']} · Firecrawl {total['firecrawl']} · neither {total['neither']}",
                  styles["Normal"]),
        Paragraph(f"Searches: Exa {web_state.get('exaCalls', 0)} · Firecrawl {web_state.get('firecrawlCalls', 0)} · "
                  f"Firecrawl recovery: {rate}", styles["Normal"]),
        Paragraph("Fast mode researches every confirmed restaurant with Google AI Mode (ai_mode_research on google-places-oauth, "
                  "through DataForSEO): one question on the twelve points, one on delivery storefronts, up to three waves for failed calls. "
                  "City and market searches are deferred. Missing research is incomplete, not evidence of absence.", styles["Normal"]),
        Spacer(1, 10), t, Spacer(1, 12), Paragraph(verdict, styles["Normal"]),
    ]
    doc.build(story)
    return ""


def write_summary_b(rows, dashboard, engines, web_state, pdf_error):
    processed = [r for r in rows if r["Processed"] == "yes"]
    alive = [r for r in processed if r["Verdict"] != "NOT WORKABLE"]
    _per, total = engine_stats(engines)
    gaps = {}
    for r in processed:
        for key in filter(None, r.get("Extra Not Found", "").split(" | ")):
            gaps[key] = gaps.get(key, 0) + 1
    top = sorted((l for l in dashboard if l["phone"] and l["verdict"] != "NOT WORKABLE" and l["score"] != ""),
                 key=lambda l: (-int(l["score"]), l["callWindow"]))[:3]
    summary = {
        "rows": len(rows), "worked": len(processed), "reps": len({r.get("Sales Rep", "") for r in processed}),
        "workable": sum(r["Verdict"] == "WORKABLE" for r in processed),
        "toVerify": sum(r["Verdict"] == "TO VERIFY" for r in processed),
        "notWorkable": sum(r["Verdict"] == "NOT WORKABLE" for r in processed),
        "identityRejected": sum(r["Identity Match"] == "REJECTED" for r in processed),
        "P1": sum(r["Band"] == "P1" for r in alive), "P2": sum(r["Band"] == "P2" for r in alive),
        "P3": sum(r["Band"] == "P3" for r in alive),
        "platformResolved": sum(r["On Uber Eats"] in ("TRUE", "FALSE") for r in processed),
        "onUberEats": sum(r["On Uber Eats"] == "TRUE" for r in processed),
        "onDoorDashOrGrubhubOnly": sum(r["On Uber Eats"] != "TRUE" and "TRUE" in (r["On DoorDash"], r["On Grubhub"])
                                       for r in processed),
        "topExtraGaps": sorted(gaps.items(), key=lambda kv: -kv[1])[:3],
        "engagement": {b: sum(r["Engagement Band"] == b for r in processed) for b in ("High", "Medium", "Low")},
        "topCalls": [{"rep": l["seller"], "name": l["name"], "phone": l["phone"], "score": l["score"],
                      "pht": l["callWindow"]} for l in top],
        "exaFilled": total["exa"], "firecrawlRecovered": total["firecrawl"],
        "firecrawlRetried": web_state.get("firecrawlRetried", 0),
        "placesCalls": sum(int(r["Places API Calls"] or 0) for r in processed),
        "exaCalls": web_state.get("exaCalls", 0), "firecrawlCalls": web_state.get("firecrawlCalls", 0),
        "pdfError": pdf_error, "elapsedSeconds": core.elapsed(),
        "researchWarning": web_state.get("researchWarning", ""), "uniqueMerchants": len(dashboard),
        "researchChecklists": len(dashboard),
        "researchAnswersWithSources": sum(l["research"]["coverage"] for l in dashboard),
        "namedDecisionMakers": sum(bool(l["research"].get("owner")) for l in dashboard),
        "menuUSPs": sum(bool(l["research"].get("menuUSP")) for l in dashboard),
        "bestSellers": sum(bool(l["research"].get("bestSeller")) for l in dashboard),
        "interestingFacts": sum(l["research"]["factsFound"] for l in dashboard),
        "salesPlaybooks": sum(bool(l["playbook"].get("available")) for l in dashboard),
        "outreachDrafts": sum(bool(l.get("outreach")) for l in dashboard),
        "personalizedOutreachWithSources": sum(bool((l.get("outreach") or {}).get("sources")) for l in dashboard),
        "emailsSent": 0, "emailMode": "copy_only",
        "webResearchedLeads": web_state.get("webResearchedLeads", 0),
        "webEligibleLeads": web_state.get("webEligibleLeads", 0),
        "speedTargetSeconds": web_state.get("speedTargetSeconds"),
        "firecrawlSucceededQueries": web_state.get("firecrawlSucceededQueries", 0),
        "firecrawlUnresolvedQueries": web_state.get("firecrawlUnresolvedQueries", 0),
        "firecrawlCapacity": {k:v for k,v in web_state.get("firecrawlCapacity", {}).items() if k not in {"waveMeasurements", "firstThrottle"}},
    }
    core.save_json(WORK / "summary.json", summary)


def check():
    raw = core.load_json(WORK / "raw.json")
    errors = []
    csv_path, html_path = APP / "leads.csv", APP / "output.html"
    if not csv_path.exists():
        return fail(["leads.csv missing"])
    data = csv_path.read_bytes()
    if not data.startswith(b"\xef\xbb\xbf"):
        errors.append("leads.csv has no UTF-8 BOM")
    import io
    table = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    header = table[0]
    if header != raw["header"] + core.EXTRA_COLUMNS + EXTRA_COLUMNS:
        errors.append("leads.csv header differs from the specification (47 core + 39 Extra columns)")
    if any(len(r) != len(header) for r in table[1:]):
        errors.append("leads.csv has ragged rows")
    if len(table) - 1 != len(raw["rows"]):
        errors.append(f"leads.csv has {len(table) - 1} rows for {len(raw['rows'])} input rows")
    processed = sum(1 for r in table[1:] if r[header.index("Processed")] == "yes")
    for r in table[1:]:
        row = dict(zip(header, r))
        for col in EXTRA_COLUMNS:
            if col.endswith("Source") and col != "Platform Source":
                value_col = {"Extra Contact Source": "Extra Contact Person", "Tenure Source": "Tenure",
                             "Best Seller Source": "Best Seller Dish", "Avg Order Source": "Avg Order Count",
                             "Peak Hours Source": "Peak Hours", "Same Cuisine Source": "Same Cuisine On Uber Eats",
                             "Delivery vs Onsite Source": "Delivery vs Onsite Benchmark"}.get(col, col[:-7])
                value_col = {"About Source": "About Merchant", "Menu Source": "Menu Note"}.get(col, value_col)
                if row.get(value_col) and not row[col].startswith("http"):
                    errors.append(f"{row['Lead ID']}: {value_col} has no source URL")
    if TEMPLATE.exists():
        template = TEMPLATE.read_text()
        if not html_path.exists():
            errors.append("output.html missing")
        else:
            html = html_path.read_text()
            pattern = r'<script id="data" type="application/json">(.*?)</script>'
            doc = json.loads(re.search(pattern, html, re.S).group(1))
            represented = sum(len(l.get("duplicateLeadIds", [l["id"]])) for l in doc["leads"])
            if represented != processed:
                errors.append(f"dashboard represents {represented} leads for {processed} processed rows")
            strip = lambda s: re.sub(pattern, "", s, flags=re.S)
            if strip(html) != strip(template):
                errors.append("output.html differs from the template outside the data block")
            for lead in doc["leads"]:
                if [q["question"] for q in lead.get("research", {}).get("checklist", [])] != sales.QUESTIONS:
                    errors.append(f"{lead['id']}: research checklist not the twelve requested questions")
                outreach = lead.get("outreach")
                if outreach:
                    if lead["verdict"] == "NOT WORKABLE" or outreach.get("mode") != "copy_only":
                        errors.append(f"{lead['id']}: outreach must be copy-only and excluded for dropped leads")
                    expected = sales.EMAIL_BODY.format(merchant=(lead["research"].get("owner") or {}).get("value", "").split(" — ")[0] or f"Team {lead['name']}",
                                                       rep=lead["seller"].split(" · ")[0] or "[YOUR NAME]", personalization=outreach["personalization"])
                    if outreach["body"] != expected:
                        errors.append(f"{lead['id']}: email differs from Camille's first template")
                for q in lead.get("research", {}).get("checklist", []):
                    if not q.get("value"):
                        errors.append(f"{lead['id']}: unanswered checklist question must say Not publicly available")
                keys = [f["key"] for f in lead["extra"]["fields"]]
                if keys != FIELD_KEYS:
                    errors.append(f"{lead['id']}: Extra fields not the twelve in order")
                if any(not isinstance(v, str) for v in lead["components"].values()):
                    errors.append(f"{lead['id']}: non-string component")
                for f in lead["extra"]["fields"]:
                    if f["value"] and not f["source"].startswith("http"):
                        errors.append(f"{lead['id']}: {f['key']} has a value without a source URL")
                if lead["verdict"] != "NOT WORKABLE" and lead["score"] != "" and lead["score"] != sum(
                        int(v) for v in lead["components"].values() if v):
                    errors.append(f"{lead['id']}: score is not the sum of its components")
    else:
        errors.append("template document output.html missing: HTML skipped")
    if not PDF_PATH.exists():
        errors.append("engine-analysis.pdf missing (send the email with the CSV alone and quote the PDF error)")
    return fail(errors) if errors else ok()


def fail(errors):
    core.log("CHECK FAILED:\n- " + "\n- ".join(errors[:20]))
    return False


def ok():
    core.log("CHECK PASSED")
    return True


def prepare(input_path):
    """Run Places + bounded web together, before model review can consume its allowance.

    Ambiguous identities are excluded from web searches. Restore REVIEW afterwards so
    the existing human/model judgment still applies at rendering, without a second web pass.
    """
    core.research(input_path)
    initial = core.load_json(WORK / "state.json")
    pending = {l["id"] for l in initial["leads"] if l.get("decision") == "REVIEW"}
    web_steps()
    state = core.load_json(WORK / "state.json")
    for lead in state["leads"]:
        if lead["id"] in pending:
            lead["decision"] = "REVIEW"
            lead["identityNote"] = ""
            lead.setdefault("refs", [])
            lead.setdefault("searches", {k: "Deferred: identity requires review" for k in ("platform", "operator", "reputation")})
            lead.setdefault("webCalls", {"exa": 0, "firecrawl": 0})
            lead.setdefault("platforms", {k: None for k in PLATFORMS})
            lead.setdefault("emailFound", None)
            lead.setdefault("platformSearched", False)
            lead.setdefault("cityKey", "")
            lead.setdefault("cuisine", "")
    core.save_json(WORK / "state.json", state)
    review = core.load_json(WORK / "review.json", [])
    by_id = {l["id"]: l for l in initial["leads"]}
    for entry in review:
        lead = by_id[entry["leadId"]]
        entry["inputAnchors"] = {k: lead.get(k, "") for k in ("inputPhone", "inputWebsite", "inputAddress")}
        options = ([lead.get("place")] if lead.get("place") else []) + lead.get("candidates", [])
        for candidate in entry["candidates"]:
            p = next((p for p in options if p and p["id"] == candidate["placeId"]), {})
            candidate.update(phone=p.get("phone", ""), website=p.get("website", ""))
    core.log("IDENTITY REVIEW " + json.dumps(review, ensure_ascii=False))
    for path in sorted(WEB.glob("digest_*.json")):
        core.log(path.name + " " + path.read_text())
    core.log("market.json " + (WEB / "market.json").read_text())
    core.log("PREPARED: write overrides and extractions from the printed review/digests, then render. Do not repeat web or inspect raw/state files.")


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "prepare":
        if len(sys.argv) < 3:
            raise SystemExit("Usage: lead_pipeline_b.py prepare <input file>")
        prepare(sys.argv[2])
        return
    if command == "run":
        if len(sys.argv) < 3:
            raise SystemExit("Usage: lead_pipeline_b.py run <input file>")
        core.research(sys.argv[2])
        review = core.load_json(WORK / "review.json", [])
        core.log(f"PLACES DONE. REVIEW {len(review)} ambiguous identities in {WORK / 'review.json'}; "
                 "write overrides.json, then run `web`.")
        return
    if command == "web":
        web()
        return
    if command == "render":
        render()
    elif command != "check":
        raise SystemExit(__doc__)
    passed = check()
    core.log("SUMMARY " + json.dumps(core.load_json(WORK / "summary.json", {}), ensure_ascii=False))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
