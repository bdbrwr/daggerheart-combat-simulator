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
| A PC drinks a healing consumable at 2 or fewer unmarked HP | `combat/policy.py` → `LOW_HP_UNMARKED` | Nothing. |
| A PC drinks a stamina consumable with 1 or fewer free Stress slots | `combat/policy.py` → `LOW_STRESS_SLOTS`, `_should_clear_stress` | Nothing. Held until being out of Stress actually costs something - going Vulnerable, or being unable to pay a card's cost - rather than drunk on the first mark. |
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
| **Strange Patterns**: the number the Wizard watches for is drawn at random at the start of each fight rather than written on the sheet, and the trigger clears a Stress when any is marked, otherwise gains a Hope | `features/classes.py` → `_watched_number`, `strange_patterns` | Choosing the number is the player's, and every number is as good as every other. Which reward to take is also theirs; Stress is the scarcer resource here, since running out of it hands every adversary Advantage. |
| **Hold Them Off** spends its 3 Hope only when there are two other adversaries *and* the roll would beat at least one of them | `features/classes.py` → `_hold_them_off` | Using the feature is a choice. Spending 3 Hope on a roll that beats nobody is the one outcome a player at the table would avoid. |
| **Vicious Entangle** never declines, and spends the Hope for a second Restrain only when there's another adversary *and* the GM holds at least 1 Fear | `domain_cards/sage.py` → `_entangle_a_second` | Using the card is a choice. At 0 Fear a temporary condition costs the GM nothing (see below), so the Hope would buy nothing. |
| **Tekaira Armored Beetles** are conjured whenever they aren't already up and a spare Stress slot remains; the Hope to keep them up after a hit is spent only above 3 Hope | `domain_cards/sage.py` → `tekaira_armored_beetles`, `BEETLES_HOPE_FLOOR` | Both are player choices. Marking the last Stress hands every adversary Advantage, which outlives the one threshold the beetles save. |
| **Fire Flies** declines unless it would reach 2 or more adversaries | `domain_cards/sage.py` → `FIRE_FLIES_WORTH_IT` | The card can be cast at one target; against one it's a Hope spent for less than a weapon swing. |
| **Healing Hands** always clears HP rather than Stress, and only fires for an ally at 2 or fewer unmarked HP | `domain_cards/splendor.py` | The card offers the choice; HP is taken because a downed PC is what ends a fight. |
| **Unstoppable** is turned on once the Guardian has 1 or more HP marked, not on the first spotlight | `features/classes.py` → `UNSTOPPABLE_HP_MARKED_BEFORE_USE` | Nothing - the rules let a player flip it whenever they like. Going early runs the damage bonus for longer; going late keeps the damage reduction for the dangerous end of a fight. A knob. |
| **Iron Will** marks its extra Armor Slot only when the hit would drop the Guardian, or would still mark 2+ HP after the free slot | `features/subclasses.py` → `IRON_WILL_WORTH_A_SLOT` | Marking the extra slot is a choice. Slots are finite, so spending one to save a single HP is usually the worse trade - but that is a judgement, not a rule. |
| The Beastbound **Companion**'s "advantage on your next action roll" is taken **immediately**, as a weapon swing with Advantage in the same spotlight | `features/subclasses.py` → `_press_the_advantage` | The companion sheet grants it on a success with Hope "if your next action builds on their success" - a fiction call, assumed always true. A success with Hope also keeps the spotlight, but the loop hands it to a random PC who hasn't acted, so waiting would usually give the advantage to nobody. The cost is that a Beastbound Ranger makes two action rolls in one spotlight, which no other PC can do. The companion roll's Hope is paid out inside the feature, since only the returned roll reaches the loop. |
| **Adept** fires only *below* the Hope floor, so a Wizard pays for an Experience with Hope while they have plenty and with Stress once they don't | `features/subclasses.py` → `adept` | The feature offers the choice on every Experience. Splitting the two by the Hope floor means the doubled modifier is never taken while Hope is plentiful, even though a player might take it. |
| **Not This Time** is spent on an adversary's **critical**, or on any hit against a PC who is **near death** (`NEAR_DEATH_HP_UNMARKED` unmarked HP or fewer) - and never on a miss | `features/classes.py` → `not_this_time` | The card can force a reroll of any attack roll. A natural 20 hits regardless of Evasion and doubles what the damage is worth, so it's both the worst roll the GM makes and the only one a reroll is certain to improve. A hit on a PC one blow from the floor is the other one worth three Hope, because what it's measured against is a PC leaving the fight rather than a number. On any other ordinary hit the same price buys much less, and rerolling a *miss* only gives the GM a second try. |
| **Luckbender** rerolls only a **failed** roll, only at 6 Hope or above, and for an *ally's* roll only if a range check passes | `features/ancestries.py` → `luckbender`, `LUCKBENDER_HOPE_FLOOR` | The card triggers on any action roll, yours or a willing ally's within Close range. Rerolling a success buys nothing measurable; the Hope floor keeps a class Hope feature affordable afterwards, since those are generally the bigger swing. |
| **Adaptability** is used only while 4 or fewer Stress are marked | `features/ancestries.py` → `ADAPTABILITY_MAX_STRESS_MARKED` | The card sets no limit. Marking the last Stress makes a PC Vulnerable for the rest of the fight, which costs far more than one rerolled attack is worth, so the last slots are held back. |

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

