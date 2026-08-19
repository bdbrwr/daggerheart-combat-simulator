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
| The GM gets at most **party size + 1** activations per turn | `combat/state.py` → `max_activations_per_gm_turn` | The SRD lets the GM spend Fear to spotlight **as many as they can afford**. Ours is a cap that a greedy simulator needs; a knob worth sweeping. Activations, not adversaries: `Relentless (X)` lets one adversary take several and they all count against the cap. |
| **`Relentless (X)` spends from the same activation budget as everyone else.** Its extra spotlights count against party size + 1, and each still costs the usual 1 Fear — no discount, no surcharge | `features/adversaries.py` → `relentless`; `combat/fight.py` → `_take_gm_turn` | The SRD puts **no cap** on activations at all: the GM spotlights as many adversaries as they can afford, and Relentless only says "spend Fear as usual". The cap is entirely ours, and so is the decision to make Relentless live inside it. The point of the cap is to hold a simulated fight to something a GM would actually run at a table, and a feature that could reach around it would defeat that. Consequence worth knowing: against a *small* field the feature now converts activations that previously went unused, so the GM spends more Fear than the same encounter used to — the Fear rule didn't change, the number of things worth spending it on did |
| Everyone who can act goes before anyone goes again, and ties are broken **at random** | `combat/fight.py` → `_next_adversary` | Nothing; the GM chooses. Previously the first-listed living adversary went every time, which let the order an encounter spawned its adversaries in decide who acted - the same thing `_next_pc` already avoids on the party side. It matters more now that `Relentless` exists: taken greedily, a Relentless adversary would swallow the whole GM turn before anything else moved, where at a table the extra activation reads as the dangerous thing coming back round. |
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
| An adversary's spotlight is **one action feature or the standard attack**, chosen at random among those willing | `combat/policy.py` → `take_adversary_turn` | The SRD calls these Actions and says they're what an adversary does when the spotlight is on them, but nothing says which to pick. Same random-among-viable stand-in the party already uses, and for the same reason: the order a stat block lists its features in carries no meaning. |
| **An adversary spends Stress on an Action only once hurt**: with X Stress slots still free, when `hp_unmarked <= X**2 + 1` | `adversaries/adversary.py` → `will_spend_stress` | Nothing; spending an adversary's Stress is the GM's choice every time. See "Adversary desperation" below for the whole rule. |
| **A Reaction costing Stress fires on every trigger it can pay for** — the desperation rule above deliberately does not apply | `adversaries/adversary.py` → `can_spend_stress`, called directly by reaction features | Nothing. A reaction has a moment rather than a choice of moment; gating it on how hurt the adversary is would mean throwing the trigger away instead of picking a better time. |
| **An attack feature that is worse than the standard attack by ≥ `2` expected damage and exists mainly to apply a condition is used only against a target that doesn't already have that condition** | `features/adversaries.py` → `CONDITION_ATTACK_EV_MARGIN` | Nothing. The margin is a knob and is deliberately a single named number rather than a per-feature threshold. It is set from two examples only (Venomous Stinger and Grab and Drag, both at exactly 2.0), which is thin — see the open validation note below. |
| **Anything with no policy of its own is chosen at random among the options whose costs can be paid** | `combat/policy.py` → `take_adversary_turn`; `content/registry.py` → `action_options` | Nothing. The same rule the party already plays by, and the standing default rather than a per-feature placeholder: a feature is a candidate when it can be afforded and reaches somebody, and the shuffle picks among the candidates. |
| **A Minion Group Attack is used when it reaches 2 or more Minions of that stat block** | `features/adversaries.py` → `GROUP_ATTACK_WORTH_IT` | Nothing; spending the Fear is the GM's choice. Below the threshold the feature buys nothing - it is one shared roll for the combined damage of everyone swept, so at one Minion it *is* that Minion's standard attack, bought with a Fear. Written for Minions in general rather than for the Giant Rat, since the shape recurs across the SRD's Minions. |
| **Spitter is bought at the first spotlight the Fear allows**, and its extra activation is granted **once**, on that turn | `features/adversaries.py` → `spitter` | Nothing. The die keeps rolling every spotlight for the rest of the fight, so it is worth strictly more the earlier it lands and there is no reason to hold it. The one-off grant is the Overload shape (`grant_activation`) rather than the Relentless one: the Fear buys the die *and* one extra activation that turn, and every turn afterwards the die rolls and buys nothing. |
| **`Flying (X)` is authored as the *average* uplift**, not checked per round | `features/adversaries.py` → `flying`; `adversaries/adversary.py` → `spawn` | The SRD qualifies it - "*while* flying" - and nothing tracks whether an adversary is currently airborne. Rather than invent a per-round check, the qualifier moves to the author: a creature in the air the whole fight is written `Flying (2)`, one up half the time `Flying (1)`. Over a high-N run those land in the same place, and the knob is in the JSON per adversary. |
| **An adversary spends its own HP on a feature freely, but never its last** | `adversaries/adversary.py` → `will_spend_hp`; `features/adversaries.py` → `sickening_flux` | Nothing; spending an adversary's HP is the GM's choice. Ruled as "the same reading as Stress, never the last one" — and worth knowing that the first half is vacuous: the desperation test asks whether `hp_unmarked` has fallen to `X**2 + 1` with X the slots left after paying, which when the pool *is* the HP track reduces to `hp_unmarked <= hp_unmarked**2 + 1` and is true of everything alive. So the guard is the rule: such a feature is used from full health and stops one HP short of suicide. |
| **`I've Got 'Em` doubles damage before the target's thresholds**, not after | `features/adversaries.py` → `ive_got_em`; `adversaries/adversary.py` → `_dealt`; `content/registry.py` → `damage_multiplier` | The SRD says the creature "takes double damage". Doubling the rolled total is the reading; doubling the HP marked would be a far larger effect, since damage becomes HP through bands. Applied per target, so a sweep doubles only against whoever is actually held. |
| **Adaptability** is used only while 4 or fewer Stress are marked | `features/ancestries.py` → `ADAPTABILITY_MAX_STRESS_MARKED` | The card sets no limit. Marking the last Stress makes a PC Vulnerable for the rest of the fight, which costs far more than one rerolled attack is worth, so the last slots are held back. |

