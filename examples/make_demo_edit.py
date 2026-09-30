"""Create a hash-bound edit example from a freshly generated multi-quote workbook."""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    patch = {
        "source_sha256": hashlib.sha256(args.workbook.read_bytes()).hexdigest(),
        "changes": [{"sheet": "Compact", "cell": "E6", "expected": 4, "value": 6}],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(patch, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