The same fractions do second duty as **odds that one particular combatant is in
range**, via `content/aoe.py` → `chance_within`. Some content isn't sweeping an
area at all but needs one named person to be close by — Luckbender rescues "a
willing ally within Close range". With no positions tracked the simulator has to
put a number on that, and reusing the area fraction means both answers come from
one set of knobs: sweeping the range bands moves them together. At Close that's
a 3-in-4 chance the ally is reachable.

### Imperfect information is not modelled

The party is otherwise simulated playing well — an Experience is spent whenever
it helps, a trigger gets its lenient reading. The exception is content whose
decision depends on information a real player does not have at the moment of
choosing.

The simulator can see an adversary's attack roll, the target's Evasion and the
damage about to land; a player sees none of it until afterwards. Implementing
such content would inevitably fire it at precisely the right moments, which does
not model the party more accurately — it models a *better* party than the one at
the table. So it is declared as assessed content with the reasoning recorded,
rather than implemented.

The Faerie's **Wings** is the case this was ruled on: its Stress buys +2 Evasion
against an incoming attack, and a player never learns what that attack needed to
beat. Note the boundary — this covers information genuinely unavailable when the
choice is made, not content that is merely hard to optimise. A trigger the player
can see (their own failed roll, an announced critical, an ally already down) is
ordinary content and gets modelled with a stated policy. That's exactly why
**Not This Time** is implemented and Wings is not.

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
| **Unstoppable**'s "reduce the severity by one threshold" is one HP fewer marked, floored at zero | `features/classes.py` → `unstoppable_reduces_severity` | The SRD names the steps (Severe→Major, Major→Minor, Minor→None) rather than an amount. Each threshold is worth exactly one HP here, so the ladder and "one less HP" are the same thing - and "Minor to None" is what the floor at zero means. |
| **Unstoppable**'s die grows on HP **marked**, so a hit an Armor Slot swallowed entirely doesn't advance it | `features/classes.py` → `unstoppable_grows` | SRD: "after you make a damage roll that deals 1 or more Hit Points to a target". Read as HP the target actually marked, not damage dealt - the other reading would advance the die off a hit that cost the target nothing. |
| The Beastbound **Companion**'s Spellcast Roll *is* its attack roll, so commanding it costs the Ranger their one action roll and the companion never takes a spotlight of its own | `features/subclasses.py` → `companion` | The Ranger Companion sheet says to make a Spellcast Roll to command the companion, and separately that their damage roll uses your Proficiency "on a success" - without saying outright that the two are one roll. Reading them as separate would give a Beastbound Ranger two attacks per spotlight. |
| **Whirlwind**'s additional adversaries are **hit automatically** and take half damage - the attack roll is not re-checked against each one's Difficulty | `domain_cards/blade.py` → `whirlwind` | "All additional adversaries you succeed against with this ability" can be read as a per-target success check, and was implemented that way at first. The trigger is a single successful attack being *used* against the others, which is the reading the table plays. Makes the card meaningfully stronger against high-Difficulty groups. |
| **Hold Them Off** deals the *same damage roll in full* to each additional adversary | `features/classes.py` → `_hold_them_off` | Whirlwind says explicitly that additional targets take half damage; this card says nothing at all, so nothing is halved. |
| **Ranger's Focus** spends its Hope on an attack that has already landed, rather than being declared before the roll | `features/classes.py` → `_rangers_focus` | The card reads "spend a Hope and make an attack". Spending afterwards means a missed Focus attempt costs nothing, which is slightly generous - but deciding beforehand would mean committing Hope without knowing whether the attack even happens. |
| **Strange Patterns** fires once on a roll showing the number on **both** dice, not twice | `features/classes.py` → `strange_patterns` | The card is written as a trigger on the roll rather than on each die, and doubles are already a critical. |
| An attack rolled **against a whole area** ("against all adversaries within Close range") is one roll checked against each target's own Difficulty. The roll counts as a success if it beat the **lowest** Difficulty in the area | `content/aoe.py` → `area_difficulty`, `targets_beaten`; `domain_cards/sage.py` → `fire_flies` | Such a spell has no single Difficulty, but the spotlight rules need to know whether the roll succeeded. Reading it as "you beat somebody" keeps the spotlight on a partial hit; reading it as the highest would hand the spotlight over whenever the toughest adversary shrugged it off. This is a different shape from Whirlwind, which rolls against one target and reuses that roll. |
| Extra damage dice a feature adds for how the attack roll came out (**Face Your Fear**) are rolled **as part of the same damage roll**, not applied afterwards | `content/registry.py` → `extra_damage`, `total_extra_damage`; `items/weapons.py` → `_attack_with` | The SRD says "you deal an extra 1d10 magic damage", which reads as one total. Applying it after the fact would measure it against the target's thresholds a second time and could mark an HP the rules never intended. |
| **Reinforced** (armor) applies to the hit that marked the last Armor Slot, not only to later ones | `features/armor.py` → `reinforced` | The SRD raises the thresholds "when you mark your last Armor Slot". By the time damage responses are consulted that slot has already been marked, so the wearer is in the state the feature describes. Reading it the other way would need the damage pipeline to remember what armor looked like before the hit, for a difference of one HP on one hit per fight. |
| A **weapon's** feature applies only to attacks made with that weapon; an **armor's** applies to everything that happens to its wearer | `items/weapons.py` → `attack_with`; `characters/player_character.py` → `named_features`, `weapon_features` | Not an ambiguity in the rules so much as one the code could easily introduce. Dispatch is holder-scoped by default, so registering a Broadsword's *Reliable* that way would silently add +1 to a Wizard's spell attacks. Armor genuinely is holder-scoped - Fortified changes what any hit costs - so the two reach a fight by different routes. |
| **Massive**/**Powerful** discard the lowest of the dice *the weapon* rolled. Dice a feature added are rolled alongside and added to the same total, out of the discard's reach - and the total is still checked against the thresholds once | `dice/damage.py` → `DiceGroup.discardable`, `dropped`, `critical_bonus` | "Roll an additional damage die and discard the lowest result" doesn't say whose dice. The feature belongs to the weapon, so its discard is read as reaching only the weapon's own pool; the other reading lets a Greatstaff throw away a Wizard's Face Your Fear die. |
| **At most one reroll applies to any roll.** The first piece of content willing to re-make it wins, and nothing else is asked | `content/registry.py` → `remake_action_roll`, `force_adversary_reroll` | Nothing in the SRD forbids a party stacking Luckbender on top of Adaptability for a third attempt at one roll, but no card describes a chain off a single trigger, and allowing it would make a failed roll cheap. |
| A reroll re-makes the **whole** roll, not only the Duality Dice — but re-rolls only the *dice*, never the decisions that fed them: bonuses, the Hope Die and any Experience are worked out once and reused | `items/weapons.py` → `attack_with`; the `_spellcast` helpers in `domain_cards/` | Luckbender and Adaptability both say to reroll the Duality Dice, which would leave an Advantage or Help die standing; re-making everything differs only on rolls that had one, and is declared as a gap on both. Holding the modifiers fixed is not optional — asking content for a roll bonus is the commitment, so several of them spend Hope or mark Stress on being asked, and re-asking would charge twice. |
| A die discarded by **Massive**/**Powerful** doesn't count toward the critical bonus - a crit adds the maximum of the dice that were kept, not of every die rolled | `dice/damage.py` → `critical_bonus` | A crit "adds the maximum possible result of the damage dice"; the SRD doesn't say whether a discarded die is still one of "the damage dice". Counting it would pay for a die that was thrown away. |

