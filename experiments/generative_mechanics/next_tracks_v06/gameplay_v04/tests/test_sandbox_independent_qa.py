from __future__ import annotations

import random
import unittest

from pmw import Event, WorldState

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import basic_registry
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_area,
    parse_area_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    FieldDefinition, GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.dynamics import (
    evaluate_field,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.ecology import (
    parse_ecology_spec,
    sample_ecology,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    build_runtime,
    clock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.processes import (
    PROCESS_COMPONENT,
    PROCESS_EXPIRE_EVENT,
    ConversionPort,
    ProcessController,
    ProcessProfile,
    ProcessTemplate,
    StockBinding,
    StockRef,
    build_process_laws,
    instantiate_process,
    stock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import (
    build_gameplay_world,
)


def _field(curve: str = "linear", rate: float = 0.0) -> dict:
    return {
        "id": "temperature",
        "domain": {"min": 0.0, "max": 1.0},
        "initial": 0.5,
        "target": 0.5,
        "rate": rate,
        "curve": curve,
        "max_persistent_patches": 2,
        "max_temporary_modifiers": 2,
    }


def _area() -> object:
    return instantiate_area(
        parse_area_blueprint({
            "protocol": "pmw-gameplay-v0.4",
            "kind": "area_blueprint",
            "id": "eco_area",
            "fields": [_field()],
        }),
        "eco_area",
    )


def _world() -> object:
    return build_gameplay_world("eco_probe", areas=[_area(), clock_entity()])


def _ecology_raw(rate: float = 0.5) -> dict:
    return {
        "protocol": "pmw-gameplay-v0.4",
        "id": "edge_eco",
        "label": "Edge",
        "initial_regime": "alpha",
        "sample_count": 2,
        "regimes": [
            {
                "id": "alpha",
                "label": "A",
                "clue": "a",
                "baselines": [{
                    "field_id": "temperature", "target": 0.2,
                    "rate": 0.0, "curve": "linear",
                }],
            },
            {
                "id": "beta",
                "label": "B",
                "clue": "b",
                "baselines": [{
                    "field_id": "temperature", "target": 0.2,
                    "rate": rate, "curve": "none",
                }],
            },
        ],
        "transitions": [{
            "id": "transition",
            "from": "alpha",
            "to": "beta",
            "condition": {
                "field_id": "temperature",
                "comparator": "gte",
                "threshold": 0.5,
            },
            "window_ticks": 1,
            "clue": "go",
        }],
    }


def _ecology(rate: float = 0.5) -> object:
    return parse_ecology_spec(_ecology_raw(rate))


def _process_template(
    *,
    template_id: str = "independent_conversion",
    inputs: tuple[ConversionPort, ...] = (ConversionPort("feed", 2.0, "wood"),),
    outputs: tuple[ConversionPort, ...] = (ConversionPort("product", 3.0, "board"),),
    rate: float = 1.0,
    duration: int = 4,
    maximum_duration: int = 8,
) -> ProcessTemplate:
    return ProcessTemplate(
        template_id,
        inputs,
        outputs,
        rate,
        duration,
        rate * 10.0,
        maximum_duration,
    )


def _process_profile(
    profile_id: str,
    template: ProcessTemplate,
    bindings: tuple[tuple[str, str], ...],
) -> ProcessProfile:
    input_names = {port.name for port in template.inputs}
    inputs = tuple(
        StockBinding(port, StockRef(stock_id))
        for port, stock_id in bindings
        if port in input_names
    )
    outputs = tuple(
        StockBinding(port, StockRef(stock_id))
        for port, stock_id in bindings
        if port not in input_names
    )
    return ProcessProfile(
        profile_id,
        template,
        f"process_{profile_id}",
        "factory_owner",
        inputs,
        outputs,
    )


def _process_session(
    profiles: tuple[ProcessProfile, ...],
    stocks: dict[str, tuple[float, float, str]],
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
    return build_runtime(
        WorldState("independent_process_world", entities=entities),
        extra_laws=build_process_laws(profiles),
    )


def _process_component(session, profile: ProcessProfile) -> dict:
    return session.state.entities[profile.process_entity_id].components[
        PROCESS_COMPONENT
    ]


def _stock_amount(session, stock_id: str) -> float:
    return session.state.entities[stock_id].components["stock"]["amount"]


class NoRecoveryEcologyIntegrationTests(unittest.TestCase):
    def test_none_ecology_baseline_honors_zero_rate_policy(self):
        with self.assertRaises(GameplayContractError):
            parse_ecology_spec(_ecology_raw(rate=0.5))

    def test_none_ecology_transition_selects_live_baseline_on_next_tick(self):
        spec = _ecology(rate=0.0)
        plan = sample_ecology(spec, 7)
        content = make_content(basic_registry(), ecology_by_area={"eco_area": plan})
        world = initialize_content_world(_world(), content)
        session = build_content_session(world, compile_content(content))

        advance_world_tick(session)
        first_field = session.state.entities["eco_area"].components[
            "pmw_gameplay_dynamics"
        ]["fields"]["temperature"]
        self.assertEqual(first_field["baseline"]["curve"], "none")
        self.assertEqual(first_field["diagnostics"]["effective_curve"], "linear")
        advance_world_tick(session)
        field = session.state.entities["eco_area"].components[
            "pmw_gameplay_dynamics"
        ]["fields"]["temperature"]
        self.assertEqual(
            session.state.entities["eco_area"].components[
                "pmw_gameplay_ecology"
            ]["current"],
            "beta",
        )
        self.assertEqual(field["baseline"]["curve"], "none")
        self.assertEqual(field["value"], 0.5)
        # Ecology and dynamics read the same pre-event state. The baseline
        # published by that tick governs the next tick without a rebuild.
        self.assertEqual(field["diagnostics"]["effective_curve"], "none")
        self.assertEqual(field["diagnostics"]["effective_rate"], 0.0)


class NoRecoveryClampParityTests(unittest.TestCase):
    def test_out_of_range_none_state_is_clamped_by_formal_tick_and_reference(self):
        area = instantiate_area(
            parse_area_blueprint({
                "protocol": "pmw-gameplay-v0.4",
                "kind": "area_blueprint",
                "id": "area_x",
                "fields": [{
                    "id": "temperature",
                    "domain": {"min": 0.0, "max": 1.0},
                    "initial": 0.8,
                    "target": 0.2,
                    "rate": 0.0,
                    "curve": "none",
                    "max_persistent_patches": 2,
                    "max_temporary_modifiers": 2,
                }],
            }),
            "area_x",
        )
        session = build_runtime(
            build_gameplay_world("clamp_probe", areas=[area, clock_entity()]),
        )
        pre_tick_state = session.state.entities["area_x"].components[
            "pmw_gameplay_dynamics"
        ]["fields"]["temperature"]
        pre_tick_state["value"] = 1.7
        reference = evaluate_field(
            FieldDefinition("temperature", 0.0, 1.0, 0.8, 0.2, 0.0, "none", 2, 2),
            1.7,
        )

        advance_world_tick(session)
        state = session.state.entities["area_x"].components[
            "pmw_gameplay_dynamics"
        ]["fields"]["temperature"]
        self.assertEqual(reference.value, 1.0)
        self.assertEqual(state["value"], 1.0)
        self.assertEqual(state["diagnostics"]["clamp_loss"], -0.7)
        self.assertEqual(state["diagnostics"]["unclamped"], 1.7)
        # Core copy-on-write replaces the entity clone, so the pre-tick dict is
        # intentionally stale. Keep this assertion to prevent future QA from
        # mistaking the replacement for a dynamics failure.
        self.assertEqual(pre_tick_state["value"], 1.7)


class ProcessConservationTests(unittest.TestCase):
    def test_multi_port_conversion_matches_independent_stoichiometric_oracle(self):
        rng = random.Random(0x5A17)
        for case in range(80):
            with self.subTest(case=case):
                coefficients = tuple(
                    10.0 ** rng.uniform(-3.0, 3.0) for _ in range(4)
                )
                input_amounts = tuple(
                    10.0 ** rng.uniform(-6.0, 4.0) for _ in range(2)
                )
                output_capacities = tuple(
                    10.0 ** rng.uniform(-6.0, 4.0) for _ in range(2)
                )
                output_amounts = tuple(
                    capacity * rng.uniform(0.0, 0.999999)
                    for capacity in output_capacities
                )
                rate = 10.0 ** rng.uniform(-3.0, 2.0)
                template = _process_template(
                    inputs=(
                        ConversionPort("feed_a", coefficients[0], "ore"),
                        ConversionPort("feed_b", coefficients[1], "flux"),
                    ),
                    outputs=(
                        ConversionPort("metal", coefficients[2], "metal"),
                        ConversionPort("slag", coefficients[3], "slag"),
                    ),
                    rate=rate,
                )
                profile = _process_profile(
                    "fuzz_line",
                    template,
                    (
                        ("feed_a", "feed_a"),
                        ("feed_b", "feed_b"),
                        ("metal", "metal"),
                        ("slag", "slag"),
                    ),
                )
                session = _process_session(
                    (profile,),
                    {
                        "feed_a": (input_amounts[0], input_amounts[0] * 2.0, "ore"),
                        "feed_b": (input_amounts[1], input_amounts[1] * 2.0, "flux"),
                        "metal": (output_amounts[0], output_capacities[0], "metal"),
                        "slag": (output_amounts[1], output_capacities[1], "slag"),
                    },
                )
                ProcessController((profile,)).start(
                    session, profile.id, owner="factory_owner"
                )
                advance_world_tick(session)

                quantity = min(
                    rate,
                    input_amounts[0] / coefficients[0],
                    input_amounts[1] / coefficients[1],
                    (output_capacities[0] - output_amounts[0]) / coefficients[2],
                    (output_capacities[1] - output_amounts[1]) / coefficients[3],
                )
                expected = (
                    max(0.0, input_amounts[0] - quantity * coefficients[0]),
                    max(0.0, input_amounts[1] - quantity * coefficients[1]),
                    min(
                        output_capacities[0],
                        output_amounts[0] + quantity * coefficients[2],
                    ),
                    min(
                        output_capacities[1],
                        output_amounts[1] + quantity * coefficients[3],
                    ),
                )
                actual = (
                    _stock_amount(session, "feed_a"),
                    _stock_amount(session, "feed_b"),
                    _stock_amount(session, "metal"),
                    _stock_amount(session, "slag"),
                )
                for index, (got, want) in enumerate(zip(actual, expected)):
                    self.assertAlmostEqual(
                        got,
                        want,
                        delta=1e-9 * max(1.0, abs(want)),
                        msg=f"stock port {index}",
                    )
                self.assertGreaterEqual(actual[0], 0.0)
                self.assertGreaterEqual(actual[1], 0.0)
                self.assertLessEqual(actual[2], output_capacities[0])
                self.assertLessEqual(actual[3], output_capacities[1])

    def test_one_full_output_makes_the_whole_conversion_atomic(self):
        template = _process_template(
            inputs=(ConversionPort("feed", 1.0, "wood"),),
            outputs=(
                ConversionPort("good", 1.0, "board"),
                ConversionPort("full", 1.0, "panel"),
            ),
        )
        profile = _process_profile(
            "atomic_line",
            template,
            (("feed", "feed"), ("good", "good"), ("full", "full")),
        )
        session = _process_session(
            (profile,),
            {
                "feed": (10.0, 20.0, "wood"),
                "good": (0.0, 20.0, "board"),
                "full": (20.0, 20.0, "panel"),
            },
        )
        ProcessController((profile,)).start(
            session, profile.id, owner="factory_owner"
        )
        advance_world_tick(session)

        self.assertEqual(_stock_amount(session, "feed"), 10.0)
        self.assertEqual(_stock_amount(session, "good"), 0.0)
        self.assertEqual(_stock_amount(session, "full"), 20.0)
        component = _process_component(session, profile)
        self.assertEqual(component["remaining_ticks"], 4)
        self.assertEqual(component["elapsed_ticks"], 0)
        self.assertEqual(component["last_step"], 1)

    def test_one_empty_input_makes_the_whole_conversion_atomic(self):
        template = _process_template(
            inputs=(
                ConversionPort("feed_a", 1.0, "wood"),
                ConversionPort("feed_b", 1.0, "ore"),
            ),
            outputs=(ConversionPort("product", 2.0, "alloy"),),
        )
        profile = _process_profile(
            "two_feed_line",
            template,
            (
                ("feed_a", "feed_a"),
                ("feed_b", "feed_b"),
                ("product", "product"),
            ),
        )
        session = _process_session(
            (profile,),
            {
                "feed_a": (10.0, 20.0, "wood"),
                "feed_b": (10.0, 20.0, "ore"),
                "product": (0.0, 20.0, "alloy"),
            },
        )
        controller = ProcessController((profile,))
        controller.start(session, profile.id, owner="factory_owner")
        session.state.entities["feed_b"].components["stock"]["amount"] = 0.0
        advance_world_tick(session)

        self.assertEqual(_stock_amount(session, "feed_a"), 10.0)
        self.assertEqual(_stock_amount(session, "feed_b"), 0.0)
        self.assertEqual(_stock_amount(session, "product"), 0.0)
        component = _process_component(session, profile)
        self.assertEqual(component["state"], "paused")
        self.assertEqual(component["last_failure"], "insufficient_input")


class ProcessForgedStateTests(unittest.TestCase):
    def test_tick_does_not_accept_forged_negative_rate(self):
        profile = _process_profile(
            "negative_rate_line",
            _process_template(),
            (("feed", "feed"), ("product", "product")),
        )
        session = _process_session(
            (profile,),
            {
                "feed": (4.0, 20.0, "wood"),
                "product": (0.0, 20.0, "board"),
            },
        )
        ProcessController((profile,)).start(
            session, profile.id, owner="factory_owner"
        )
        _process_component(session, profile)["rate"] = -1.0

        advance_world_tick(session)

        self.assertEqual(
            (_stock_amount(session, "feed"), _stock_amount(session, "product")),
            (4.0, 0.0),
            "negative forged rate produced output without consuming input",
        )

    def test_tick_rejects_or_prevents_forged_shared_running_writer(self):
        template = _process_template()
        first = _process_profile(
            "a_line", template, (("feed", "feed"), ("product", "a_product"))
        )
        second = _process_profile(
            "b_line", template, (("feed", "feed"), ("product", "b_product"))
        )
        session = _process_session(
            (first, second),
            {
                "feed": (4.0, 20.0, "wood"),
                "a_product": (0.0, 20.0, "board"),
                "b_product": (0.0, 20.0, "board"),
            },
        )
        ProcessController((first, second)).start(
            session, first.id, owner="factory_owner"
        )

        forged = _process_component(session, second)
        forged.update(
            state="running",
            started_at=0.0,
            hard_deadline=8.0,
            expiry_handle="forged-shared-expiry",
            last_step=0,
        )
        session.state.scheduled_events.append(Event(
            "forged-shared-expiry",
            PROCESS_EXPIRE_EVENT,
            8.0,
            second.owner,
            second.process_entity_id,
            {"profile_id": second.id, "profile_hash": second.profile_hash},
        ))
        session.runtime.revalidate()

        advance_world_tick(session)

        consumed = 4.0 - _stock_amount(session, "feed")
        produced = (
            _stock_amount(session, "a_product")
            + _stock_amount(session, "b_product")
        )
        # At most one writer may spend each input unit. Doubling production
        # is evidence that two running instances bypassed exclusivity.
        self.assertLessEqual(
            produced,
            consumed * (3.0 / 2.0) + 1e-12,
            "two forged concurrent writers each spent the same input Stock",
        )


if __name__ == "__main__":
    unittest.main()
