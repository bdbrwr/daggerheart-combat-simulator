# SRD adversaries: what's ported

The SRD lists **129 adversaries**. This file tracks which of them are in
`srd.json` and which are still outstanding, because an SRD update is expected
(25 Aug) that will add more, and without a list there is no way to tell a new
adversary from one we simply hadn't got to.

## How porting works

- **Batches of five**, so a change stays reviewable - a batch is usually five
  stat blocks plus whatever features they need.
- **Tier ascending**, and within a tier the book's own print order, which is what
  `srd.json` is ordered by too.
- **Social adversaries are skipped.** They aren't used in combat encounters, and
  a simulator that only models combat has nothing to say about them.
- Numbers are taken from the reference JSON in `.reference/` and **checked
  against the printed page** in the SRD PDF before the batch lands.

### Mechanics are implemented; usage policies are ruled on

Implementing a feature is two jobs, and only the first is a coding job:

- **The mechanics** — what the SRD says the feature does. Read them off the page
  and write them.
- **The usage policy** — when a GM would actually reach for it. This is a
  judgement about the game and it belongs to the user, exactly like the decision
  to dismiss content as having no combat effect.

Batch 1 got this wrong: usage thresholds were invented, written into the code as
though settled, and recorded in `SIMULATION-RULES.md` as policies nobody had
chosen. The process that replaces it:

1. **Hand over the batch's policy table first** — one row per feature that
   involves a choice, naming the cost and the actual trade. Rulings come back
   before the policies are written.
2. **Until a ruling, the placeholder is "fires whenever its cost can be paid."**
   The least inventive option. Never a threshold like "only when it reaches two
   targets" — those are knobs, and a knob nobody set is worse than no knob.
3. **A placeholder is labelled as one**, in the docstring (`USAGE POLICY -
   awaiting a ruling`) and in the table above. Nothing reaches
   `SIMULATION-RULES.md`'s policy list until it has been ruled on, because that
   file is a record of decisions and an invented entry corrupts it.
4. **Never policy a feature into never firing because of something the simulator
   leaves out.** A feature being weaker *on damage* is a fact about damage; if
   the thing that justifies it at a table is unmodelled, that is a gap of ours,
   and the gap is declared where the feature is registered rather than smuggled
   into a policy.

## What a "ported" adversary is and isn't

Porting a stat block gets its **numbers** into the simulator: Difficulty,
thresholds, HP, Stress, attack modifier and standard-attack damage. Those work
immediately, and for many adversaries that is most of what makes them dangerous.

Its **features** are a separate job, and the standing rule is that the machinery
for one gets built the first time a feature needs it. A feature with nothing
behind it yet reports as *unimplemented* in the coverage block, which is honest -
the report says so on every run - but don't mistake a ported adversary for a
fully simulated one until its features are ticked off below.

## Two things settled while porting

- **Type carries no mechanics.** The SRD says only that "an adversary's type
  represents the role they play in a conflict", with one descriptive line each.
  Everything that sounds like a type rule is printed as a named feature instead -
  `Minion (X)`, `Horde (X)`, `Relentless (X)`, `Slow`, `Arcane Form`,
  `Armored Carapace` are all in the SRD's list of example passives. So `type` is
  carried as data on `Adversary` and the fight loop never reads it.
- **Feature names drop the category suffix.** The book prints
  `Relentless (3) - Passive`; the catalogue writes `"Relentless (3)"`. The
  suffix says which hook a feature belongs on, which the code expresses by
  which decorator it registers with.

---

## Ported

### Tier 1

Feature states are the four in `CLAUDE.md`: **implemented**, **no combat
effect** (nothing here for it to touch), **irrelevant** (represented, but too
small to change an outcome), **not implemented** (work still to do).