## 3. Not implemented

Real rules we knowingly skip. Listed so a result is never mistaken for a
complete simulation of the game.

> **Per-combatant content is tracked in code, not here.** Domain cards,
> ancestries, communities, classes, subclasses, gear features and adversary
> features each declare their own state in `content/registry.py` — *modelled*
> (optionally with declared gaps), *no combat effect*, *insignificant combat
> effect* (both with a reason), or *unimplemented*. Every run prints the
> breakdown per combatant, so this section covers only the rules that apply to
> everyone. Never leave content silently absent when the answer is "it can't
> matter" or "it barely matters": declare it, so a judgement never looks like a
> gap — and never park a decision in *unimplemented*, which reports it as work
> nobody has done.

- **Massive Damage** (SRD-optional: 2× Severe marks 4 HP instead of 3) — `characters/player_character.py`
- **Damage-type resistance and immunity** — nowhere
- **Range and positioning entirely.** Every range band ("Melee", "Very Close", "Far") is treated as always satisfied. This is why `I Am Your Shield` never checks distance, and why adversary features keyed to position are skipped.
- **All conditions except Vulnerable.** Restrained, Hidden, On Fire, Stunned and the rest have no representation.
- **Adversary Fear features** — no adversary does anything but a standard attack
- **Adversary passive features** — named in `adversaries/srd.json` rather than sitting in a code comment, so they reach the coverage block. All three Jagged Knife passives are assessed in `features/adversaries.py`: *Climber* has no combat effect, and *From Above* (+1 expected damage) and *Unseen Strike* (+2) are declared **insignificant**, because damage reaches HP through threshold bands and a bump that size lands within a band far more often than across one. Neither is left *unimplemented* — that state is for work nobody has done, not for a decision
- **Most of the SRD armor table.** Only what the current sheets equip is catalogued in `items/srd.json`. Fortified, Resilient, Shifting, Impenetrable, Painful, Hopeful, Burning and the rest are real mechanics with nothing behind them yet — an armor naming one reports as unimplemented the moment it's equipped
- **Armor Score and armor thresholds are never read from the catalogue.** A sheet carries them already resolved (see the standing rule on sheet-resolved values), so `items/*.json` records them as provenance only. The consequence is that a sheet whose numbers don't match the armor it names will not be caught
- **Subclass features above the foundation tier.** Specialization (level 5) and mastery (level 8) features are declared as gaps on each subclass rather than implemented, since the current party has neither tier
- **Nothing ever attacks the Beastbound companion**, so its Stress, and dropping out of the scene when its last Stress is marked, don't exist here. It contributes damage and carries no risk
- **Damage types.** Nothing records whether damage is physical or magic, so Unstoppable's physical-only reduction applies to every hit — declared as a gap where it's registered, and it makes the feature slightly better here than at a table
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
- **"Near death" means 2 or fewer unmarked HP** on whoever came closest. Not a game concept — `characters/player_character.py` → `NEAR_DEATH_HP_UNMARKED`, `is_near_death`. It began as a reporting threshold and is now a trigger content keys on too (Not This Time), which is why it lives on the character rather than in `simulation/`: a report that called a fight a near thing on a different number from the one the party plays to would be describing two different edges
- **One seed per command** seeds every encounter in it, so variations face the same dice — `simulation/cli.py`
