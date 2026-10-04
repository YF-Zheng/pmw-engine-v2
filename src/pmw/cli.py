from __future__ import annotations

import argparse
import json

from .engine import Engine
from .io import load_event, load_laws, load_world, save_world


def main() -> None:
    parser = argparse.ArgumentParser(description="PMW Engine v2 event runner")
    parser.add_argument("--world", required=True, help="Path to a v2 world JSON document")
    parser.add_argument("--laws", required=True, help="Path to a v2 law JSON document")
    parser.add_argument("--event", required=True, help="Path to an event JSON document")
    parser.add_argument("--out", help="Optional output world path")
    args = parser.parse_args()

    world = load_world(args.world)
    result = Engine(load_laws(args.laws)).run_event(world, load_event(args.event))
    print(json.dumps({"changed": result.changed, "laws": result.triggered_law_ids, "events": result.processed_event_ids, "conflicts": result.conflicts}, ensure_ascii=False, indent=2))
    if args.out:
        save_world(args.out, world)
    else:
        print(json.dumps(world.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