| Adversary | Type | Batch | Features |
|---|---|---|---|
| Acid Burrower | Solo | 1 | Relentless (3), Earth Eruption, Spit Acid, Acid Bath *implemented* |
| Bear | Bruiser | 1 | Momentum, Bite *implemented* · Overwhelming Force *no combat effect* |
| Cave Ogre | Solo | 1 | Bone Breaker, Ramp Up, Hail of Boulders, Rampaging Fury *implemented* |
| Construct | Solo | 1 | Relentless (2), Weak Structure, Trample, Overload, Death Quake *implemented* |
| Deeproot Defender | Bruiser | 1 | Ground Slam, Grab and Drag *implemented* |
| Dire Wolf | Skulk | 2 | Pack Tactics, Hobbling Strike *implemented* |
| Giant Mosquitoes | Horde (5/HP) | 2 | Horde (1d4+1), Flying (2), Bloodsucker *implemented* |
| Giant Rat | Minion | 2 | Minion (3), Group Attack *implemented* |
| Giant Scorpion | Bruiser | 2 | Momentum, Double Strike, Venomous Stinger *implemented* |
| Glass Snake | Standard | 2 | Armor-Shredding Shards, Spinning Serpent, Spitter *implemented* |
| Jagged Knife Bandit | Standard | earlier | Climber *no combat effect* · From Above *irrelevant* |
| Jagged Knife Sniper | Ranged | earlier | Unseen Strike *irrelevant* |

---

## Outstanding

### Tier 1, in print order

Next batch starts at the top of this list. Types are confirmed against the
printed page as each batch is read, so a blank one is unknown rather than
unknown-to-be-blank - and a Social found there is skipped rather than ported.

1. Courtier — **Social, skipped**
2. Harrier — Standard
3. Archer Guard — Ranged
4. Bladed Guard — Standard
5. Head Guard — Leader
6. Jagged Knife Hexer — Support
7. Jagged Knife Kneebreaker — Bruiser
8. Jagged Knife Lackey — Minion
9. Jagged Knife Lieutenant
10. Jagged Knife Shadow
11. Merchant
12. Minor Chaos Elemental
13. Minor Fire Elemental
14. Minor Demon
15. Minor Treant
16. Green Ooze
17. Tiny Green Ooze
18. Red Ooze
19. Tiny Red Ooze
20. Petty Noble
21. Pirate Captain
22. Pirate Raiders
23. Pirate Tough
24. Sellsword
25. Skeleton Archer
26. Skeleton Dredge
27. Skeleton Knight
28. Skeleton Warrior
29. Spellblade
30. Swarm of Rats
31. Sylvan Soldier
32. Tangle Bramble Swarm
33. Tangle Bramble
34. Weaponmaster
35. Young Dryad
36. Brawny Zombie
37. Patchwork Zombie Hulk
38. Rotted Zombie
39. Shambling Zombie
40. Zombie Pack

### Tiers 2-4

Not started. The SRD lists them under TIER 2 (LEVELS 2-4), TIER 3 (LEVELS 5-7)
and TIER 4 (LEVELS 8-10); they get enumerated here when tier 1 is done, so this
file doesn't carry eighty rows nobody is working from yet.

---

## Settled

- **A printed `Thresholds: None` is stored as 9999**, via
  `catalogue.py`'s `NO_THRESHOLD`. Every case found so far is an adversary with
  fewer HP than the threshold could ever matter for - a Minion is defeated by any
  damage, the Tiny Green Ooze has 2 HP - so a threshold out of reach says exactly
  the right thing and every hit lands in the lowest band. Both `null` and the
  string `"None"` are accepted.
- **A feature's name can carry a parameter.** `Relentless (3)` and
  `Relentless (2)` are one feature with an argument, so it registers once as
  `adversary:Relentless` and reads X off whichever stat block carries it. Same
  machinery will serve `Minion (X)` and `Horde (X)`.
- **`Relentless (X)` spends from the same activation budget as everyone else.**
  Its extra spotlights count against the party size + 1 cap and each costs the
  usual Fear. The cap is our simulation rule rather than a game rule - the SRD
  puts no limit on activations at all - and a feature that reached around it
  would defeat the point of having it.
- **`harden_damage` is the counterpart to `soften_damage`**, for content that
  makes a hit mark *more* HP. Both sides of the table run the pipeline, and
  hardening is always asked second so "when you mark HP" is measured against
  what the hit finally cost.

- **Conditions are records with an end condition** — `content/conditions.py`.
  Vulnerable is modelled; Restrained is ruled to have no combat effect here and
  is declared as a gap on each feature that applies it.
- **Direct damage** skips the Armor Slot and nothing else.
- **Reaction Rolls** are Duality Dice plus a trait, with the Hope/Fear outcome
  unread. A critical ignores the whole effect.
