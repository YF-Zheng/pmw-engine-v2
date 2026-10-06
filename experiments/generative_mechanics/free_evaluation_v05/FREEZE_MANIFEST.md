# Free-Invention Evaluator v0.5 Freeze Manifest

v0.5 freeze only freezes the evaluator contract; it does not mean that any real-model experiment has been completed.

## Protocols and status

- Free generation protocol: `gm-free-invention-v0.3`
- Free evaluation protocol: `gm-free-evaluation-v0.5`
- Controlled protocol: `gm-generation-v0.2-controlled`
- Evaluator status: `frozen`
- Formal paper experiment: `NOT STARTED`
- DEV pilot: `NOT STARTED`

## Administrative transition

- Candidate protocol: `gm-free-evaluation-v0.5-candidate`
- Candidate status: `preregistered_candidate_not_frozen`
- Frozen protocol: `gm-free-evaluation-v0.5`
- Frozen status: `frozen`
- Change scope: `administrative_identifier_and_status_only`
- Base commit: `fdb5c845dea48db41255b9c38aee830c77e8d87a`
- Pre-freeze reviewed semantic contract digest: `01635c9e500c22250bb8fe3309c54a213bcd9a0638a8429b730f07e8121851d2`
- Measurement source continuity: the causal, cross-environment, and structural evaluator hashes below are identical to the reviewed candidate hashes.

## Git provenance

- Base commit: `fdb5c845dea48db41255b9c38aee830c77e8d87a`
- Freeze commit: `COMMIT_CONTAINING_THIS_MANIFEST`
- Resolution: `git log -1 --format=%H -- experiments/generative_mechanics/free_evaluation_v05/FREEZE_MANIFEST.json`

The freeze commit is necessarily identified by the commit containing this manifest; a Git commit cannot embed its own object ID without changing that ID.

## Contract digests

- core_manifest_sha256: `0cb9271e7dcfa9b1882246190f78afddfb1f153e699c7609182cbcd921cacf5d`
- reference_registry_projection_sha256: `bffb8ff4bbaaf678bcacd81af867c77b31147fe5c6c44ee2f51a0f95e77383cc`
- reference_registry_file_sha256: `32823cff7d438f39db60909f550ff68fc277963e6ea06ec7bfcc6aca22d6eacc`
- reference_source_sha256: `7f3fe174c9c9820b2ad7572fd42a28113018cd614ff3bb3676a1bd59a1ce6d91`
- adversarial_preregistration_digest: `0a4658766b0166602c7410b65bc1dabb313711d6ce6b4b95ad2f43ef19ee44ce`
- adversarial_preregistration_file_sha256: `e251f35169a3afe73e1b7e052c4c14f3d86db2ccef42c8189cefb01b1740dd76`
- semantic_contract_digest: `de843327762164af55c7ba342345a4861da2aab3d2082ecdd1392d4558e3b28f`
- semantic_contract_file_sha256: `7cc68777d324c54214bef42b736e5728d2147ac4463dfa3646658b8890663be9`

## Evaluator source hashes

- `experiments/generative_mechanics/free_evaluation_v05/causal.py`: `59f60ab40a9eff77f640a3e95014e601a58278cf96174693cd813f08a8d5ab54`
- `experiments/generative_mechanics/free_evaluation_v05/environment.py`: `a6099184c569270b998f43c719689a45906d1c56184fc78e84c6d4afdcee950e`
- `experiments/generative_mechanics/free_evaluation_v05/structure.py`: `804d31745a7bb28044cac7dab195539b4141fd34dba898cc6738869bc750b905`
- `experiments/generative_mechanics/free_evaluation_v05/protocol.json`: `e651fae542512b2e75e5142fca35618cd988798d4e47d98044471763d62eadb9`

## Administrative source hashes

- `experiments/generative_mechanics/free_evaluation_v05/freeze_manifest.py`: `65dfc96cbf5435af8f31c60ad3dc2e0d2178ab06aa3a20df03adf1a90b3236f7`

