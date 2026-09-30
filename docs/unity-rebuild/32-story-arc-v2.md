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
