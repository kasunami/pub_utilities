#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request


DEFAULT_MODEL = "gemini-3-pro-preview"
DEFAULT_PROMPT = "Whatup, Dawg??"


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def looks_like_key(value):
    # Basic sanity: no whitespace, plausible length/charset.
    return re.fullmatch(r"[A-Za-z0-9_\-]{20,}", value) is not None


def build_payload(prompt):
    return {"contents": [{"parts": [{"text": prompt}]}]}


def run_request(key, model, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": key,
        "Content-Type": "application/json",
    }
    data = json.dumps(build_payload(prompt)).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return body, str(resp.getcode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return body, str(exc.code)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc.reason}") from exc


def is_exhausted(body, http_code):
    if http_code == "429":
        return True
    lowered = body.lower()
    return "resource_exhausted" in lowered or "quota" in lowered


def extract_response_text(body):
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()

    if isinstance(payload, dict):
        candidates = payload.get("candidates") or []
        if candidates:
            content = candidates[0].get("content") or {}
            parts = content.get("parts") or []
            if parts and isinstance(parts[0], dict):
                text = parts[0].get("text")
                if isinstance(text, str):
                    return text.strip()
        error = payload.get("error") or {}
        message = error.get("message")
        if isinstance(message, str):
            return message.strip()

    return body.strip()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Check Gemini API keys for validity and remaining quota.",
        epilog=(
            "Input can be a file of keys (one per line) or a single key string. "
            "Use --key for a single key if you prefer flags."
        ),
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to a key file (one per line), or a single API key string.",
    )
    parser.add_argument(
        "-k",
        "--key",
        help="Single API key string to check (alternative to the positional input).",
    )
    parser.add_argument(
        "-m",
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model ID to use (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "-p",
        "--prompt",
        default=DEFAULT_PROMPT,
        help=(
            "Prompt text to send as a test request "
            f"(default: {DEFAULT_PROMPT})."
        ),
    )
    parser.add_argument(
        "-w",
        "--max-workers",
        type=int,
        default=4,
        help="Maximum concurrent requests to run (default: 4).",
    )
    parser.add_argument(
        "--min-interval",
        type=float,
        default=1.0,
        help="Minimum seconds between starting requests (default: 1.0).",
    )
    return parser.parse_args()


def load_keys(args):
    if args.input and args.key:
        die("provide either a positional input or --key, not both")
    if not args.input and not args.key:
        die("provide a key file or a single key (positional or --key)")

    if args.key:
        return [args.key]

    if os.path.isfile(args.input):
        with open(args.input, "r", encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f]
        if not lines:
            die("file is empty")
        return lines

    return [args.input]

def validate_keys(lines):
    for i, line in enumerate(lines, start=1):
        if line.strip() == "":
            die(f"line {i} is empty; each line must contain a single API key")
        if line != line.strip() or " " in line or "\t" in line:
            die(f"line {i} contains whitespace; each line must contain a single API key")
        if not looks_like_key(line):
            die(f"line {i} does not look like an API key")

    return lines


class RateLimiter:
    def __init__(self, min_interval):
        self.min_interval = max(0.0, min_interval)
        self._lock = threading.Lock()
        self._last_time = 0.0

    def wait(self):
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            next_time = self._last_time + self.min_interval
            if now < next_time:
                time.sleep(next_time - now)
                now = next_time
            self._last_time = now


def check_key(index, key, model, prompt, rate_limiter):
    rate_limiter.wait()
    body, http_code = run_request(key, model, prompt)
    exhausted = is_exhausted(body, http_code)
    is_ok = http_code == "200" and not exhausted
    response_text = extract_response_text(body)
    return {
        "index": index,
        "key": key,
        "is_ok": is_ok,
        "response_text": response_text,
    }


def main():
    args = parse_args()
    keys = validate_keys(load_keys(args))

    if args.max_workers < 1:
        die("--max-workers must be at least 1")
    if args.min_interval < 0:
        die("--min-interval must be >= 0")
    total = len(keys)
    passed = 0
    failed = 0
    active_keys = []
    rate_limiter = RateLimiter(args.min_interval)
    max_workers = min(args.max_workers, total)

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max_workers
    ) as executor:
        futures = {}
        for i, key in enumerate(keys, start=1):
            future = executor.submit(
                check_key, i, key, args.model, args.prompt, rate_limiter
            )
            futures[future] = (i, key)
        for future in concurrent.futures.as_completed(futures):
            index, key = futures[future]
            try:
                result = future.result()
                is_ok = result["is_ok"]
                response_text = result["response_text"]
            except Exception as exc:
                is_ok = False
                response_text = str(exc)

            if is_ok:
                passed += 1
                active_keys.append(key)
                status = "PASS"
            else:
                failed += 1
                status = "FAIL"

            print(f"[{index}/{total}] pass={passed} fail={failed} status={status}")
            print(f"'{key}': '{response_text}'")

    if active_keys:
        print("Active keys with remaining usage:")
        for k in active_keys:
            print(k)
    else:
        print("All keys have been exhausted.")


if __name__ == "__main__":
    main()
