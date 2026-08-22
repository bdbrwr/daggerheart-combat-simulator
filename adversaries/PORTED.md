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
| Harrier | Standard | 3 | Fall Back *implemented* · Maintain Distance *no combat effect* |
| Archer Guard | Ranged | 3 | Hobbling Shot *implemented* |
| Bladed Guard | Standard | 3 | Detain *implemented* · Shield Wall *no combat effect* |
| Head Guard | Leader | 3 | Rally Guards, On My Signal (5), Momentum *implemented* |
| Jagged Knife Bandit | Standard | earlier | Climber *no combat effect* · From Above *irrelevant* |
| Jagged Knife Hexer | Support | 3 | Curse, Chaotic Flux *implemented* |
| Jagged Knife Kneebreaker | Bruiser | 4 | I've Got 'Em, Hold Them Down *implemented* |
| Jagged Knife Lackey | Minion | 4 | Minion (3), Group Attack *implemented* — both were already generic, so this stat block needed no new code at all |
| Jagged Knife Lieutenant | Leader | 4 | Tactician, More Where That Came From, Coup de Grace, Momentum *implemented* |
| Jagged Knife Shadow | Skulk | 4 | Backstab, Cloaked *implemented* |
| Jagged Knife Sniper | Ranged | earlier | Unseen Strike *irrelevant* |
| Minor Chaos Elemental | Solo | 4 | Arcane Form, Sickening Flux, Remake Reality, Magical Reflection, Momentum *implemented* — Arcane Form was the last one outstanding and landed with damage-type resistance |
| Minor Fire Elemental | Solo | 5 | Relentless (2), Scorched Earth, Explosion, Consume Kindling, Momentum *implemented* |
| Minor Demon | Solo | 5 | Relentless (2), All Must Fall, Hellfire, Reaper, Momentum *implemented* |
| Minor Treant | Minion | 5 | Minion (5), Group Attack *implemented* — needed no new code at all, like the Jagged Knife Lackey |
| Green Ooze | Skulk | 5 | Slow, Acidic Form, Envelop, Split *implemented* |
| Tiny Green Ooze | Skulk | 5 | Acidic Form *implemented* — shares the Green Ooze's registration |
| Red Ooze | Skulk | 6 | Ignite, Split (Tiny Red Ooze) *implemented* · Creeping Fire *no combat effect* |
| Tiny Red Ooze | Skulk | 6 | Burning *implemented* |
| Pirate Captain | Leader | 6 | Swashbuckler, Reinforcements, No Quarter, Momentum *implemented* |
| Pirate Raiders | Horde (3/HP) | 6 | Horde (1d4+1), Swashbuckler *implemented* — needed no new code of its own |
| Pirate Tough | Bruiser | 6 | Swashbuckler, Clear the Decks *implemented* |

---

## Outstanding

### Tier 1, in print order

Next batch starts at the top of this list. Types are confirmed against the
printed page as each batch is read, so a blank one is unknown rather than
unknown-to-be-blank - and a Social found there is skipped rather than ported.

1. Courtier — **Social, skipped**
2. Petty Noble — **Social, skipped**
3. Sellsword — Minion
4. Skeleton Archer — Ranged
5. Skeleton Dredge — Minion
6. Skeleton Knight
7. Skeleton Warrior
8. Spellblade
9. Swarm of Rats
10. Sylvan Soldier
11. Tangle Bramble Swarm
12. Tangle Bramble
13. Weaponmaster
14. Young Dryad
15. Brawny Zombie
16. Patchwork Zombie Hulk
17. Rotted Zombie
18. Shambling Zombie
19. Zombie Pack

Types down to Skeleton Dredge were confirmed against the printed page (SRD
pp. 78–81), which is also where the Socials were spotted. **Batch 7 starts at the
Sellsword**, and the next five are the Sellsword, Skeleton Archer, Skeleton
Dredge, Skeleton Knight and Skeleton Warrior.

Batch 7 opens cheaply again: the **Sellsword** is `Minion (4)` plus `Group
Attack`, both generic since batch 2, so it should need no code at all — the third
stat block to come online with its JSON entry. The **Skeleton Dredge** is the
same shape. Types for the two Skeletons after Dredge are unconfirmed and want
checking against the page as that batch is read.

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
3. **A feature whose point is applying a condition** is used only against a
   target that doesn't already have that condition. The check lives in each such
   feature, because which ones they are is a reading of the printed text.
   Deliberately **not** gated on expected damage: a policy may not turn on a
   comparison nobody at the table performs, which is what removed
   `CONDITION_ATTACK_EV_MARGIN`.
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
| Grab and Drag | 1 Fear on a hit | rule 4. The condition it applies is Restrained, which has no effect of its own here, so there is nothing for rule 3's check to protect and declining would hold back an attack over nothing |

