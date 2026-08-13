# Simulation rules

Not everything this simulator does is Daggerheart. A great deal of it is
decisions a person at the table would make case by case, which a simulator has
to freeze into a fixed policy — plus a handful of places where the SRD is silent
and we had to pick a reading, plus rules we knowingly skip.

This file catalogues all of them. It exists because the project's whole premise
is being more trustworthy than the official Battle Points math, and a number is
only trustworthy if a reader can tell which parts of it are the rules and which
parts are our assumptions.

**When you implement a mechanic, add its entry here in the same change**, and
keep the reasoning next to the code as well. Entries name the code that
implements them so the two can be checked against each other.

---

## 1. Simulation policies

A choice the rules leave to a player or GM, which we automate. These are the
entries most likely to be worth *changing* — each one is a knob that could move
the balance numbers, and none of them is wrong in a rules sense.

| Policy | Where | What the rules actually say |
|---|---|---|
| A free Armor Slot is **always** marked against any damage, including a hit that would only mark 1 HP | `characters/player_character.py` → `should_mark_armor_slot` | Marking a slot is a **choice**. Always spending is our simplification, and it front-loads the party's durability. |
| The party focuses fire on the adversary with the most HP marked | `combat/policy.py` → `choose_pc_target` | Nothing. Target choice is entirely the players'. |
| An adversary attacks whoever hit it last, else the last PC to attack anything, else the first PC standing | `combat/policy.py` → `choose_adversary_target` | Nothing. Target choice is the GM's. |
| A PC drinks a healing consumable at 2 or fewer unmarked HP | `combat/policy.py` → `LOW_HP_REMAINING` | Nothing. |
| A PC spends Hope on an Experience only above 5 Hope, and we assume an Experience always applies | `combat/policy.py` → `EXPERIENCE_HOPE_FLOOR`, `_experience_bonus` | Whether an Experience applies is a fiction call. Assuming it always does is optimistic. |
| Which PC acts is random among those who haven't acted this pass; everyone goes once before anyone goes twice | `combat/fight.py` → `_next_pc` | Daggerheart has no turn order at all. This stops one lucky PC acting forever. |
| The GM spotlights at most **party size + 1** adversaries per turn | `combat/state.py` → `max_activations_per_gm_turn` | The SRD lets the GM spend Fear to spotlight **as many as they can afford**. Ours is a cap that a greedy simulator needs; a knob worth sweeping. |
| The GM spends Fear greedily on extra activations and on nothing else | `combat/fight.py` → `_take_gm_turn` | Fear also pays for adversary Fear features and GM moves, neither implemented. |
| PCs always take **Avoid Death** as their death move | `characters/player_character.py` → `take_damage`, `avoid_death` | Three death moves exist. Blaze of Glory and Risk It All are not modelled. |
| An unconscious PC is never revived and takes no further part | `characters/player_character.py` → `clear_hp` | Per the SRD an ally can clear a downed PC's HP to revive them. Spending a turn on that isn't modelled. |
| **Get Back Up**: pay the Stress if the hit would drop the PC, otherwise only while a spare Stress slot remains | `domain_cards/blade.py` → `_worth_a_stress` | Using the card is a choice. |
| **I Am Your Shield**: step in only when the ally is closer to going down than the shielder, and never on the shielder's last HP | `domain_cards/valor.py` → `_worth_shielding` | Using the card is a choice. |
| A PC picks **at random among the options they can actually use** - every ability whose resources they can pay, plus their weapon attack | `content/registry.py` → `action_options`, `use_free_abilities`; `combat/policy.py` → `_make_the_roll` | Nothing; a player weighs their options. Random-among-viable is the stand-in until there's something better. **No automated scoring** - deliberately not built. |
| A **no-rest encounter** assumes *every* per-rest ability was already spent | `combat/rest.py` → `Rest.NONE` | Nothing carries between encounters yet, so the simulator can't know which were actually used. Conservative, and makes a no-rest fight harder than it may really be. |
| **Slumber** is only cast when the GM holds 3+ Fear; **Arcane Barrage** spends Hope down to a floor of 2; **Tava's Armor** waits until somebody has run out of Armor Slots | `domain_cards/codex.py` | All three are player choices the rules leave open. Each is a knob. |
| **Healing Hands** always clears HP rather than Stress, and only fires for an ally at 2 or fewer unmarked HP | `domain_cards/splendor.py` | The card offers the choice; HP is taken because a downed PC is what ends a fight. |