### Adversary desperation — when Stress gets spent

An adversary's Stress is a small, fixed pool, and nothing in the SRD says when
the GM should spend it. A simulator left alone spends it immediately, which turns
every stat block's Stress into an opening flourish and makes a fight front-heavy
in a way a table never is.

The rule instead ties spending to how close the adversary is to going down. With
**X** Stress slots still free, an **Action** costing Stress is available when

```
hp_unmarked <= X ** 2 + 1
```

| Slots still free | Spends at |
|---|---|
| 3 | 10 or fewer unmarked HP |
| 2 | 5 or fewer |
| 1 | 2 or fewer |

The last slot opens at 2 unmarked HP, which is `NEAR_DEATH_HP_UNMARKED` — the
same line the party plays to — and that alignment is where the `+ 1` comes from.
A cost of more than one slot is measured at the *last* slot it would mark, since
that is the one that has to be affordable.

The shape it produces: most ported tier 1 adversaries have three Stress against
9 HP or fewer, so their first Stress Action is on the table from the opening
spotlight and the rest arrive as the party wears them down. The **Bear** is the
outlier and the clearest illustration — 7 HP against only two Stress, so it
cannot Bite until it is at 5 unmarked HP, and a healthy Bear is a plain 1d8+3
attacker.

**Reactions are exempt.** A reaction has one moment, not a choice of moments, so
gating it on the adversary's HP would discard the trigger rather than time it
better. They call `can_spend_stress` directly and fire whenever the trigger
happens and the slot exists. The largest consequence is the Construct's
**Overload**: all four of its Stress ride its first four landed attacks, from
full health.

Both halves are knobs. The exponent, the `+ 1`, and the action/reaction split are
each worth sweeping.

### Area of effect, standing in for range

