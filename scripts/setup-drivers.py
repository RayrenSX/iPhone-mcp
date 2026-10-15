"""Headless setup: JSON status on stdout, human actions belong to the caller."""
import argparse
import json

from iphonemirror_mcp.runtime import RuntimeClient

parser = argparse.ArgumentParser()
parser.add_argument("--device-id")
parser.add_argument("--proxy")
args = parser.parse_args()
jobs = RuntimeClient().setup
status = jobs.begin(device_id=args.device_id, proxy=args.proxy)
previous = None
while True:
    serialized = json.dumps(status, ensure_ascii=True)
    if serialized != previous:
        print(serialized, flush=True)
        previous = serialized
    if status["state"] != "running":
        break
    status = jobs.status(status["jobId"], after_revision=status["revision"], timeout=20)
raise SystemExit(0 if status["state"] == "completed" else 2)