### Batch 2

All eleven features are implemented. The policies are settled.

| Feature | Cost | Ruled by |
|---|---|---|
| Hobbling Strike (Dire Wolf) | 1 Stress | rule 1 |
| Double Strike (Scorpion) | 1 Stress | rule 1. Explicitly **no** target-count threshold, so it can be spent against a lone PC for nothing but the Stress |
| Spinning Serpent (Glass Snake) | 1 Stress | rule 1. Explicitly no "only when it reaches 2+ PCs" threshold - though the AOE rules themselves may want revisiting |
| Bloodsucker (Mosquitoes) | 1 Stress | rule 2 - a Reaction, so every hit that marked HP |
| Venomous Stinger (Scorpion) | 1 Fear on a hit | rule 3, and the only feature it acts on: the sting's point is the Poison, so it is held back against a target already Poisoned. Poison **is** modelled, so the check has something to read |
| Group Attack (Giant Rat) | 1 Fear | Used when it beats what one Minion's standard attack would do, i.e. **2 or more** of that stat block in range. **Generalised to all Minion group attacks**, not written for the Rat |
| Spitter (Glass Snake) | 1 Fear, once | Bought at the Snake's first spotlight the Fear allows - it is worth strictly more the earlier it lands |

### Batch 3

Ten features across five stat blocks, and the four rules covered every one of
them — no feature in this batch needed a policy of its own. The rulings that had
to be made were **rules readings** instead — what a feature *is*, not when a GM
reaches for it — and all four are now in `SIMULATION-RULES.md` §2.

| Feature | Cost | Ruled by |
|---|---|---|
| Fall Back (Harrier) | 1 Stress | rule 2 — a Reaction, so all three Stress ride the first three melee attackers, from full health |
| Hobbling Shot (Archer Guard) | 1 Stress, paid on a success | rule 1, which never bites here: 3 HP against two Stress puts the Archer inside the line from full health |
| Detain (Bladed Guard) | 1 Stress, paid on a success | rule 1 to gate, then rule 4. Rule 3 doesn't reach it — the Restrain isn't the point of the attack, it is a Stress spent on top of an ordinary swing |
| Chaotic Flux (Hexer) | 1 Stress | rule 1, capped at three targets at Very Close |
| Curse — applying it (Hexer) | free | rule 4, with the one check that the target isn't Cursed already |
| Curse — each conversion | 1 Stress | rule 2 — every Hope roll it can pay for |
| On My Signal (Head Guard) | free | No policy: nothing about it is a choice. It arms on the first spotlight and ticks on its own |
| Momentum (Head Guard) | — | already modelled for the Bear |
| Rally Guards (Head Guard) | 2 Fear | rule 4. The proposal to hold it back below 2 allies in range — the `GROUP_ATTACK_WORTH_IT` shape — was put and declined, so a Head Guard with nobody in range will still spend 2 Fear on an activation the GM could have had for 1. Ruled, not an oversight; nothing new was added to `SIMULATION-RULES.md` because rule 4 already covers it |

The four rules readings, in short: an attack feature printing no damage deals the
adversary's **standard** damage; an interrupting Reaction **doesn't cancel** the
attack it interrupts, and its "moves into Melee range" is read off the attacker's
weapon; a countdown triggers **once**, with every Archer Guard firing at the same
PC and their successes **combined into one damage roll**; and a condition an
adversary applies to a PC lasts **until their next rest** unless the feature says
otherwise, which inside one fight means it never lifts.

**Machinery batch 3 built, all reusable.** `before_attacked` is `on_attacked`'s
earlier twin — same signature, same holder, fired before the roll instead of
after a hit — and deliberately cannot cancel what follows. `on_party_attack_roll`
and `convert_party_roll` are the GM-side mirrors of the party's reroll hooks:
both scan the living adversaries rather than a sheet, one watching a PC's roll
(the countdown) and one rewriting it (Curse). `Condition.disadvantage_on` gives a
condition a way to hobble one trait, answered by `FightState.disadvantaged_on`
and read where a roll knows its trait, and `dice/common.py`'s `combined` folds it
against whatever Advantage the roll already had. Curse's conversion itself needed
nothing new: swapping the two duality dice leaves the total, the success and the
critical exactly as they fell and flips only which die came up higher.