No positioning is modelled, so an ability that hits "all targets within X range"
would otherwise hit everything, every time — which is far more generous than a
table, where the GM places adversaries and the spread of a fight is what makes an
AOE good or wasted. Instead, **the range band caps how many adversaries an AOE
can reach**:

**The reach is rolled, not fixed.** Each band has a base reach from the field
size and then a *spread roll* that can cut it, because a table's spread isn't
fixed either — the same four adversaries are sometimes bunched and sometimes
strung out, and a band that always delivered its best case would price every
area ability off its best case. Two calls with the same field can differ, on
purpose; a seeded run is still reproducible.

As a formula over `n` living adversaries, with the result floored at 1 and
capped at `n`:

| Band | Base | Spread roll |
|---|---|---|
| Far | `n` | one short, **1 in 4** |
| Close | `min(n * 3 // 4, n - 1)` | held to `CLOSE_CAP` (3), **1 in 2** |
| Very Close | `n // 3` | held to `VERY_CLOSE_CAP` (2) unless **1 in 10** |
| Melee | 3 at `n >= MANY_ADVERSARIES`, else 2 | one fewer, **1 in 2** |

So against four adversaries: Far reaches 4 or 3, Close reaches 3, Very Close
reaches 1, and Melee reaches 2 or 1.

Two of these were tightened deliberately, because the bands they governed were
too strong. **Far** used to mean "the whole field, always", which made every Far
ability worth its ceiling on every cast. **Melee** used to be a flat 2 below
`MANY_ADVERSARIES` and is now 1 or 2, so a Melee sweep is no longer reliably
better than a single-target attack on a small field.

Every number here is a knob — the caps, the one-in-N divisors and
`MANY_ADVERSARIES` alike. They are the whole of how much an area ability is
worth in this simulator, so they are the first thing to sweep when an area-heavy
party looks mispriced.

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
put a number on that. At Close that's a 3-in-4 chance the ally is reachable.

> **These three shares are now out of step with the counts above, and that is
> flagged rather than fixed.** The spread rolls cut every band's expected reach,
> but `_BAND_SHARE` still reads Far 1.0, Close 3/4, Very Close 1/3. Re-deriving
> them would make Far n-dependent (`1 - 0.25/n`) instead of certain and would
> change how often Luckbender can rescue an ally, which is a balance decision
> rather than a tidy-up — so it is left for a ruling. Melee is the exception and
> was fixed: its count is rolled, so `chance_within` uses the *expectation*
> (the higher count less a half) rather than asking the roller, which would have
> returned one sample of a random variable and called it a likelihood.

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

### Temporary conditions

A condition is a record on the `FightState` carrying its name and a predicate
saying when it ends — `content/conditions.py` → `Condition`. The loop announces
two moments and each condition decides whether that's its cue: a combatant taking
the spotlight (`WHEN_THEY_ACT`), and the GM's turn coming round (`ON_A_GM_TURN`).

**Vulnerable** hands every roll against its holder Advantage, which is a large
and fully represented effect, so content that applies it has something to apply.
`FightState.is_vulnerable` answers for both sources at once — a PC with every
Stress marked, and anyone the condition was put on.

**A condition can also hobble one trait**, through `Condition.disadvantage_on`
and `FightState.disadvantaged_on`. The SRD writes several of these without giving
them a keyword — the Archer Guard's Hobbling Shot leaves its target "with
disadvantage on Agility Rolls until they clear at least 1 HP" — so the field
carries the traits and whoever applies one names the condition whatever the page
calls it. It reaches a PC's weapon attack (`items/weapons.py` → `attack_with`,
which knows the weapon's trait) and their Reaction Rolls
(`features/adversaries.py` → `_reaction_roll`). Content that rolls an attack of
its own doesn't consult it, which is declared as a gap where Hobbling Shot is
registered. Where a PC would have Advantage as well, the two cancel, per the SRD
— `dice/common.py` → `combined`.

**A condition an adversary applies to a PC lasts until their next rest** unless
the feature says otherwise, which inside one fight means it never lifts (an `end`
of `None`). The SRD clears a *temporary* condition when its holder "makes a move
against it" — for a PC, spending their spotlight on a successful action roll —
and nothing here models a PC spending a turn that way. Note this is the mirror
of the GM-side default below rather than the same rule: a condition the *party*
puts on an adversary ends when the GM pays a Fear.