- **Adversary Experiences will not be modelled.** Ruled out rather than left
  outstanding. The SRD makes them optional and GM-facing - "the GM can spend a
  Fear to add an adversary's relevant Experience to raise their attack roll or
  increase the Difficulty of a roll made against them" - and the objection is
  the Fear economy: this simulator already commits a lot of Fear to extra
  activations, which an Experience competes with while buying a comparatively
  minor bonus on one roll. They stay in each entry's `notes` so the entry is
  still checkable against the page. Do not put this back on a list of work.
- **Machinery batch 2 built, all reusable.** `standard_damage` /
  `standard_attack_damage` swaps the dice a *printed* attack rolls, asked from
  inside the damage roll so a feature that brought its own dice is never
  touched - it serves `Horde (X)` and `Pack Tactics` at once. `on_attacked`
  belongs to whoever was hit rather than whoever swung, and is handed the
  attacker's weapon because range is what Armor-Shredding Shards keys on.
  `on_spotlight` fires on the spotlight arriving rather than on a choice, which
  is what lets the Spitter Die keep rolling however the Snake spends its turns.
  `Condition.effect` has its first user and its first announced moment,
  `BEFORE_AN_ACTION_ROLL`. `Adversary.attack` gained `direct=`, matching
  `area_attack`, for a feature whose own attack is direct without a passive
  granting it.
- **`Flying (X)` resolves into `Adversary.difficulty` at spawn time**, via
  `content/registry.py`'s `difficulty_bonus` hook - the only hook with no
  `fight` in its signature, because it never runs during one. The four places
  that read Difficulty are therefore already correct and none of them knows the
  feature exists. The "while flying" qualifier moves to the author: the number
  on the stat block is the *average* uplift, so a creature airborne half the
  time is written `Flying (1)` rather than checked every round.

## Batch 2 rules rulings

Decided before any of batch 2's feature code was written. These are rules
questions rather than usage policies — they change what a feature *is*, not when
a GM reaches for it.

- **`Minion (X)` overkill only defeats Minions of the same adversary name.** For
  every X damage, an additional one of *that stat block* goes down. A useful
  consequence: they all share a Difficulty, so there is no per-target check to
  make — "the attack would succeed against" is answered once.
- **`Horde (X)` replaces the standard attack's dice**, rather than penalising the
  total. Needs a hook that swaps an adversary's attack dice; none exists yet.
- **A Group Attack is one activation.** However many Minions it sweeps in, the
  GM turn is charged once — the feature is one shared roll, so it costs one
  spotlight. How many it reaches is the feature's own rule and the area rules.
- **Poison is modelled**, and it is a *family* rather than one condition. The
  Giant Scorpion's ends on a Knowledge Roll at Difficulty 16; the Druid
  beastforms' poisons have different effects and take the default end (the GM
  spending a Fear). This is the first real use of `Condition.effect` — the
  Scorpion's is "roll a d6 before an action roll; on 4 or lower, mark a Stress".
- **`Flying` is parameterised as `Flying (X)`**, X being the Difficulty bonus, so
  it is authorable per adversary. The SRD prints the name bare; we write
  `Flying (2)` for the Giant Mosquitoes. The "while flying" qualifier is treated
  as always true for these — narratively right for the tier 1–2 fliers
  (mosquitoes, bats), and a tier 4 dragon may well want a different number rather
  than a different rule.
- **Armor-Shredding Shards keys off the attacker's weapon range.** Every attacker
  is assumed to have attacked from the greatest range their weapon allows, so a
  Melee-only weapon triggers it and a Far one doesn't.
- **The Spitter Die is a real per-fight die**, rolled at each of the Snake's
  spotlights — including the extra one the feature grants — with a 2-in-6 chance
  of a Far Reaction Roll for 1d4.
- **Spitter's extra spotlight is granted once, on the turn the die is
  introduced** — not every turn the die is active, and not for rolling 5 or
  higher. Spending the Fear buys the die *and* one extra spotlight that turn;
  every turn afterwards the die keeps rolling but buys no more spotlights.

  So it is a one-off `grant_activation` (the `Overload` shape), not an
  `activation_limit` (the `Relentless` shape). It stays inside the party size + 1
  cap and the extra activation still costs the usual Fear.

## Usage policies — ruled

