import hashlib
import json
from pathlib import Path

from acoustic_ladder.protocol.planning_persistence import validate_development_protocol_plan
from acoustic_ladder.protocol.rehearsal import (
    DevelopmentProtocolRehearsalStore,
    apply_protocol_rehearsal_transition,
    initialize_protocol_rehearsal,
    validate_protocol_rehearsal,
)
from tests.dev05.test_protocol_rehearsal import _clock, _command, _published_plan

EXPECTED_FULL_REHEARSAL_HASHES = {
    "stage1": {
        "completion": "9742273e5457d2dc22f7501e6e3e133614fa2bc2f342ffbe7479443078e4c87b",
        "completion_sidecar": "476e6f68dd4c7399c4fd11b4529727ba21e4c3f92700265593ba6752a28e29de",
        "first_event": "7db73ca8747177aaf2da2afe6321c66b53f604d7fe19c5e76d5d7287ebcdc481",
        "last_event": "5bf18e699c1ce9a779e80c33deea5d1f4ac183952a5505fbc4734cf605b084b4",
        "manifest": "4696f9e06cb525712f1e5dc38353ee40ba6f082524686e2e2304425c3f138df3",
        "manifest_sidecar": "3bacfe25ead10c0f5e98acef0d93f6cad1190b2af75b06b707920509f7ddf1f7",
        "ordered_event_aggregate": (
            "16bf1b39e3d21f99dee7c652c44bd20785a866db376f28dea0b51a960c3c5801"
        ),
        "record": "2553fcaa84926ed2e393cd43ea149925f8aec1d26677cf36088e1c5baaa874bc",
        "record_sidecar": "73249c8b23e0794e46a7eb2b35cf7cfb76029b2640cd170f5ede83704ead3029",
    },
    "stage2": {
        "completion": "46d830a40b575a8449d64ad7548de59c0046e27a3bb9ac2a78d3d2764333c50e",
        "completion_sidecar": "0ef5e823bbac515743d016759297ef25b36c8fc4f417374384f6454fb2547c43",
        "first_event": "7d76618fd43c1a5dac45e408d6bec1b640f2f1dd2cdaccdd0aaca46db2c51e52",
        "last_event": "6a5171f58ae3f3a614d23c9495215b146959ced329057d12c0a16476b8ca0656",
        "manifest": "abcdb020002285bbaede39439c943901fb7f86d86b92576262093e0ddf0ded67",
        "manifest_sidecar": "447211eb74ae13c8a04894c58ea119088cb374ffff3e5a26dbde534d1cab48f7",
        "ordered_event_aggregate": (
            "26e9cb7a5f6211b51af747f40eabb7604ab3416b7623960653566c6e2444f88b"
        ),
        "record": "5e40e10dc1a20e8a96d76947e843d1079da54e852ccb8a01a086c7e0332ce5a0",
        "record_sidecar": "4ea236e10647f310e8ff1264607d56369bad9f66ff762b7f7dfc9ad3863c6229",
    },
    "stage3": {
        "completion": "9a6f40bd8dc45cf62a76cf55b302cffdd2296d03f7e9e714c8032670ed57793a",
        "completion_sidecar": "60daf31ff3b1d5067712e5176261944782b9baa4f6f5803a16a14150ebd6478a",
        "first_event": "a45805a40c9357a30a7bd429f95201bd2bbcea247360132ef1544c968116734e",
        "last_event": "0f0a868c1c68421d030c9626d5820f7f6ad14ceb6e43ed05597efe8f5de3637e",
        "manifest": "2c6aef8c6100b6bd6a550fab6c2c821b949bf568fee1cf76d811588ab7282c0f",
        "manifest_sidecar": "45b0b92cee2c99a01577c046471b15266fb45e6d79e4e198f3a9bc67854fe3c1",
        "ordered_event_aggregate": (
            "1cb87cf29e4ac26e1fae6c5f207b20d25859b4d04fcaeecf42336382c2819d87"
        ),
        "record": "5812b70bd0323d864a4c6209a6a0078d4e4f4c1bb1ee1dc556e07e5a7dcae6ab",
        "record_sidecar": "ca785eb91a8865a4bcd576c28f89eb724431f10d97944a417a0cc947140a5e23",
    },
    "stage4": {
        "completion": "c59b29e90513ee61f9b1b35cbfc88a57c8fbcff22b2dad90c821a567dc1f252a",
        "completion_sidecar": "bc50e7301f6f2f2d11275411e77c32b2ce27c0ebe762d39dc3860a741cb16be1",
        "first_event": "36543abcb9a7384704a36d10fc1303e6b13ba3bc8ee2da508f4b470394c8a14f",
        "last_event": "df2bc575813f3a451b827bed9dafee2c275a6d2fb56301649b0cb66e1c1e09c1",
        "manifest": "dbbe77a9704fb9e8c01d175767fc6e937db825738b6d3757989830d0e9efaac8",
        "manifest_sidecar": "18180cd6b3cd01213ddb46690431b7848b86906c03d12b87150b87c9a091c5f5",
        "ordered_event_aggregate": (
            "b90600ee964168dc452da8dbd99f5c7f0173e62f91bbca912e5ad5cfbe06d5c1"
        ),
        "record": "7f32dd91159cf94bfbbd85b2a1f8a0794a3fc7a0a265d52d438244547ba6d94f",
        "record_sidecar": "c6be323d5b050571b4ca02035e30ad0b9ac584be91ae97eef63db57341dba936",
    },
}