**Poison is modelled, and it is a family rather than one condition.** Several of
the SRD's poisons share the name while differing in both what they do and how
they end, so `POISONED` is the shared name and each source supplies its own `end`
and `effect`. The Giant Scorpion's is the first: shaken off on a Knowledge
Reaction Roll at 16, and costing its holder a Stress on a d6 of 4 or lower before
each action roll. That second half is the first real use of `Condition.effect`
and of `BEFORE_AN_ACTION_ROLL`, announced from `combat/policy.py` →
`_make_the_roll`.

**Restrained is recorded, and still does nothing by itself.** It stops a
combatant moving and no movement is modelled, so the condition has no effect of
its own — that ruling is unchanged. What *is* new is that a feature applying one
now writes it down, with `Condition.source` naming who applied it, because other
content asks: the Jagged Knife Kneebreaker's `I've Got 'Em` doubles the damage
its allies deal to creatures **it** has Restrained, and a condition nobody
recorded is one nothing can key on. Bite, Grab and Drag, Detain and Hold Them
Down all record theirs. What stays declared as a gap is the movement.

**A printed way out of a hold is modelled, not skipped.** Where the SRD ends a
condition on a roll ("until they break free with a successful Strength Roll"),
the held PC attempts it as a Reaction Roll at each announced moment —
`features/adversaries.py` → `_breaks_free` — using the **best** of the traits the
text offers, since the player would choose. Where it ends on the holder being
hurt ("until the Defender takes Severe damage"), an `on_damaged` hook frees
everyone that adversary is holding — `_release_held`. What is not modelled is the
*cost* of trying: the attempt rides on the announced moments rather than
spending the PC's spotlight.

The rest — Hidden, On Fire, Stunned — have no representation and nothing applies
one.

**The GM pays to shake a condition off**, which is `when_the_gm_pays`: a
condition the party put on an adversary ends when the GM spends 1 Fear on their
next turn. Several are written to end exactly this way (Slumber says so
outright), so draining the pool is close to what the condition costs the GM side,
and it lands in a currency already tracked carefully. A GM who can't afford it
doesn't clear it — which is the honest consequence, and better than the earlier
version of this rule, which charged the Fear the moment the condition landed and
so made conditions free whenever the pool was empty.