Two consequences worth knowing before reading any numbers. **A Curse conversion
is worth more than a Hope** — the party loses the Hope, the GM gains a Fear, and
the spotlight passes instead of staying — so the Hexer's four Stress are four
stolen turns. And **the Harrier punishes a front line specifically**: its
counterattack is 1d10+2 against its own printed 1d6+2, and a party of archers
never triggers it at all.

### Batch 4

Eleven features, and the **Lackey needed no code at all** — `Minion (3)` and
`Group Attack` were written generically in batch 2, so a whole stat block came
online the moment its entry was typed. That is what the generic-first rule buys.

The rulings were again mostly rules readings, and one of them reopened a
standing decision.

| Feature | Cost | Ruled by |
|---|---|---|
| Hold Them Down (Kneebreaker) | free | rule 4 |
| I've Got 'Em (Kneebreaker) | — | Passive. Doubles what *other* adversaries deal to a creature it has Restrained |
| Tactician (Lieutenant) | 1 Stress | rule 1, and it does **not** cost the Lieutenant its action |
| More Where That Came From (Lieutenant) | free | rule 4, with **no cap** — see below |
| Coup de Grace (Lieutenant) | 1 Fear | rule 4, plus the printed requirement that the target be Vulnerable |
| Backstab (Shadow) | — | Passive, on an attack rolled with Advantage |
| Cloaked (Shadow) | free | rule 4 |
| Sickening Flux (Elemental) | 1 **HP** | A new cost class: spent freely, never the last HP |
| Remake Reality (Elemental) | 1 Fear | rule 4 |
| Magical Reflection (Elemental) | free | Reaction, fires on every triggering hit |

**Restrained is now recorded.** The standing ruling that being Restrained has no
effect of its own is unchanged — but a condition nobody writes down is one
nothing can key on, and `I've Got 'Em` keys on it. So a feature that Restrains
applies the record, tagged with `Condition.source` so "Restrained **by the
Kneebreaker**" can be read strictly, and Bite, Grab and Drag and Detain were
retrofitted to do the same. The movement it stops is still declared as a gap.

**A printed escape roll is modelled.** Where the SRD ends a hold on a Strength
Roll, the held PC attempts it at each announced moment, using the best of
whatever traits the text offers — the Scorpion Poison's shape, generalised into
`_breaks_free`. Where it ends on the holder taking damage, `_release_held` frees
everyone that adversary holds. Neither is a gap any more.

**Machinery batch 4 built.** `damage_multiplier` is the first hook consulted from
*neither* side of an attack — it scans the field, because `I've Got 'Em` belongs
to a third party. `attack_advantage` lets content grant Advantage to its holder's
standard attack, with `combat/policy.py`'s `adversary_attack_advantage` as the
one place both the loop and Backstab read the answer from. `standard_damage` now
receives the attack roll, so content keyed on how the attack came out doesn't
have to work it out again. `on_attacked` now carries the damage dealt, which it
and `on_damaged` previously knew only half of each. `FightState.summon` adds an
adversary mid-fight, and `Adversary.will_spend_hp` prices a feature paid for in
HP.

**Two things to watch when reading numbers.** A Kneebreaker beside anything else
roughly doubles that thing's output against whoever it is holding, so the pair is
worth far more than the two stat blocks read separately — which is the SRD's
intent and the reason a Jagged Knife band is priced the way it is. And Sickening
Flux makes most of a party Vulnerable for the rest of a fight for one HP, which
is the largest single effect in tier 1 so far.

### More Where That Came From is uncapped, deliberately

It costs nothing and can fire on any of the Lieutenant's spotlights, and it is
the only feature in the catalogue that makes the field **bigger**. A cap was
proposed — once per fight, or only below N live Lackeys — and declined: Minions
are defeated by any damage, so a summoned field clears about as fast as it
arrives, and bounding it would have priced the feature below what the page
describes.

The same ruling settled a second question that had been sitting in
`combat/fight.py`: **there is no early-victory end state**, and there will not be
one. Calling a fight over once only Minions are left would be right in a bandit
encounter and wrong in a rat plague, and nothing in the loop can tell those
apart. Fights are played to the end and the extra rounds are counted as what they
are; `MAX_PC_ACTIONS` stays as scaffolding rather than becoming a rule.

### Rule 3's expected-damage margin is gone

It was set at 2 from a sample of two, both sitting on exactly 2.0, and it has
since been struck rather than tuned: **no usage policy may turn on a comparison
of expected damage**, because nothing at a table computes one. That is the
imperfect-information principle - the one that leaves the Faerie's Wings
unmodelled - applied to the GM's side of the screen.

