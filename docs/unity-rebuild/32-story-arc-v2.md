# 32 - Story arc v2: exploration -> combat -> gear -> the deep end -> big islands -> the Mad God

"V0.2 final final" session. The user asked for the quest log to start with exploration, then move to combat and
items, then the islands, then the Mad God. They also asked for a new name for Act I.

## 1. Acts (`game/story.py` `ACTS`, `FINAL_ACT` = 7)
| # | Title | Objectives (kind: key) |
|---|---|---|
| 0 | Prologue: Welcome, Sucker | `talk`, `zone: realm` |
| 1 | Act I: The Grand Tour | `area` x5 (big named places, `areas.py`), `landmark` x4 (outer biomes, within 8 tiles), `npc` x3 (any NPC conversation), `fish` x1 |
| 2 | Act II: Bouncer Problems | `guardian` for each outer biome (forest / desert / tundra / swamp), `dungeon` x1 |
| 3 | Act III: Retail Therapy | `equip_tier` (T8+ worn, checked on the side-quest tick), `dungeon` x2, `heroic_unlock` x1, `forge` x1 |
| 4 | Act IV: The Deep End | `guardian` x4 (inner biomes), `heroic_dungeon` x2 |
| 5 | Act V: Last Call | `island` x7 (the big islands need level 20) |
| 6 | Finale: Closing Time | `mad_god` (the Forge fight, unchanged) |

- **Free play:** the hint points at the Mad God's Room (doc 34).
- **Act scaling:** `act_scale = 1 + 0.1 * act`, so 1.0 up to 1.6. That's the same top end as the old arc.
- **Guardians:** every Landmark Guardian now drops a Dungeon Shard, outer ones included.
- **Event sources:**
  - `RealmSim._story_personal`: area, landmark, fish, equip (single-player credit only)
  - `dialogue.Conversation.start`: npc
  - `dialogue` Anvil: forge
  - `sidequests._unlock_heroic`: heroic_unlock
  - `RealmSim._reward` on a Heroic boss: heroic_dungeon
- Every objective kind has an `objective_target()`, and every target resolves to a codex entry. New entries: `area:areas`, `locals`, `water`, `gear`, `anvil`, `heroic_trials` and `heroic_dungeons`.

## 2. Save migration
- `StoryProgress.to_json` writes `"v": 2`.
- A character save with no `"v"` is from the old 5-act arc. Its act is mapped with
  `OLD_ACT_TO_NEW = {0: 0, 1: 1, 2: 3, 3: 4, 4: 6, 5: 7}` and its in-act progress is dropped, because the old objective ids no longer exist.
- The account record gets `story_v`. `accounts.get_story_act` migrates an unversioned checkpoint once and saves it; `set_story_act` always stamps the version.

## 3. Rebuild notes
Act indices are exported as `ACT_PROLOGUE` ... `ACT_FINALE`. Code and tests use those names, never raw numbers.

## 4. Pacing

Measured with `tools/pacing_bot.py` (4 classes x 2 seeds, simulated minutes). It found two real problems, now fixed: Act IV only counted *different* Heroic dungeons, and tempering needed 3 items of one slot.

Re-measured 2026-10-07 after precise combat, the night update and danger by distance (doc 39):

| Act | Median | Min | Max | Before (doc 32 first run) |
|---|---|---|---|---|
| Prologue | 0.5 | 0.5 | 0.5 | 0.5 |
| I: The Grand Tour | 9.7 | 8.7 | 11.4 | 9.9 |
| II: Bouncer Problems | 50.5 | 23.0 | 64.2 | 24.9 |
| III: Retail Therapy | 24.6 | 14.3 | 57.3 | 29.3 |
| IV: The Deep End | 7.9 | 4.4 | 23.5 | 17.3 |
| V: Last Call | 12.7 | 8.2 | 17.0 | 9.6 |
| Finale | 5.6 | 2.4 | 20.0 | 9.9 |
| **Total** | **105.4** | 92.8 | 173.3 | 100.8 (52.8-170.0) |

Act II roughly doubled: its landmark guardians stand in the inner biomes, and the mobs around them are now
danger-scaled up to x2.2 HP. The bot stalled on the forest / desert guardian in 5 of 8 runs and died up to 34 times
in a run, so a human will feel the centre. The guardians themselves stay on their act scaling.

