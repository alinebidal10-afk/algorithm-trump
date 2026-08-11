# RL_CFR_MONOPOLYMODIFIED

This directory is **vendored third-party code**, not original work of this
repository.

Source: [cavaunpeu/monopoly-deal-ai](https://github.com/cavaunpeu/monopoly-deal-ai)
Author: Will Wolf (Copyright 2025)

License: see [`./LICENSE`](./LICENSE) (Apache License, Version 2.0, as
modified by the copyright holder) and [`../NOTICE`](../NOTICE) for full
attribution and the list of modifications made here.

This code implements **Monopoly Deal**, a two-player card game — it is a
different game from the board Monopoly implemented in
`monopoly_game_engine/` (ruleset `ppo-plus-v2`), and is out of scope for
that work.

Do not edit files in this directory except for
`RL_models_1_CounterfactualRegretMinimization/cfr/classic_cfr.py`, which was
added locally and has no upstream counterpart. Keeping the rest unmodified
(beyond the import-path rewrite noted in `../NOTICE`) keeps this vendored
copy diffable against upstream.