What survives is the visible half: a feature whose point is a condition doesn't
apply one the target already has. Nothing else changed. Venomous Stinger keeps
its check because the Poison is what the sting is for; Grab and Drag never had
one, and still doesn't, because Restrained does nothing here for the check to
protect. Neither behaves differently from before - a knob and its justification
were removed, not a decision.

### Batch 5

Twelve features across five stat blocks, and **the Minor Treant needed no code
at all** — `Minion (5)` and `Group Attack` were both written generically in batch
2, so it came online with its JSON entry exactly as the Lackey did. Four more
features were already modelled: `Relentless (2)` and `Momentum` on both Solos.

| Feature | Cost | Ruled by |
|---|---|---|
| Scorched Earth (Fire Elemental) | 1 Stress | rule 1, with no threshold on how many PCs it reaches |
| Explosion (Fire Elemental) | 1 Fear | rule 4 |
| Consume Kindling (Fire Elemental) | free, 3 per scene | **Ruled**: the flammable scenery is always to hand, so it clears on each spotlight until its uses are gone — HP first, Stress only once the HP track is clean. See `SIMULATION-RULES.md` §1 |
| All Must Fall (Demon) | free | Passive. No choice to make; it fires on any PC failure with Fear inside the band |
| Hellfire (Demon) | 1 Fear | rule 4 |
| Reaper (Demon) | 1 Stress | rule 2, plus the new general qualifier: **a Reaction whose benefit computes to zero is not taken**, so an unhurt Demon banks its Stress |
| Slow (Green Ooze) | — | Passive. Nothing about it is a choice |
| Acidic Form (both Oozes) | — | Passive |
| Envelop (Green Ooze) | free | rule 4. Rule 3 deliberately doesn't reach it — the attack deals full damage and 2 Stress whether or not the hold is already on |
| Split (Green Ooze) | 1 Fear | rule 4 |

**Three rules readings**, all in `SIMULATION-RULES.md`:

- ~~**Only PCs make Reaction Rolls.**~~ **Reversed after batch 6** — the user
  corrected it. Adversaries do make them, on a flat d20, so "all creatures"
  reaches the acting adversary's own side and they roll to save like anybody
  else. Scorched Earth therefore catches allies; see the batch 6 section.
- **A success can buy half rather than everything.** Scorched Earth and Hellfire
  are the first saves worth something short of a clean escape, so "success" and
  "critical" come apart — half rounds down, a critical still takes nothing.
- **Split removes the Ooze without defeating it.** `FightState.remove` is the
  mirror of `summon`; marking its HP would have told the reader the party had
  won something at the moment they are worse off.

**Machinery batch 5 built.** `skip_spotlight` / `skips_spotlight` is the first
hook that can spend an activation on nothing — an `action` declining just lets
the next option try, and the standard attack never declines, so nothing could
previously say "this spotlight resolves into nothing at all". `FightState.remove`
is the other half of `summon`. Two module-local helpers in
`features/adversaries.py` carry clauses the SRD prints verbatim on several stat
blocks: `_burn_an_armor_slot` (Spit Acid and Acidic Form) and `_flames`
(Scorched Earth and Hellfire).

**Two things to watch when reading numbers.** The Fire Elemental is effectively a
**12 HP Solo** once Consume Kindling is counted, on top of a Far standard attack
the area rule rarely holds back. And the Green Ooze's Slow cuts its output in
half — it acts every other spotlight, and the wasted activation still costs the
GM whatever the turn charged — which is what pays for Envelop, Acidic Form and
Split all sitting on one 5 HP stat block.

### Batch 6

Ten features across five stat blocks, and **Pirate Raiders needed no code of its
own**: `Horde (1d4+1)` was generic from batch 2 and `Swashbuckler` is shared by
all three pirates, so it registers once and reaches whichever was hit.

| Feature | Cost | Ruled by |
|---|---|---|
| Creeping Fire (Red Ooze) | — | **Ruled**: no combat effect. Movement and terrain, with no mechanical benefit attached that could be modelled in the trigger's place — unlike Consume Kindling |
| Ignite (Red Ooze) | free | rule 4, gated by **rule 3**: the point of the attack is the burn, so it isn't used on a target already Ignited |
| Split (Red Ooze) | 1 Fear | rule 4, as the Green Ooze's |
| Burning (Tiny Red Ooze) | — | Passive |
| Swashbuckler (all three pirates) | — | Passive |
| Reinforcements (Captain) | 1 Stress, once per scene | rule 1 |
| No Quarter (Captain) | 1 Fear | rule 4, plus the printed requirement of three Pirates in Melee |
| Clear the Decks (Tough) | 1 Stress on a hit | rule 1 |

