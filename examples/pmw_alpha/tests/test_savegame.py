from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from examples.pmw_alpha.savegame import (SAVE_SCHEMA, SaveGameError, SingleSlotSave,
                                         inspect_save, load_game, save_game)


class _Session:
    _registry = object()

    def export_save_metadata(self):
        return {"current_area": "mist_camp", "event_log": ["rested"]}


class SaveGameTests(TestCase):
    def test_round_trip_delegates_world_and_registry_to_gameplay_checkpoint(self):
        checkpoint = {
            "schema": "pmw-gameplay-checkpoint-v0.4",
            "world": {"world_id": "alpha"}, "blueprints": [],
            "runtime_config": {}, "payload_sha256": "gameplay-digest",
        }
        restored_runtime = object()
        with TemporaryDirectory() as directory, \
                patch("examples.pmw_alpha.savegame.save_registry_checkpoint") as save_checkpoint, \
                patch("examples.pmw_alpha.savegame.load_registry_checkpoint", return_value=restored_runtime) as load_checkpoint:
            def write_checkpoint(path, registry):
                self.assertIs(registry, _Session._registry)
                Path(path).write_text(json.dumps(checkpoint), encoding="utf-8")
                return "gameplay-digest"

            save_checkpoint.side_effect = write_checkpoint
            slot = SingleSlotSave(directory)
            summary = slot.save(_Session())
            self.assertTrue(slot.exists())
            self.assertEqual(summary.metadata["current_area"], "mist_camp")
            self.assertEqual(inspect_save(slot.path).payload_sha256, summary.payload_sha256)

            result = slot.load(object(), lambda runtime, metadata: (runtime, metadata))
            self.assertIs(result[0], restored_runtime)
            self.assertEqual(result[1], {"current_area": "mist_camp", "event_log": ["rested"]})
            load_checkpoint.assert_called_once()

    def test_tampering_metadata_is_rejected_before_runtime_restore(self):
        with TemporaryDirectory() as directory, patch(
                "examples.pmw_alpha.savegame.save_registry_checkpoint") as save_checkpoint:
            save_checkpoint.side_effect = lambda path, _: Path(path).write_text(json.dumps({"checkpoint": True}), encoding="utf-8")
            path = Path(directory) / "slot.json"
            save_game(path, _Session())
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["schema"], SAVE_SCHEMA)
            raw["metadata"]["current_area"] = "ash_observatory"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with patch("examples.pmw_alpha.savegame.load_registry_checkpoint") as load_checkpoint:
                with self.assertRaisesRegex(SaveGameError, "hash mismatch"):
                    load_game(path, compiled=object(), restore=lambda *_: None)
                load_checkpoint.assert_not_called()

    def test_rejects_non_json_session_metadata_and_nested_slot_names(self):
        class BadSession(_Session):
            def export_save_metadata(self):
                return {"bad": {1, 2}}

        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SaveGameError, "JSON-safe"):
                save_game(Path(directory) / "slot.json", BadSession())
            with self.assertRaises(ValueError):
                SingleSlotSave(directory, "nested/slot.json")