### Area of effect, standing in for range

No positioning is modelled, so an ability that hits "all targets within X range"
would otherwise hit everything, every time — which is far more generous than a
table, where the GM places adversaries and the spread of a fight is what makes an
AOE good or wasted. Instead, **the range band caps how many adversaries an AOE
can reach**:

| Range band | Adversaries reached |
|---|---|
| Far | all of them |
| Close | 75%, and never all — at least one is always out of it |
| Very Close | at most a third |
| Melee | 2, or 3 once there are a lot of adversaries |

As a formula over `n` living adversaries, with the result floored at 1:

- Far: `n`
- Close: `min(n * 3 // 4, n - 1)`
- Very Close: `n // 3`
- Melee: `2`, or `3` when `n >= MANY_ADVERSARIES`

`MANY_ADVERSARIES` is a knob, not a rule — it needs a number and 6 is a
reasonable first guess. The percentages are knobs too, and worth sweeping: they
are the whole of how much an AOE ability is worth in this simulator.

The cap is the **total** number of adversaries caught, uniformly — including,
for an ability that extends an attack that already hit someone, the adversary
already hit. There is no separate allowance for "additional" targets.

Worth knowing what that costs: an ability at Very Close reaches `n // 3`, so
extending a single-target attack adds nobody until there are 6 adversaries in
the fight. Whirlwind is inert in a four-adversary encounter. That is the
intended consequence of a uniform rule, not an oversight.

Which adversaries get picked is a separate policy question. Focus fire already
governs single-target selection, so an AOE takes the most wounded first.

### How much a PC can do before passing the spotlight

The rules put no hard number on the actions that don't require a roll, so a
simulator left alone will stack every free ability a PC can afford, every time —
a PC who never lets go of the spotlight. Real play doesn't look like that. The
budget per spotlight is therefore:

- **Consumables are free** and never count against it.
- Then **either** two actions requiring no roll, **or** one action requiring no
  roll plus one action that does.
- **Riders and damage responses don't count** against any of it. A rider
  modifies a roll that is already happening, and a damage response fires when
  damage arrives rather than when its holder acts.

So at most one action roll per spotlight, which is the actual rule, and at most
two other things around it, which is the simplification.

A PC who spends their budget without making an action roll doesn't pass the
spotlight — correctly, since only a roll can. Play moves to the next PC who
hasn't acted this pass. That can't stall a fight in practice because free
abilities cost Hope, Stress or a per-rest use and run out, but it is why the
action cap in section 4 exists.

### Temporary conditions, standing in for condition tracking

Conditions other than Vulnerable aren't tracked. Rather than dropping an ability
that applies one — which would understate it — **applying a temporary condition
costs the GM 1 Fear**, floored at zero.

This is a simplification, but a well-grounded one: several of these abilities are
written to end when the GM spends a Fear to clear them (Slumber says exactly
that), so draining the pool is close to what the condition actually costs the GM
side. It also lands in the one currency the simulator already tracks carefully,
which means the effect shows up in the Fear numbers rather than vanishing.

Edge case worth remembering: a GM already at 0 Fear pays nothing, so the
condition is free to them. That understates the effect, and it happens most in
exactly the fights where Fear is scarce.

## 2. Rules interpretations

The SRD is silent or ambiguous, and a simulator can't be. Each of these is a
reading we committed to; flipping one is a small change with a real effect on
the numbers.