**Three rules readings, one of them a reversal:**

- **Adversaries DO make Reaction Rolls**, on a **flat d20 with no modifier** —
  they have no traits to add. This corrects the batch 5 ruling, which had them
  making none at all. The consequence is that "all creatures" features reach the
  acting adversary's own side, and those allies get a real save.

  **Read the printed noun, because the SRD alternates it.** "All *creatures*"
  includes allies; "all *targets*" is the party only. *Scorched Earth* and *Earth
  Eruption* say creatures and now catch allies; *Hellfire*, two stat blocks after
  Scorched Earth, says targets and does not. All three in the same two batches,
  which is what makes the distinction hard to put down to loose wording.
- **"The Captain marks 2 or fewer HP" is the Captain marking it**, not the
  Captain making a PC mark it. That is Daggerheart's design language throughout,
  and reading it the other way would turn a defensive quirk into a second attack.
  It also settles the lower bound: adversaries have no Armor Slots, so a landed
  hit always marks 1 or 2 and the zero case cannot arise on the GM's side.
- **"Pirates" is a kind, not a stat block.** No Quarter counts any living
  adversary with "Pirate" in its name, matched canonically — the one feature that
  matches on part of a name, where On My Signal names "Archer Guard" in full. How
  many are *in range* goes through the area rule exactly as Pack Tactics does.

**Machinery batch 6 built.** `on_attacked` gained `hp_marked` alongside the
`damage` it already carried — Swashbuckler needs the attacker (for the Melee
check) *and* what the hit cost, and each of the two damage hooks knew only half
of that. The same shape as the `damage` addition in batch 4. `Split` became
**parameterised** (`Split (Tiny Green Ooze)`, `Split (Tiny Red Ooze)`): one rule
whose argument differs per stat block, so it follows `Flying (X)` in
parameterising a name the book prints bare, and the Green Ooze's batch-5 entry
was updated with it.

**Worth knowing before reading numbers.** **No Quarter cannot fire below six
pirates.** The Melee band reaches at most 3, and only on a field of
`MANY_ADVERSARIES` or more with the clustered roll — so the Captain's signature
move is dead in any small crew. That follows from the printed 3 meeting the area
rule; dropping it to 2 was offered and declined. And **a melee party pays a
Stress for nearly every swing at this crew**: focus fire aims at the most wounded
adversary, and a Raiders Horde on 4 HP with 5/11 thresholds marks 1 HP off most
tier 1 hits, which is exactly Swashbuckler's window.

### Damage types, and what closed with them

Not a batch — a retrofit, and the last piece of batch 4. `content/damage_types.py`
carries the SRD's two types plus what resistance and immunity do to a hit;
`damage_resistance` / `resistance_to` is one hook for both, keyed by type, since
they differ only in how much of the hit survives.

Three rules readings came out of it, all in `SIMULATION-RULES.md` §2: halving
lands **before** thresholds (so a resistance changes the HP marked, not just the
number), several resistances fold by taking the **strongest single** one, and
**untyped damage matches nothing** — it is never resisted and satisfies no type
restriction, so a missing type can only ever fail to apply an effect.

Two declared gaps closed and a third was found and closed with them: **Weak
Structure** (Construct), **Unstoppable** (Guardian) and **Iron Will** (Stalwart)
are all physical-only on the page and now enforce it. That needed `damage_type`
added to the `severity_response` and `severity_increase` signatures — chosen over
passing a `Hit` record or filtering inside dispatch, on the grounds that the type
is a fact about the hit exactly as `amount` and `hp_to_mark` are.

**Every feature that rolls damage now states a type**, and where the page states
none the ruling is that it takes the adversary's own standard-attack type
(`Adversary.type_of_damage`). Death Quake was the case worth catching: magic out
of a physical Construct, which the fallback alone would have got wrong.

## Still open

- **Three PC cards still charge condition Fear the old way.** Slumber, Vicious
  Entangle and Tava's Armor spend the GM's Fear at the moment they apply a
  condition, rather than going through `Condition` and `when_the_gm_pays`. The
  same rule is expressed twice until they migrate.
- **Area attacks can't be force-rerolled.** `Not This Time` re-makes "an attack
  roll", and one already measured against five different Evasions can't be
  re-made without unwinding all of them. Declared as a gap on the card.