> **Known duplication.** The three PC-side cards that apply conditions
> (Slumber, Vicious Entangle, Tava's Armor) still charge that Fear at
> application time from their own code, rather than going through `Condition`.
> They should migrate to it; until they do, the same rule is expressed twice.

### Reaction Rolls

Duality Dice plus a trait, and nothing else: the **Hope/Fear outcome is not
read**. Nobody gains a Hope, the GM gains no Fear, and the spotlight doesn't
move — a Reaction Roll is not an action roll, and only an action roll does any of
that. Features call `roll_duality` directly and read `is_success` and
`is_critical`.

**A critical ignores the whole effect**, not only the part a success avoids.
Where a failure is "15 damage and Vulnerable" and a success is "5 damage", a
critical is nothing at all.

| Policy | Where | What the rules say |
|---|---|---|
| Where the SRD prints **no Difficulty** for a Reaction Roll, the adversary's own Difficulty is used | `features/adversaries.py` → `_reaction_roll` | The GM sets it. The stat block's Difficulty is the number already on the page and it scales with tier, which makes it the least invented option — but it is invented, and it's a knob. |
| A Reaction Roll gets the **trait only** — no Experience, no Help, no Advantage. A condition that hobbles the trait *is* honoured, and rolls it at Disadvantage | `features/adversaries.py` → `_reaction_roll` | The SRD would let a PC spend Hope on a relevant Experience here as on any roll. Not modelled. The hobble is the one thing that reaches these rolls, because "disadvantage on Agility Rolls" plainly covers the Agility Reaction Roll a PC makes to keep their feet. |

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
| An adversary's **area attack** is one roll checked against each target's Evasion, with one damage roll applied to everyone it beat | `adversaries/adversary.py` → `area_attack`; `content/aoe.py` → `targets_hit` | The mirror of the reading already used for a PC rolling against an area, and of `Hold Them Off` reusing one roll against several. The roll's own success is measured against the *lowest* Evasion present, for the same reason the PC side measures against the lowest Difficulty: it either beat somebody or it beat nobody. |
| A feature keyed on "takes **Severe damage**" reads the number rolled; one keyed on "marks **2 or more HP**" reads what the hit cost | `features/adversaries.py` → `acid_bath`, `rampaging_fury`; `content/registry.py` → `on_damaged` | The SRD writes both kinds and means different things by them, so `on_damaged` is handed both figures and each feature reads the one its own text names. |
| Content that **worsens** a hit is asked after content that softens it, and **Weak Structure** fires only on a hit that actually marked HP | `content/registry.py` → `harden_damage`, `severity_increase`; `features/adversaries.py` → `weak_structure` | "When the Construct marks HP … they must mark an additional HP" doesn't say whether that's the HP the damage started at or the HP it ended at. Reading it as the final amount means a hit an Armor Slot or a domain card absorbed entirely marked nothing, so there is nothing to add to - which is what the trigger says on its face. Fixing the order in the dispatch rather than in each feature keeps the answer the same however many features register |
| **Pack Tactics** asks the **area rule** whether the pack converged: of the wolves alive, `targets_reached(MELEE, ...)` says how many are on this target, and the feature needs 2 - the attacker and one more | `features/adversaries.py` → `pack_tactics`, `PACK_TACTICS_WOLVES` | "Another Dire Wolf within Melee range of the target" is positioning, and none is tracked. Reading it as "is another wolf alive anywhere?" would fire on every standard attack for as long as any packmate stood, which is far more than the page promises - so the Melee band answers instead. Since that band is rolled, a pair converges about half the time and a pack of six always does, and how often the band lets it through is the whole of what holds the feature back. |
| **Armor-Shredding Shards** reads "within Melee range" off the **attacker's weapon**: everyone is assumed to have attacked from the greatest range their weapon allows, so a Melee-only weapon triggers it and anything reaching further does not | `features/adversaries.py` → `armor_shredding_shards`; `items/weapons.py` → `attack_with` | No positions are tracked, so the trigger needs some handle on distance and the weapon is the only one there is. It makes the feature a tax on the front line and free for archers, which is the shape it has at a table - and it means a party's answer to the Glass Snake is a weapon choice. Only weapon attacks reach it; content that rolls an attack of its own has no weapon and no range, declared as a gap |
| A **Minion Group Attack** is **one activation** however many Minions it sweeps, but each Minion swept has its own spotlight consumed and doesn't act again that GM turn | `features/adversaries.py` → `group_attack`; `combat/state.py` → `consume_activation`; `combat/fight.py` → `_next_adversary` | "Spend a Fear to choose a target and spotlight all Giant Rats within Close range" - the SRD spotlights several combatants with one feature, which nothing in the loop had a shape for. Charging one activation follows from it being one shared attack roll; consuming the rest follows from them having been spotlighted. Reading it the other way (one activation each) would let a swarm act, then act again, and would empty the GM turn's budget into a single feature |
| An adversary feature that makes an attack deals **whatever damage it states, and otherwise the adversary's standard damage** | `features/adversaries.py` → `detain`; `adversaries/adversary.py` → `_damage_for` | The SRD prints all three cases and only two of them explicitly: dice of its own (Bite at 3d4+10), no damage at all (the Kneebreaker's Hold Them Down, which says "the target takes no damage"), and silence. Silence is read as the standard attack, and the corroboration is that Hold Them Down has to say otherwise — a clause only worth printing if damage is the default. Passing no dice keeps it true mechanically too, since `dice is None` is already the discriminator for "the printed attack", so a standard-damage swap reaches such a feature. |
| An **interrupting Reaction does not cancel the attack it interrupts** | `content/registry.py` → `before_attacked`; `features/adversaries.py` → `fall_back` | The Harrier's Fall Back fires "before the attack roll" and moves the Harrier out of Melee, which could be read as making the attack impossible. Nothing in the SRD says it is cancelled, and a PC can move within Close range as part of their own action, so one whose target backed off would simply follow. So the hook can't veto: what the Reaction buys is the counterattack it comes with. Reading it the other way would turn the Harrier's three Stress into three negated melee attacks and make the stat block far stronger. |
| **"Moves into Melee range to make an attack" is read off the attacker's weapon** | `features/adversaries.py` → `fall_back` | The same handle on distance Armor-Shredding Shards already uses, and the only one there is: a Melee weapon triggers it, anything reaching further does not. |
| **On My Signal** triggers **once**, every Archer Guard fires at the **same** PC, and their successes are **combined into one damage roll** | `features/adversaries.py` → `on_my_signal_ticks` | The SRD only re-arms a countdown that says it loops, and this one doesn't. "The nearest target within their range" is positioning; the standing targeting rule stands in for it, asked once on the Head Guard's behalf, which is also what leaves "if any attacks succeed on the same target, combine their damage" with anything to do. Combining is not a rounding detail: three separate hits of 7 mark 3 HP, while one combined 21 is Severe. |
| **Tactician does not cost the Lieutenant its action** | `features/adversaries.py` → `tactician` | The SRD files it as an Action, but the text triggers "when you spotlight the Lieutenant… to **also** spotlight two allies". Ruled as a rider on being spotlighted, so it registers on `on_spotlight` and the Lieutenant still attacks afterwards. Reading it the other way would make it one option among several and roughly halve how often a Jagged Knife band gets its extra activations. |
| **Magical Reflection** reads "within Close range" off the attacker's weapon, and halves the damage **rolled**, rounding down | `features/adversaries.py` → `magical_reflection` | The same handle on distance Armor-Shredding Shards uses, so Melee, Very Close and Close weapons trigger it and Far ones don't. "The damage they dealt" is read as the number rolled rather than the HP it cost, so a hit the Elemental shrugged off still rebounds at full size. |
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
- **Damage-type resistance and immunity** — nowhere, and now blocking a ported feature (see the damage-types entry below)
- **Range and positioning entirely.** Every range band ("Melee", "Very Close", "Far") is treated as always satisfied. This is why `I Am Your Shield` never checks distance, and why adversary features keyed to position are skipped.
- **All conditions except Vulnerable and the trait hobble** — see the conditions section above. Restrained is *ruled* to have no combat effect here rather than merely absent; Hidden, On Fire and Stunned have no representation and nothing applies them. *Cursed* (the Jagged Knife Hexer's) is a named condition whose whole effect is its own feature's, so it needs nothing from this list.
- **Direct damage bypasses the Armor Slot only.** `characters/player_character.py` → `take_damage(direct=True)`; `content/registry.py` → `direct_damage`, `deals_direct_damage`. Thresholds still decide how many HP it costs, and damage responses still get their say — the SRD's restriction is on armor. Against this party it's worth close to a whole HP per hit, since the policy otherwise marks a free slot against everything
- **Adversary Fear features** — no adversary has one implemented yet. Note this is distinct from features that merely *cost* the GM Fear, several of which are modelled (Ramp Up charges to spotlight, Grab and Drag spends on a hit)
- **Adversary Experiences — ruled out, not outstanding.** The SRD gives adversaries optional Experiences the GM can spend a Fear on, "to raise their attack roll or increase the Difficulty of a roll made against them". The user has decided not to model them, and the reason is the Fear economy rather than the effort: this simulator already commits a great deal of Fear to extra activations, and an Experience competes for that same Fear while buying a comparatively minor bonus on a single roll. A GM in this simulator would essentially never take that trade, so implementing it would add a branch that never fires. They stay recorded in each catalogue entry's `notes` so an entry remains checkable against the printed page, and there is deliberately no field and no mechanic. This is a decision, so it does not belong on anyone's list of work to do
- **Adversary `type` is data only.** The SRD gives a type no rules of its own — "an adversary's type represents the role they play in a conflict", then one descriptive line each. Everything mechanical that sounds like a type is printed as a named *feature* (`Minion (X)`, `Horde (X)`, `Relentless (X)`, `Slow`, `Arcane Form`, `Armored Carapace` are all SRD example passives), so the fight loop never reads `Adversary.type`. It is carried because it's on the printed page and because it's what "Social adversaries aren't ported" keys on — see `adversaries/PORTED.md`
- **Adversary passive features** — named in `adversaries/srd.json` rather than sitting in a code comment, so they reach the coverage block. All three Jagged Knife passives are assessed in `features/adversaries.py`: *Climber* has no combat effect, and *From Above* (+1 expected damage) and *Unseen Strike* (+2) are declared **insignificant**, because damage reaches HP through threshold bands and a bump that size lands within a band far more often than across one. Neither is left *unimplemented* — that state is for work nobody has done, not for a decision
- **Most of the SRD armor table.** Only what the current sheets equip is catalogued in `items/srd.json`. Fortified, Resilient, Shifting, Impenetrable, Painful, Hopeful, Burning and the rest are real mechanics with nothing behind them yet — an armor naming one reports as unimplemented the moment it's equipped
- **Armor Score and armor thresholds are never read from the catalogue.** A sheet carries them already resolved (see the standing rule on sheet-resolved values), so `items/*.json` records them as provenance only. The consequence is that a sheet whose numbers don't match the armor it names will not be caught
- **Subclass features above the foundation tier.** Specialization (level 5) and mastery (level 8) features are declared as gaps on each subclass rather than implemented, since the current party has neither tier
- **Nothing ever attacks the Beastbound companion**, so its Stress, and dropping out of the scene when its last Stress is marked, don't exist here. It contributes damage and carries no risk
- **Damage types are authored but never read.** Every weapon in `items/*.json` carries a `damage_type`, and every adversary stat block prints the type of its standard attack — so the data is there and this is a gap in the *code*, not an absence in the model. Nothing consults it yet, which is why Unstoppable's physical-only reduction applies to every hit and Weak Structure worsens magic damage it shouldn't. **Resistance and immunity are the same gap** and are real outstanding work: the Minor Chaos Elemental's `Arcane Form` ("resistant to magic damage") is therefore left *unimplemented* rather than dismissed, because a dismissal would claim the effect has nothing here to touch and that is not true
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
- **A printed threshold of `None` is stored as 9999** — `adversaries/catalogue.py` → `NO_THRESHOLD`. Some stat blocks print no thresholds at all (Minions, and small things like the Tiny Green Ooze on 2 HP), and every case so far is an adversary with fewer HP than the threshold could ever become relevant for. A threshold out of reach says exactly that: every hit lands in the lowest band. Zero would be catastrophically wrong — it would put every hit at or above Severe and mark 3 HP off a 1 HP track
- **An adversary's standard-attack range is a required field** — `adversaries/adversary.py` → `range`, `attack_band`; `adversaries/catalogue.py` → `parse_range`. No positioning is tracked, so it never decides whether an ordinary attack connects, and it looks like provenance. It isn't: a feature that turns the standard attack into an area one sweeps *this* band, so the number decides how many combatants such a feature reaches. Before it was a field, content had to name a band itself — the Cave Ogre's Very Close was written into `Ramp Up`, which would have swept the wrong band on a Melee adversary and meant every future feature of that shape carrying its own hand-entered copy of a number already printed on the page. `Ramp Up` and `Trample` now read `attack_band`; features that name their *own* band on the page (Hail of Boulders at Far, Spinning Serpent at Very Close) still state it, because that band is theirs and not the adversary's
- **A feature's name may carry a parameter** — `content/names.py` → `base_name`, `parameter`; `content/registry.py` → `_registered`, `feature_parameter`. The SRD prints `Relentless (3)`, `Minion (3)`, `Horde (1d4+1)`: one feature with an argument, not several features. Content registers under the base name and reads its own X off the holder, so no hook signature grows a parameter that almost nothing uses