def test_four_stage_two_root_complete_rehearsals_are_byte_deterministic(
    tmp_path: Path,
) -> None:
    expected_counts = {
        1: (19, 152, 456),
        2: (4, 32, 96),
        3: (4, 32, 96),
        4: (16, 128, 384),
    }
    root_outputs: list[dict[str, dict[str, bytes]]] = []

    for root_name in ("a", "b"):
        stage_outputs: dict[str, dict[str, bytes]] = {}
        task_root = tmp_path / root_name
        for stage, (condition_count, work_order_count, event_count) in expected_counts.items():
            stage_root = task_root / f"s{stage}"
            bundle, spec, plan_store = _published_plan(stage_root, stage)
            store = DevelopmentProtocolRehearsalStore(stage_root / "ledger")
            rehearsal_id = f"s{stage}"
            status = initialize_protocol_rehearsal(
                store=store,
                plan_store=plan_store,
                bundle=bundle,
                spec=spec,
                plan_id=f"stage{stage}-plan",
                rehearsal_id=rehearsal_id,
                now=_clock(),
            )
            assert status.total_work_order_count == work_order_count
            now = _clock()
            observed_orders: list[int] = []
            for _ in range(work_order_count):
                assert status.current_work_order is not None
                observed_orders.append(status.current_work_order.global_planned_ordinal)
                for action in ("present-requirements", "claim", "mark-rehearsed"):
                    status = apply_protocol_rehearsal_transition(
                        store=store,
                        plan_store=plan_store,
                        bundle=bundle,
                        spec=spec,
                        plan_id=f"stage{stage}-plan",
                        rehearsal_id=rehearsal_id,
                        command=_command(status, action),
                        token=status.concurrency_token,
                        now=now,
                    )
            validated = validate_protocol_rehearsal(
                store=store,
                plan_store=plan_store,
                bundle=bundle,
                spec=spec,
                plan_id=f"stage{stage}-plan",
                rehearsal_id=rehearsal_id,
            )
            assert observed_orders == list(range(1, work_order_count + 1))
            assert validated.rehearsal_state == "complete"
            assert validated.cursor == work_order_count
            assert validated.concurrency_token.event_sequence == event_count
            root = store.rehearsal_path(rehearsal_id)
            assert len(list((root / "events").glob("event_*.json"))) == event_count
            validated_plan = validate_development_protocol_plan(
                store=plan_store,
                bundle=bundle,
                spec=spec,
                plan_id=f"stage{stage}-plan",
            )
            assert condition_count == len(
                {
                    block.condition_id
                    for session in validated_plan.plan.session_slots
                    for reassembly in session.reassembly_slots
                    for block in reassembly.condition_blocks
                }
            )
            last_name = f"event_{event_count:08d}.json"
            completion_bytes = (root / "protocol_rehearsal_completion.json").read_bytes()
            completion = json.loads(completion_bytes)
            stage_outputs[f"stage{stage}"] = {
                "manifest": (root / "protocol_rehearsal_manifest.json").read_bytes(),
                "manifest_sidecar": (root / "protocol_rehearsal_manifest.sha256").read_bytes(),
                "record": (root / "protocol_rehearsal_record.json").read_bytes(),
                "record_sidecar": (root / "protocol_rehearsal_record.sha256").read_bytes(),
                "first_event": (root / "events/event_00000001.json").read_bytes(),
                "last_event": (root / "events" / last_name).read_bytes(),
                "completion": completion_bytes,
                "completion_sidecar": (root / "protocol_rehearsal_completion.sha256").read_bytes(),
                "ordered_event_aggregate": completion["ordered_event_aggregate_sha256"].encode(
                    "ascii"
                ),
            }
            assert not list(stage_root.rglob("session_*"))
            assert not list(stage_root.rglob("run_*"))
            assert not list(stage_root.rglob("*.wav"))
            assert not list(stage_root.rglob("*.npz"))
            assert not (stage_root / "real").exists()
            assert not (stage_root / "synthetic").exists()
        root_outputs.append(stage_outputs)

    assert root_outputs[0] == root_outputs[1]
    hashes = {
        stage: {name: hashlib.sha256(payload).hexdigest() for name, payload in artifacts.items()}
        for stage, artifacts in root_outputs[0].items()
    }
    assert hashes == EXPECTED_FULL_REHEARSAL_HASHES
