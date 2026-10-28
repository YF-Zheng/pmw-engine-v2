from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import math
import tempfile
import unittest

from pmw import Event, WorldState, load_world, save_world

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.dynamics import (
    WORLD_TICK_EVENT,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.processes import (
    PROCESS_COMPONENT,
    PROCESS_START_EVENT,
    ConversionPort,
    ProcessController,
    ProcessLimits,
    ProcessProfile,
    ProcessTemplate,
    StockBinding,
    StockRef,
    build_process_laws,
    instantiate_process,
    stock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    build_runtime,
    clock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.transactions import (
    stage_gameplay_session,
)


def _template(
    *,
    template_id: str = "generic_conversion",
    input_coefficient: float = 2.0,
    output_coefficient: float = 3.0,
    input_unit: str = "wood",
    output_unit: str = "board",
    rate: float = 1.0,
    duration: int = 4,
    maximum_duration: int = 8,
) -> ProcessTemplate:
    return ProcessTemplate(
        template_id,
        (ConversionPort("feed", input_coefficient, input_unit),),
        (ConversionPort("product", output_coefficient, output_unit),),
        rate,
        duration,
        rate * 10,
        maximum_duration,
    )


def _profile(
    profile_id: str,
    template: ProcessTemplate,
    input_id: str,
    output_id: str,
    *,
    owner: str = "factory_owner",
    rate: float | None = None,
    duration: int | None = None,
) -> ProcessProfile:
    return ProcessProfile(
        profile_id,
        template,
        f"process_{profile_id}",
        owner,
        (StockBinding("feed", StockRef(input_id)),),
        (StockBinding("product", StockRef(output_id)),),
        rate,
        duration,
    )


def _session(
    profiles: tuple[ProcessProfile, ...],
    stocks: dict[str, tuple[float, float, str]],
    *,
    world_id: str = "process_world",
):
    entities = {
        "pmw:v04:clock": clock_entity(),
        **{
            profile.process_entity_id: instantiate_process(profile)
            for profile in profiles
        },
        **{
            stock_id: stock_entity(
                stock_id, amount=amount, capacity=capacity, unit=unit
            )
            for stock_id, (amount, capacity, unit) in stocks.items()
        },
    }
    world = WorldState(world_id, entities=entities)
    laws = build_process_laws(profiles)
    return build_runtime(world, extra_laws=laws)


def _component(session, profile: ProcessProfile) -> dict:
    return session.state.entities[profile.process_entity_id].components[PROCESS_COMPONENT]


def _amount(session, entity_id: str) -> float:
    return session.state.entities[entity_id].components["stock"]["amount"]


class ProcessCompilationTests(unittest.TestCase):
    def test_two_named_profiles_share_one_generic_compiler_and_keep_ratios(self):
        template = _template()
        saw = _profile("saw_line", template, "logs", "planks")
        press = _profile("press_line", template, "ore", "ingots")
        laws = build_process_laws((press, saw))
        ids = {law["id"] for law in laws}
        self.assertIn("pmw.v04.sandbox.process.saw_line.convert", ids)
        self.assertIn("pmw.v04.sandbox.process.press_line.convert", ids)

        session = _session(
            (saw, press),
            {
                "logs": (10.0, 20.0, "wood"),
                "planks": (0.0, 20.0, "board"),
                "ore": (10.0, 20.0, "wood"),
                "ingots": (0.0, 20.0, "board"),
            },
        )
        controller = ProcessController((saw, press))
        controller.start(session, saw.id, owner="factory_owner")
        controller.start(session, press.id, owner="factory_owner")
        tick = advance_world_tick(session)

        self.assertEqual(tick.step, 1)
        self.assertEqual(_amount(session, "logs"), 8.0)
        self.assertEqual(_amount(session, "planks"), 3.0)
        self.assertEqual(_amount(session, "ore"), 8.0)
        self.assertEqual(_amount(session, "ingots"), 3.0)
        self.assertEqual(_component(session, saw)["elapsed_ticks"], 1)
        self.assertEqual(_component(session, saw)["progress"], 0.25)

    def test_conversion_is_one_event_commit_batch(self):
        profile = _profile("batch_line", _template(), "logs", "planks")
        session = _session(
            (profile,),
            {
                "logs": (10.0, 20.0, "wood"),
                "planks": (0.0, 20.0, "board"),
            },
        )
        controller = ProcessController((profile,))
        controller.start(session, profile.id, owner="factory_owner")
        tick = advance_world_tick(session)

        addresses = set()
        for event_trace in tick.event_result.trace.events:
            if event_trace.event.type != WORLD_TICK_EVENT:
                continue
            for commit in event_trace.commits:
                current = {str(delta.address) for delta in commit.state_deltas}
                if "entity:logs/stock/amount" in current and "entity:planks/stock/amount" in current:
                    addresses = current
                    break
        self.assertIn("entity:logs/stock/amount", addresses)
        self.assertIn("entity:planks/stock/amount", addresses)


class ProcessExecutionTests(unittest.TestCase):
    def test_shortage_pauses_without_underflow_and_saturation_loses_nothing(self):
        starved = _profile(
            "starved_line",
            _template(input_coefficient=2.0, output_coefficient=3.0, duration=4),
            "feed",
            "product",
        )
        starved_session = _session(
            (starved,),
            {
                "feed": (2.0, 10.0, "wood"),
                "product": (0.0, 10.0, "board"),
            },
        )
        controller = ProcessController((starved,))
        controller.start(starved_session, starved.id, owner="factory_owner")
        advance_world_tick(starved_session)
        self.assertEqual(_amount(starved_session, "feed"), 0.0)
        self.assertEqual(_amount(starved_session, "product"), 3.0)
        self.assertEqual(_component(starved_session, starved)["state"], "running")
        advance_world_tick(starved_session)
        self.assertEqual(_component(starved_session, starved)["state"], "paused")
        self.assertEqual(_component(starved_session, starved)["last_failure"], "insufficient_input")
        self.assertEqual(_amount(starved_session, "feed"), 0.0)

        saturated = _profile(
            "saturated_line",
            _template(input_coefficient=2.0, output_coefficient=3.0, duration=4),
            "full_feed",
            "full_product",
        )
        saturated_session = _session(
            (saturated,),
            {
                "full_feed": (5.0, 10.0, "wood"),
                "full_product": (10.0, 10.0, "board"),
            },
        )
        saturated_controller = ProcessController((saturated,))
        saturated_controller.start(
            saturated_session, saturated.id, owner="factory_owner"
        )
        advance_world_tick(saturated_session)
        self.assertEqual(_amount(saturated_session, "full_feed"), 5.0)
        self.assertEqual(_amount(saturated_session, "full_product"), 10.0)
        self.assertEqual(_component(saturated_session, saturated)["elapsed_ticks"], 0)
        self.assertEqual(_component(saturated_session, saturated)["progress"], 0.0)
        self.assertEqual(_component(saturated_session, saturated)["last_step"], 1)

    def test_rate_duration_pause_resume_and_hard_deadline(self):
        profile = _profile(
            "adjustable_line",
            _template(input_coefficient=1.0, output_coefficient=1.0,
                      duration=5, maximum_duration=5),
            "feed",
            "product",
        )
        session = _session(
            (profile,),
            {
                "feed": (20.0, 20.0, "wood"),
                "product": (0.0, 20.0, "board"),
            },
        )
        controller = ProcessController((profile,))
        controller.start(session, profile.id, owner="factory_owner")
        controller.modify(
            session, profile.id, owner="factory_owner", rate=2.0, remaining_ticks=4
        )
        self.assertEqual(_component(session, profile)["hard_deadline"], 5.0)
        advance_world_tick(session)
        self.assertEqual(_amount(session, "feed"), 18.0)

        controller.pause(session, profile.id, owner="factory_owner")
        paused = _component(session, profile)
        self.assertEqual(paused["state"], "paused")
        self.assertEqual(paused["remaining_ticks"], 3)
        self.assertEqual(session.state.scheduled_events, [])

        controller.resume(session, profile.id, owner="factory_owner")
        resumed = _component(session, profile)
        self.assertEqual(resumed["state"], "running")
        self.assertEqual([event.time for event in session.state.scheduled_events], [4.0])
        advance_world_tick(session)
        self.assertEqual(_amount(session, "feed"), 16.0)

        before = session.state.to_dict()
        with self.assertRaises(GameplayContractError):
            controller.modify(
                session, profile.id, owner="factory_owner", remaining_ticks=4
            )
        self.assertEqual(session.state.to_dict(), before)

    def test_expiry_precedes_the_tick_and_duration_one_never_converts(self):
        two_tick = _profile(
            "two_tick_line",
            _template(duration=2, maximum_duration=2),
            "feed_two",
            "product_two",
        )
        session = _session(
            (two_tick,),
            {
                "feed_two": (10.0, 20.0, "wood"),
                "product_two": (0.0, 20.0, "board"),
            },
        )
        controller = ProcessController((two_tick,))
        controller.start(session, two_tick.id, owner="factory_owner")
        advance_world_tick(session)
        self.assertEqual(_amount(session, "feed_two"), 8.0)
        advance_world_tick(session)
        self.assertEqual(_component(session, two_tick)["state"], "stopped")
        self.assertEqual(_amount(session, "feed_two"), 8.0)
        self.assertEqual(_amount(session, "product_two"), 3.0)

        one_tick = _profile(
            "one_tick_line",
            _template(duration=1, maximum_duration=1),
            "feed_one",
            "product_one",
        )
        one_session = _session(
            (one_tick,),
            {
                "feed_one": (10.0, 20.0, "wood"),
                "product_one": (0.0, 20.0, "board"),
            },
        )
        one_controller = ProcessController((one_tick,))
        one_controller.start(one_session, one_tick.id, owner="factory_owner")
        advance_world_tick(one_session)
        self.assertEqual(_component(one_session, one_tick)["state"], "stopped")
        self.assertEqual(_amount(one_session, "feed_one"), 10.0)
        self.assertEqual(_amount(one_session, "product_one"), 0.0)

    def test_last_step_guard_blocks_duplicate_tick_application(self):
        profile = _profile("guarded_line", _template(duration=5), "feed", "product")
        session = _session(
            (profile,),
            {
                "feed": (10.0, 20.0, "wood"),
                "product": (0.0, 20.0, "board"),
            },
        )
        controller = ProcessController((profile,))
        controller.start(session, profile.id, owner="factory_owner")
        advance_world_tick(session)
        self.assertEqual(_amount(session, "feed"), 8.0)

        duplicate = stage_gameplay_session(session)
        clock = duplicate.state.entities["pmw:v04:clock"].components["pmw_gameplay_clock"]
        clock.update(next_step=1, next_time=1.0, last_completed_step=0)
        duplicate.state.sim_time = 1.0
        result = duplicate.runtime.run_event(Event(
            "duplicate-world-tick", WORLD_TICK_EVENT, 1.0, "pmw:v04:clock", None,
            {"step": 1},
        ))
        self.assertTrue(result.changed)
        self.assertEqual(_amount(duplicate, "feed"), 8.0)
        self.assertEqual(_component(duplicate, profile)["last_step"], 1)


class ProcessSafetyTests(unittest.TestCase):
    def test_tick_guards_forged_rate_stock_domains_and_shared_writers(self):
        template = _template()
        negative = _profile("negative_line", template, "feed", "product")
        session = _session(
            (negative,),
            {
                "feed": (4.0, 20.0, "wood"),
                "product": (0.0, 20.0, "board"),
            },
        )
        controller = ProcessController((negative,))
        controller.start(session, negative.id, owner="factory_owner")
        _component(session, negative)["rate"] = -1.0
        advance_world_tick(session)
        self.assertEqual(
            (_amount(session, "feed"), _amount(session, "product")), (4.0, 0.0)
        )

        forged = _profile("forged_stock_line", template, "bad_feed", "bad_product")
        forged_session = _session(
            (forged,),
            {
                "bad_feed": (4.0, 20.0, "wood"),
                "bad_product": (0.0, 20.0, "board"),
            },
        )
        forged_controller = ProcessController((forged,))
        forged_controller.start(forged_session, forged.id, owner="factory_owner")
        forged_session.state.entities["bad_product"].components["stock"]["amount"] = -3.0
        advance_world_tick(forged_session)
        self.assertEqual(_amount(forged_session, "bad_feed"), 4.0)
        self.assertEqual(_amount(forged_session, "bad_product"), -3.0)

        first = _profile("first_writer", template, "shared_feed", "first_product")
        second = _profile("second_writer", template, "shared_feed", "second_product")
        shared_session = _session(
            (first, second),
            {
                "shared_feed": (4.0, 20.0, "wood"),
                "first_product": (0.0, 20.0, "board"),
                "second_product": (0.0, 20.0, "board"),
            },
        )
        shared_controller = ProcessController((first, second))
        shared_controller.start(shared_session, first.id, owner="factory_owner")
        _component(shared_session, second).update(
            state="running",
            started_at=0.0,
            hard_deadline=8.0,
            expiry_handle="forged-shared-expiry",
            last_step=0,
        )
        shared_session.state.scheduled_events.append(Event(
            "forged-shared-expiry",
            PROCESS_START_EVENT,
            8.0,
            "factory_owner",
            second.process_entity_id,
            {},
        ))
        shared_session.runtime.revalidate()
        advance_world_tick(shared_session)
        self.assertEqual(_amount(shared_session, "shared_feed"), 4.0)
        self.assertEqual(_amount(shared_session, "first_product"), 0.0)
        self.assertEqual(_amount(shared_session, "second_product"), 0.0)

        for field, value in (
            ("rate", 0.0),
            ("rate", -1.0),
            ("rate", 1e9),
        ):
            bad = _profile(f"bad_{field}_{type(value).__name__}", template,
                           "bad_feed", "bad_product")
            bad_session = _session(
                (bad,),
                {
                    "bad_feed": (4.0, 20.0, "wood"),
                    "bad_product": (0.0, 20.0, "board"),
                },
            )
            bad_controller = ProcessController((bad,))
            bad_controller.start(bad_session, bad.id, owner="factory_owner")
            _component(bad_session, bad)[field] = value
            advance_world_tick(bad_session)
            self.assertEqual(_amount(bad_session, "bad_feed"), 4.0)
            self.assertEqual(_amount(bad_session, "bad_product"), 0.0)
            self.assertFalse(math.isnan(_amount(bad_session, "bad_product")))

    def test_invalid_numbers_overlap_units_and_authority_are_rejected(self):
        with self.assertRaises(GameplayContractError):
            _template(rate=float("nan"))
        with self.assertRaises(GameplayContractError):
            _template(duration=True)
        with self.assertRaises(GameplayContractError):
            ConversionPort("feed", True, "wood")

        template = _template()
        with self.assertRaises(GameplayContractError):
            ProcessProfile(
                "overlap",
                template,
                "process_overlap",
                "factory_owner",
                (StockBinding("feed", StockRef("same")),),
                (StockBinding("product", StockRef("same")),),
            )

        mismatch = _profile("mismatch", template, "feed", "product")
        session = _session(
            (mismatch,),
            {
                "feed": (10.0, 20.0, "stone"),
                "product": (0.0, 20.0, "board"),
            },
        )
        controller = ProcessController((mismatch,))
        with self.assertRaises(GameplayContractError):
            controller.start(session, mismatch.id, owner="factory_owner")
        with self.assertRaises(GameplayContractError):
            controller.start(session, mismatch.id, owner="intruder")
        with self.assertRaises(GameplayContractError):
            controller.start(session, "unknown", owner="factory_owner")

    def test_activation_limits_shared_stock_and_external_writer_are_atomic(self):
        template = _template()
        first = _profile("first_line", template, "left_feed", "left_product")
        second = _profile("second_line", template, "right_feed", "right_product")
        session = _session(
            (first, second),
            {
                "left_feed": (10.0, 20.0, "wood"),
                "left_product": (0.0, 20.0, "board"),
                "right_feed": (10.0, 20.0, "wood"),
                "right_product": (0.0, 20.0, "board"),
            },
        )
        limited = ProcessController(
            (first, second), ProcessLimits(max_instances=2, max_active=1)
        )
        limited.start(session, first.id, owner="factory_owner")
        before = session.state.to_dict()
        revisions = (session.runtime.revision, session.runtime.object_revision)
        with self.assertRaises(GameplayContractError):
            limited.start(session, second.id, owner="factory_owner")
        self.assertEqual(session.state.to_dict(), before)
        self.assertEqual(
            (session.runtime.revision, session.runtime.object_revision), revisions
        )

        shared = _profile("shared_line", template, "left_feed", "shared_product")
        shared_session = _session(
            (first, shared),
            {
                "left_feed": (10.0, 20.0, "wood"),
                "left_product": (0.0, 20.0, "board"),
                "shared_product": (0.0, 20.0, "board"),
            },
        )
        shared_controller = ProcessController((first, shared))
        shared_controller.start(shared_session, first.id, owner="factory_owner")
        before = shared_session.state.to_dict()
        with self.assertRaises(GameplayContractError):
            shared_controller.start(shared_session, shared.id, owner="factory_owner")
        self.assertEqual(shared_session.state.to_dict(), before)

        # Modification is another trusted activation-like write path and must
        # reject a competing running profile that shares the same Stock.
        shared_component = _component(shared_session, shared)
        shared_component.update(
            state="running",
            expiry_handle="competing-expiry",
            started_at=0.0,
            hard_deadline=8.0,
        )
        shared_session.state.scheduled_events.append(
            Event("competing-expiry", PROCESS_START_EVENT, 8.0, "factory_owner", shared.process_entity_id, {})
        )
        shared_session.runtime.revalidate()
        before = shared_session.state.to_dict()
        with self.assertRaises(GameplayContractError):
            shared_controller.modify(
                shared_session, first.id, owner="factory_owner", rate=2.0
            )
        self.assertEqual(shared_session.state.to_dict(), before)

        external = ProcessController(
            (first,),
            external_stock_writers={"left_feed": "alpha_inventory_writer"},
        )
        before = session.state.to_dict()
        with self.assertRaises(GameplayContractError):
            external.start(session, first.id, owner="factory_owner")
        self.assertEqual(session.state.to_dict(), before)

    def test_save_load_preserves_expiry_and_replays_remaining_ticks(self):
        profile = _profile("saved_line", _template(duration=4), "feed", "product")
        session = _session(
            (profile,),
            {
                "feed": (10.0, 20.0, "wood"),
                "product": (0.0, 20.0, "board"),
            },
            world_id="saved_process_world",
        )
        controller = ProcessController((profile,))
        controller.start(session, profile.id, owner="factory_owner")
        advance_world_tick(session)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            save_world(path, session.state)
            restored = build_runtime(
                load_world(path), extra_laws=build_process_laws((profile,))
            )
        self.assertEqual(restored.state.to_dict(), session.state.to_dict())
        self.assertEqual(
            [event.id for event in restored.state.scheduled_events],
            [event.id for event in session.state.scheduled_events],
        )
        advance_world_tick(session)
        advance_world_tick(restored)
        self.assertEqual(restored.state.to_dict(), session.state.to_dict())

    def test_expiry_stops_process_when_stock_target_is_missing(self):
        profile = _profile("resilient_line", _template(duration=3), "feed", "product")
        session = _session(
            (profile,),
            {
                "feed": (10.0, 20.0, "wood"),
                "product": (0.0, 20.0, "board"),
            },
        )
        controller = ProcessController((profile,))
        controller.start(session, profile.id, owner="factory_owner")
        advance_world_tick(session)
        session.state.entities.pop("product")
        session.runtime.revalidate()

        advance_world_tick(session)
        advance_world_tick(session)
        component = _component(session, profile)
        self.assertEqual(component["state"], "stopped")
        self.assertIsNone(component["expiry_handle"])
        self.assertEqual(session.state.scheduled_events, [])


if __name__ == "__main__":
    unittest.main()