## World/system law digests

- `experiments/generative_mechanics/substrate/world_laws.json`: `bac6ed0eaede6340c6a5f6a89cc3e5b240d8e4aa750f9ce85dfc5f21e143ea0c`
- `experiments/generative_mechanics/substrate.py`: `d3bfdf0f5dd7ae5262f7bdd532102f0c050cabf22ee79bc759f23fa827b06df7`

## Environment asset digests

- `experiments/generative_mechanics/environments/fragile_bridge.json`: `b3332b7190aefcd160df7055103aa2a6463de0a77dc2a5b4d233572b635ec0e6`
- `experiments/generative_mechanics/environments/industrial_yard.json`: `0f45ed4fb1e68a5627e0dbadca58f1155bc2eae245d2fa59571c9bfdb6937ed3`
- `experiments/generative_mechanics/environments/mine.json`: `d6ea27bd1d16e864a17729cb0804c37c9a5cea225bcf8dc22bb0714d233985fd`
- `experiments/generative_mechanics/environments/wetland.json`: `cbd7f602f23573e5bbb092fc58b3533733d8bf0b159ae559d73b991583dabae7`

## Scenario/context digests

- `experiments/generative_mechanics/cross_environment_v04.py`: `a1b85ae0c11282c2aee4043823fedcccb1537f9a9b66be4eb71dac06135b4b9f`
- `experiments/generative_mechanics/scenarios/calibration/aftermath.json`: `1171af8db6a803ab13b58f32f21eea98a2cd5753a692deb3e3089049dd0f985b`
- `experiments/generative_mechanics/scenarios/calibration/environmental_hazard.json`: `01fe3dd8e940c6e425e0271d689cca79f07da830e60c534f0be55f42d6216f0d`
- `experiments/generative_mechanics/scenarios/calibration/long_combat.json`: `29d5f23fc21b3cdf7dad5fd9de0dda5d5ea6f7b6b50297aed8fb546b46fa0d7f`
- `experiments/generative_mechanics/scenarios/calibration/multi_target.json`: `498c05d6352277db8835a96913de049cc89e4fa8916abddf0ac081bcfaa20b30`
- `experiments/generative_mechanics/scenarios/calibration/resource_limited.json`: `6ef442e54b19b91862db839ff6209213254ca67bce7ee862956980bce02f43b8`
- `experiments/generative_mechanics/scenarios/calibration/short_combat.json`: `d497dc5b122ddd1ff0e0bbc8bb0b195b4b58e038059a34e0621c46e1107b5389`
- `experiments/generative_mechanics/scenarios/evaluation/aftermath.json`: `9778fb3f947b3163dc3bac7a4e7a2ac360e5f97428d37dcff4cdc52504700865`
- `experiments/generative_mechanics/scenarios/evaluation/environmental_hazard.json`: `deeab594a7000bf08c7a0a9dc6eaa5f3ec47ff735bf8d2bfb51d570bfdd5bfc4`
- `experiments/generative_mechanics/scenarios/evaluation/long_combat.json`: `0ce93df7dd9cb3511612dee3ba5df153dd3a2f56e090c168190692f80ece53e2`
- `experiments/generative_mechanics/scenarios/evaluation/multi_target.json`: `28f25bb789823dc282e69ef07994eef5a121665d332c69b454cf9ade5f7629c3`
- `experiments/generative_mechanics/scenarios/evaluation/resource_limited.json`: `7f9c9cb1d5d754914bf66d79a7c64170164d1b72a6a9bfd22d8c53c9d4037dbc`
- `experiments/generative_mechanics/scenarios/evaluation/short_combat.json`: `450202becbdae770cfd2f25c940132e634ebd775c01acce6bf6846caae1cc4ef`

## Post-freeze policy

DEV pilot work must not change v0.5 metric semantics. A required measurement fix must become v0.6, preserve the original v0.5 pilot results, and document the freeze-break reason.