Implementing a feature is two jobs: the **mechanics**, which come from the SRD,
and the **usage policy** - when a GM would actually reach for it. The second is a
judgement about the game and belongs to the user.

The rulings came back as **four general rules covering classes of feature**,
rather than as a decision per feature. They live in `SIMULATION-RULES.md`; this
is the summary and the per-feature mapping.

1. **An Action costing Stress** is available once the adversary is hurt enough:
   with X Stress slots still free, when `hp_unmarked <= X**2 + 1`. So 10 or fewer
   unmarked HP at three slots, 5 at two, 2 at one - the last slot opening on the
   same near-death line the party plays to. `Adversary.will_spend_stress`.
2. **A Reaction costing Stress** fires on every trigger it can pay for. Rule 1
   deliberately does not apply: a reaction has one moment, not a choice of them.
   `Adversary.can_spend_stress`, called directly.
3. **An attack feature worse than the standard attack by ≥ 2 expected damage
   whose point is applying a condition** is used only against a target that
   doesn't already have that condition. `CONDITION_ATTACK_EV_MARGIN`.
4. **Everything else is random among the options whose costs can be paid** - the
   same rule the party already plays by. This is the standing default, so a
   feature with nothing special about it needs no policy written for it at all.

### Batch 1

| Feature | Cost | Ruled by |
|---|---|---|
| Earth Eruption | 1 Stress | rule 1 |
| Bite | 1 Stress | rule 1. The sharpest case in the catalogue: 7 HP against 2 Stress means the Bear can't Bite until 5 unmarked HP |
| Hail of Boulders | 1 Stress (+ the Ramp Up Fear already paid) | rule 1 |
| Trample | 1 Stress | rule 1 |
| Overload | 1 Stress | rule 2 - a Reaction, so all four Stress ride the Construct's first four landed attacks, from full health |
| Spit Acid | free | rule 4 |
| Ground Slam | free | rule 4 |
| Grab and Drag | 1 Fear on a hit | rule 3 catches it on the numbers (5.5 against 7.5, exactly the 2.0 margin) but the condition it applies is Restrained, which has no representation here - so there is nothing to check and it falls through to rule 4 |

### Batch 2

All eleven features are implemented. The policies are settled.

| Feature | Cost | Ruled by |
|---|---|---|
| Hobbling Strike (Dire Wolf) | 1 Stress | rule 1 |
| Double Strike (Scorpion) | 1 Stress | rule 1. Explicitly **no** target-count threshold, so it can be spent against a lone PC for nothing but the Stress |
| Spinning Serpent (Glass Snake) | 1 Stress | rule 1. Explicitly no "only when it reaches 2+ PCs" threshold - though the AOE rules themselves may want revisiting |
| Bloodsucker (Mosquitoes) | 1 Stress | rule 2 - a Reaction, so every hit that marked HP |
| Venomous Stinger (Scorpion) | 1 Fear on a hit | rule 3. 1d4+4 at 6.5 against the standard 1d12+2 at 8.5, exactly the 2.0 margin, and Poison **is** modelled - so this is the first feature the rule actually acts on |
| Group Attack (Giant Rat) | 1 Fear | Used when it beats what one Minion's standard attack would do, i.e. **2 or more** of that stat block in range. **Generalised to all Minion group attacks**, not written for the Rat |
| Spitter (Glass Snake) | 1 Fear, once | Bought at the Snake's first spotlight the Fear allows - it is worth strictly more the earlier it lands |

### The margin in rule 3 wants a validation check

It is set at 2 from a sample of two, both sitting on exactly 2.0, so right now it
separates nothing - and twelve of the SRD's ~129 adversaries are ported. Once
enough condition-applying attack features exist, `validation/` should check the
margin against the whole catalogue and the number should be revisited. Recorded
here rather than treated as settled.

## Still open

- **Three PC cards still charge condition Fear the old way.** Slumber, Vicious
  Entangle and Tava's Armor spend the GM's Fear at the moment they apply a
  condition, rather than going through `Condition` and `when_the_gm_pays`. The
  same rule is expressed twice until they migrate.
- **Area attacks can't be force-rerolled.** `Not This Time` re-makes "an attack
  roll", and one already measured against five different Evasions can't be
  re-made without unwinding all of them. Declared as a gap on the card.