| Interpretation | Where | The ambiguity |
|---|---|---|
| **Get Back Up** triggers on the damage *amount* reaching the Severe threshold, so it applies even after an Armor Slot softened the hit, and the two reductions **stack** (Severe: 3 HP → 1) | `domain_cards/blade.py` → `get_back_up` | "When you take Severe damage" could mean the number rolled, or the severity after other reductions. The other reading makes the pair order-dependent for no stated reason. |
| **I Am Your Shield** swaps who the attack targets **before it is rolled**, so it resolves against the shielder's Evasion | `domain_cards/valor.py` → `i_am_your_shield` | The effect clause says "make yourself the target of the attack instead"; the trigger clause ("when an ally would take damage") reads as firing after a hit is known, which would use the ally's Evasion instead. |
| Forced Stress that doesn't fit marks **1 HP total**, not one per Stress that wouldn't fit | `characters/player_character.py` → `mark_stress` | SRD: "When a character must mark 1 or more Stress but can't, they mark 1 HP instead." Singular, read as covering the whole requirement. |
| A die discarded by **Massive**/**Powerful** doesn't count toward the critical bonus - a crit adds the maximum of the dice that were kept, not of every die rolled | `dice/damage.py` → `critical_bonus` | A crit "adds the maximum possible result of the damage dice"; the SRD doesn't say whether a discarded die is still one of "the damage dice". Counting it would pay for a die that was thrown away. |

## 3. Not implemented

Real rules we knowingly skip. Listed so a result is never mistaken for a
complete simulation of the game.

> **Per-character content is tracked in code, not here.** Domain cards,
> ancestries, communities, classes and subclasses each declare their own state
> in `content/registry.py` — *modelled* (optionally with declared gaps),
> *no combat effect* (with a reason), or *unimplemented*. Every run prints the
> breakdown per character, so this section covers only the rules that apply to
> everyone. Never leave content silently absent when the answer is "it can't
> matter": declare it, so a judgement never looks like a gap.

- **Massive Damage** (SRD-optional: 2× Severe marks 4 HP instead of 3) — `characters/player_character.py`
- **Damage-type resistance and immunity** — nowhere
- **Range and positioning entirely.** Every range band ("Melee", "Very Close", "Far") is treated as always satisfied. This is why `I Am Your Shield` never checks distance, and why adversary features keyed to position are skipped.
- **All conditions except Vulnerable.** Restrained, Hidden, On Fire, Stunned and the rest have no representation.
- **Adversary Fear features** — no adversary does anything but a standard attack
- **Adversary passive features** — Climber, From Above, Unseen Strike are noted in `adversaries/srd.py` for debugging but not modelled
- **Guardian class and subclass features** — the steps are marked and skipped in `combat/policy.py`, not faked
- **Help an ally** — step 4 of the PC turn priority; needs more than one PC
- **Secondary weapons** — loaded from the sheet, never used
- **Multi-slot armor marking** — at most one Armor Slot is marked per hit
- **Nothing marks a PC's Stress except their own card costs.** GM moves and adversary features are the SRD's main sources of Stress, and neither exists here, so Stress rises far more slowly than at a table — and `Vulnerable` is correspondingly rare.

### Order of unordered data is never load-bearing

A loadout is an unordered list - the order someone typed their cards in. Nothing
in the simulation may depend on it, because arbitrary order carries no
information and would silently decide which abilities a PC ever gets to use.
The same goes for the spells inside a multi-spell card, and for which PC acts.

Implemented by shuffling the candidates and taking the first that accepts, which
over a random permutation is a uniform choice among the willing ones. That
depends on a contract worth stating plainly: **declining must be side-effect
free.** An ability asked whether it wants the roll must not spend Hope, mark
Stress or claim a per-rest use unless it commits.

The **weapon attack is one of the candidates**, not a fallback reached only when
every card declines. Swinging is a real choice, and for some characters usually
the right one.

## 4. Simulator scaffolding

Not game rules at all — machinery that exists because this is software.

- **Action cap**: a fight is abandoned as `UNRESOLVED` after 500 PC actions, so an unwinnable matchup reports instead of hanging — `combat/fight.py` → `MAX_PC_ACTIONS`
- **Unresolved fights are excluded** from every distribution, since the cap is not a fight length — `simulation/summary.py` → `SimulationSummary.resolved`
- **"Near death" means 2 or fewer unmarked HP** on whoever came closest. A reporting threshold, not a game concept — `simulation/summary.py` → `NEAR_DEATH_HP_REMAINING`
- **One seed per command** seeds every encounter in it, so variations face the same dice — `simulation/cli.py`
