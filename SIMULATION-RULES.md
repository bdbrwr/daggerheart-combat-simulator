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
| **A PC marks Stress freely, except their last slot, which is held until they are at 2 or fewer unmarked HP** | `characters/player_character.py` → `will_spend_stress`; consulted by `domain_cards/blade.py` → `get_back_up`, `reckless` and `domain_cards/sage.py` → `tekaira_armored_beetles` | Nothing; every Stress cost in the SRD is a player's choice. Ruled as one general rule for all PC content rather than a threshold per card, and it **replaced two earlier per-card policies**: Get Back Up used to pay whenever the hit would drop the PC, and the beetles used to refuse the last slot outright. Both now answer here. The last slot is held because marking it makes the PC Vulnerable *and* shuts off every other card costing a Stress, which outlives what any single use buys — and released at the same line the near-death rate is reported at, which is also where an adversary's last slot opens. See "PC Stress — when a player marks it" below. |
| **I Am Your Shield**: step in only when the ally is closer to going down than the shielder, and never on the shielder's last HP | `domain_cards/valor.py` → `_worth_shielding` | Using the card is a choice. |
| A PC picks **at random among the options they can actually use** - every ability whose resources they can pay, plus their weapon attack | `content/registry.py` → `action_options`, `use_free_abilities`; `combat/policy.py` → `_make_the_roll` | Nothing; a player weighs their options. Random-among-viable is the stand-in until there's something better. **No automated scoring** - deliberately not built. |
| A **no-rest encounter** assumes *every* per-rest ability was already spent | `combat/rest.py` → `Rest.NONE` | Nothing carries between encounters yet, so the simulator can't know which were actually used. Conservative, and makes a no-rest fight harder than it may really be. |
| **Slumber** is only cast when the GM holds 3+ Fear; **Arcane Barrage** spends Hope down to a floor of 2; **Tava's Armor** waits until somebody has run out of Armor Slots | `domain_cards/codex.py` | All three are player choices the rules leave open. Each is a knob. |
| **Strange Patterns**: the number the Wizard watches for is drawn at random at the start of each fight rather than written on the sheet, and the trigger clears a Stress when any is marked, otherwise gains a Hope | `features/classes.py` → `_watched_number`, `strange_patterns` | Choosing the number is the player's, and every number is as good as every other. Which reward to take is also theirs; Stress is the scarcer resource here, since running out of it hands every adversary Advantage. |
| **Hold Them Off** spends its 3 Hope only when there are two other adversaries *and* the roll would beat at least one of them | `features/classes.py` → `_hold_them_off` | Using the feature is a choice. Spending 3 Hope on a roll that beats nobody is the one outcome a player at the table would avoid. |
| **Vicious Entangle** never declines, and spends the Hope for a second Restrain only when there's another adversary *and* the GM holds at least 1 Fear | `domain_cards/sage.py` → `_entangle_a_second` | Using the card is a choice. At 0 Fear a temporary condition costs the GM nothing (see below), so the Hope would buy nothing. |
| **Tekaira Armored Beetles** are conjured whenever they aren't already up and the shared Stress rule allows it; the Hope to keep them up after a hit is spent only above 3 Hope | `domain_cards/sage.py` → `tekaira_armored_beetles`, `BEETLES_HOPE_FLOOR` | Both are player choices. The Stress half is no longer this card's own policy - it now asks `will_spend_stress` like everything else, which releases the last slot at 2 or fewer unmarked HP where this card used to refuse it outright. |
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
| **A feature whose point is applying a condition is not used against a target that already has that condition** | `features/adversaries.py` → `venomous_stinger`, `curse` | Nothing. Re-applying buys nothing, and who is already Poisoned or Cursed is visible at a table. Which features these *are* is a reading of the printed text, so the check sits in each one rather than in shared machinery. |
| **No policy may turn on a comparison of expected damage** | `features/adversaries.py`, module comment above the parameterised features | Nothing — and that is the point. This struck out `CONDITION_ATTACK_EV_MARGIN`, which had gated the row above on a feature being worse than the standard attack by ≥ 2 expected damage. Nothing at a table computes the expected value of two damage pools and compares them, on either side of the screen. It is the same principle that leaves the Faerie's Wings unmodelled, applied to the GM: see "Imperfect information is not modelled" below, which now covers policies as well as whether to implement. |
| **The party spends one action roll hunting something that has gone to ground**, taken ahead of the shuffled options rather than among them | `combat/policy.py` → `_search_for_hidden`; `content/conditions.py` → `Condition.found_by` | Nothing; whether to look for a hidden adversary is the players'. Ruled as **one** attempt per hiding — not one per PC and not one per spotlight — and enforced by taking the `found_by` off the condition after the try, so a fresh hiding brings a fresh attempt. It is a real action roll, so it can pass the spotlight on a Fear, which is most of what makes it a cost. Taken ahead of the shuffle deliberately: everything else a PC could do is random-among-viable, and this is a decision. |
| **Anything with no policy of its own is chosen at random among the options whose costs can be paid** | `combat/policy.py` → `take_adversary_turn`; `content/registry.py` → `action_options` | Nothing. The same rule the party already plays by, and the standing default rather than a per-feature placeholder: a feature is a candidate when it can be afforded and reaches somebody, and the shuffle picks among the candidates. |
| **A Minion Group Attack is used when it reaches 2 or more Minions of that stat block** | `features/adversaries.py` → `GROUP_ATTACK_WORTH_IT` | Nothing; spending the Fear is the GM's choice. Below the threshold the feature buys nothing - it is one shared roll for the combined damage of everyone swept, so at one Minion it *is* that Minion's standard attack, bought with a Fear. Written for Minions in general rather than for the Giant Rat, since the shape recurs across the SRD's Minions. |
| **Spitter is bought at the first spotlight the Fear allows**, and its extra activation is granted **once**, on that turn | `features/adversaries.py` → `spitter` | Nothing. The die keeps rolling every spotlight for the rest of the fight, so it is worth strictly more the earlier it lands and there is no reason to hold it. The one-off grant is the Overload shape (`grant_activation`) rather than the Relentless one: the Fear buys the die *and* one extra activation that turn, and every turn afterwards the die rolls and buys nothing. |
| **`Flying (X)` is authored as the *average* uplift**, not checked per round | `features/adversaries.py` → `flying`; `adversaries/adversary.py` → `spawn` | The SRD qualifies it - "*while* flying" - and nothing tracks whether an adversary is currently airborne. Rather than invent a per-round check, the qualifier moves to the author: a creature in the air the whole fight is written `Flying (2)`, one up half the time `Flying (1)`. Over a high-N run those land in the same place, and the knob is in the JSON per adversary. |
| **An adversary spends its own HP on a feature freely, but never its last** | `adversaries/adversary.py` → `will_spend_hp`; `features/adversaries.py` → `sickening_flux` | Nothing; spending an adversary's HP is the GM's choice. Ruled as "the same reading as Stress, never the last one" — and worth knowing that the first half is vacuous: the desperation test asks whether `hp_unmarked` has fallen to `X**2 + 1` with X the slots left after paying, which when the pool *is* the HP track reduces to `hp_unmarked <= hp_unmarked**2 + 1` and is true of everything alive. So the guard is the rule: such a feature is used from full health and stops one HP short of suicide. |
| **`I've Got 'Em` doubles damage before the target's thresholds**, not after | `features/adversaries.py` → `ive_got_em`; `adversaries/adversary.py` → `_dealt`; `content/registry.py` → `damage_multiplier` | The SRD says the creature "takes double damage". Doubling the rolled total is the reading; doubling the HP marked would be a far larger effect, since damage becomes HP through bands. Applied per target, so a sweep doubles only against whoever is actually held. |
| **A Reaction whose benefit computes to zero is not taken** | `features/adversaries.py` → `reaper` | Nothing; a Reaction firing is the GM's choice. A general qualifier on rule 2 rather than a threshold for one feature: the Minor Demon's *Reaper* adds damage equal to its own marked HP, so an unhurt Demon would burn a Stress for +0 and all four would be gone before the feature was worth anything. Deliberately **not** an expected-damage comparison — the bonus is a number printed on the stat block and visible to both sides of the table, which is what separates this from the rule struck out below. |
| **Consume Kindling's flammable scenery is always to hand**, so the Minor Fire Elemental clears an HP (or a Stress once its HP track is clean) on each of its spotlights until its three uses are gone | `features/adversaries.py` → `consume_kindling`, `CONSUME_KINDLING_USES` | The SRD triggers it on the Elemental "moving onto objects that are highly flammable" — terrain, which has no representation here. Dismissing it was rejected: three clears on a 9 HP Solo is worth far too much to wave through, so the effect is modelled and the *availability* is the invented part. It makes the Elemental effectively a 12 HP adversary. HP before Stress is also ruled: HP is what keeps it on the field, and a use is never spent on nothing. |
| **Adaptability** is used only while 4 or fewer Stress are marked | `features/ancestries.py` → `ADAPTABILITY_MAX_STRESS_MARKED` | The card sets no limit. Marking the last Stress makes a PC Vulnerable for the rest of the fight, which costs far more than one rerolled attack is worth, so the last slots are held back. |
| **A feature that clears fixed quantities is used only when it can clear all of them** | `features/adversaries.py` → `adrenaline_burst`, `another_for_the_pile` | Nothing; using it is the GM's choice. The Weaponmaster's *Adrenaline Burst* clears "2 HP and 2 Stress" and is once per scene, so firing it from full health would spend a Fear and the only use on nothing. Ruled as a general rule rather than a per-feature threshold. Deliberately **not** the Consume Kindling rule next door, which is a different shape: that one clears "a HP **or** a Stress" and so takes whichever is there. |
| **A corpse is an adversary defeated in this fight**, and each one can be absorbed once | `features/adversaries.py` → `another_for_the_pile`; `combat/state.py` → `defeated_adversaries` | The SRD triggers the Patchwork Zombie Hulk's *Another for the Pile* on being "within Very Close range of a corpse", and nothing here represented a body. The Consume Kindling ruling — assume the fiction is always to hand — was offered and declined: unlike scattered kindling there is real field state to point at, and using it makes the feature depend on the encounter. A Hulk fielded alone never eats. An adversary `remove`d rather than defeated leaves no body. |
| **`Voice of the Forest`'s spotlights are free** — no Fear, and outside the party size + 1 cap | `features/adversaries.py` → `voice_of_the_forest`; `combat/state.py` → `grant_activation`, `take_free_activation`; `combat/fight.py` → `_take_gm_turn` | Nothing; the SRD caps activations nowhere, and our cap is the entry above. This is the one feature ruled to sit outside it. **Scoped deliberately**: Rally Guards, Move as a Unit, Tactician and Overload all still grant activations that cost the usual Fear and count against the cap, and none of them changed. The machinery is generic (`grant_activation(..., free=True)`) so any of them could be moved later with one keyword. What the rallied allies pay is the row below. |
| **A Taunt fixes the target's target** | `features/adversaries.py` → `goading_strike`, `goading_strike_compels`; `content/registry.py` → `party_target_override` | The Weaponmaster's *Goading Strike* prints two different durations for one clause — "until their next successful attack" and "the next time the Taunted target attacks" — so rather than pick between them the effect itself was ruled: a Taunted PC swings at the Weaponmaster until they land a hit. The first GM-side content that reaches the party's own targeting rule. What the PC then *does* to it is still theirs. |
| **A caged PC rolls to break out, and on a failure an ally spends a Stress to tear the cage open** | `features/adversaries.py` → `_thorny_cage_breaks` | The Young Dryad's *Thorny Cage* prints a Strength Roll to get free, plus "when a creature makes an action roll against the cage, they must mark a Stress" — an ally attacking the cage, which nothing here does. Ruled as the two-step above, so the printed Stress lands on the ally rather than being declared a gap. Who pays is random among the allies who can. The cage therefore holds for at most one of its victim's spotlights and costs the party either nothing or one Stress. |
| **Reckless** marks its Stress on every weapon swing the shared Stress rule allows | `domain_cards/blade.py` → `reckless` | Nothing; the card sets no limit at all ("mark a Stress to gain advantage on an attack"). No threshold of its own — it asks `will_spend_stress` — so a Reckless PC swings with Advantage from the first spotlight until one slot is left. That is a fast way through a Stress track, and it is what the card is for. |
| **Forceful Push** spends its Hope on every successful hit, skipping only a target already Vulnerable or one the hit just defeated | `domain_cards/valor.py` → `_press_them` | Using the card is a choice. Unlike Vicious Entangle's second Restrain, this buys something at 0 Fear: Vulnerable is modelled outright, so the Hope is never spent on nothing. The two skips are not thresholds — both are states visible at a table, and re-applying a condition somebody already has buys nothing (the same reasoning as the Poisoned/Cursed row above). |
| **Wild Flame never declines**, where Fire Flies declines below 2 targets | `domain_cards/codex.py` → `wild_flame`; contrast `domain_cards/sage.py` → `FIRE_FLIES_WORTH_IT` | Casting is a choice, but the two cards are not the same choice. Fire Flies spends a Hope, so aiming it at one adversary is a real cost for less than a bow. Wild Flame costs nothing but the roll the caster was making anyway, so there is no state where casting it is worse than not — and it deals its damage to whatever the Melee band happens to reach. |
| **Parallela is cast on another party member**, never the caster, and the ally is random among the conscious ones | `domain_cards/codex.py` → `parallela` | The card says "yourself or an ally". Ruled by the user for the caster's own reason: optimal play puts it on somebody else and still spends the caster's own action roll, where casting it on yourself gets one attack's use out of one spotlight. Which ally follows the standing random-among-viable rule — picking the party's best attacker would be scoring the party, which is ruled out. It declines while it would buy nothing: one adversary standing means no second target exists, and the card itself says it can only hang on one creature at a time. |
| **Enraptured fixes its holder's target**, so an enraptured adversary swings at whoever enraptured them | `domain_cards/grace.py` → `enrapture`, `enrapture_compels`; `content/registry.py` → `adversary_target_override` | The printed text is fiction — "their attention is fixed on you, narrowing their field of view and drowning out any sound but your voice" — with no mechanic attached. Ruled as the exact mirror of the Taunt ruling already made for the Weaponmaster, pointed the other way across the table. It makes Enrapture the first party card whose point is *being attacked*: it takes danger off somebody else and puts it on the caster until the GM pays a Fear. Enrapture declines against a target already enraptured, per the standing don't-re-apply rule. |
| **Rain of Blades declines below two targets**, as Fire Flies does | `domain_cards/midnight.py` → `RAIN_OF_BLADES_WORTH_IT` | Both cost a Hope and both sweep an area, so both wait until the area rule says there is more than one adversary to catch — a Hope spent on a single target is a worse weapon swing. Very Close reaches `n // 3` held to two, so on a small field this card often declines. |
| **Ferocity is bought whenever its 2 Hope can be paid** | `domain_cards/bone.py` → `ferocity` | The card sets no limit. Note this is deliberately *not* the imperfect-information case: the choice is made when the PC's own hit lands, before any attack comes back, so nothing here reads a roll a player could not see — which is exactly what separates it from Wings and I See It Coming. The common case is 2 Hope for +1 Evasion against one attack. |
| **Strategic Approach's token always buys the d8** | `domain_cards/bone.py` → `strategic_approach` | The card offers three options and says nothing about choosing. Ruled to the damage die because it is the only one always available — Advantage would have to be decided before the roll this hook is asked after, and clearing an ally's Stress needs an ally with Stress marked. The trigger, "the first time you move within Close range of an adversary and make an attack", drops its positional half and is read as **the first attack against each adversary**. A party that took no long rest walks in with the card empty, following the standing no-rest rule. |
| **Rune Ward goes to the frailest ally, and its Hope is spent only when the 1d8 could save an HP** | `domain_cards/arcana.py` → `rune_ward`, `_ward_holder`, `_could_save_an_hp` | The card says "held as a ward by you or an ally" and sets no rule for when to use it. Ruled: it goes to whoever has the least unmarked HP, **never the caster**, so a Wizard's Hope pays for somebody else's defence. It fires only when the damage is within 8 of a threshold it could fall below (Severe, Major, or 1 — that last being the hit vanishing). That test reads only what a player can see when they decide: the damage announced and their own printed thresholds. It deliberately does **not** read the Ward Die, which nobody has rolled yet, so a hit two points above Severe is warded even though a 1 wouldn't have saved it. |
| **Unleash Chaos spends every token on every cast**, refilling with a Stress whenever the shared rule allows | `domain_cards/arcana.py` → `unleash_chaos` | The card lets you spend "any number of tokens" and says nothing about how many. Ruled as all of them, so it opens at full power, empties, and comes back once the caster can afford the Stress — rather than trickling out one d10 at a time. The refill needs no threshold of its own: `will_spend_stress` already answers when a PC is willing to mark one. |
| **Unleash Chaos fills to the Spellcast trait at the start of each fight** | `domain_cards/arcana.py` → `_prime` | The card says "at the beginning of a session", and the simulator has no sessions — only fights and rests. This is the closest reading available today and it is a simplification, not a rule: once encounters run in sequence a session will span several of them and the tokens should carry over. Declared as a gap on the card too. |
| **Natural Familiar's d6 is rolled per attack against the Melee band's odds** | `domain_cards/sage.py` → `familiar_flanks`; `content/aoe.py` → `chance_within` | "When you deal damage to an adversary within Melee range of your familiar" is positioning, and none is tracked. Answered by the same function that decides whether Luckbender can reach an ally: the chance that this particular adversary is inside the familiar's Melee band. Rolled per attack rather than settled once, since where the familiar stands is exactly what changes between swings. So the d6 is near-certain in a duel and occasional in a brawl. Reading it as always-on, and as pinned to the party's focus target, were both offered and declined. |
| **Reassurance** rerolls any **failed** roll by an ally, once per rest | `domain_cards/splendor.py` → `reassurance` | The card says only "after an ally attempts an action roll". Luckbender's trigger without its Hope floor, because this costs nothing but the single per-rest use — there is no resource to weigh, and rerolling a success buys nothing measurable. An ally's roll only: the card says "an ally" where Luckbender says "yours or a willing ally's". |
| **Bold Presence** spends its once-per-rest condition dodge on the first condition that would land | `domain_cards/valor.py` → `bold_presence`; `content/registry.py` → `condition_refusal` | Nothing; the card says only "once per rest when you would gain a condition". The standing default applies - it costs nothing to use, and a PC has no way of knowing a worse condition is coming, so holding it back would be inventing foresight. It cannot stop a PC going Vulnerable by marking their last Stress, which is a standing state rather than a condition anything applies. |
| **"Another Zombie" means any adversary with "Zombie" in its name** | `features/adversaries.py` → `too_many_to_handle`, `ZOMBIE` | The Shambling Zombie's *Too Many to Handle* names a **kind** rather than a stat block, the way the Pirate Captain's *No Quarter* says "three or more Pirates" and unlike Pack Tactics' "another Sylvan Soldier". The SRD prints five Zombies in tier 1 alone. Matched on part of a name, canonically — the second feature in the catalogue to do so. |

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

### PC Stress — when a player marks it

The party side of the rule above, and deliberately a much simpler shape. A PC's
Stress is spent on cards rather than hoarded for a moment, so there is no
desperation curve here: **spend freely, except the last slot.**

```
will_spend_stress(n)  =  can_spend_stress(n)
                         and (a slot remains after paying  or  is_near_death)
```

The last slot is held back until the PC has `NEAR_DEATH_HP_UNMARKED` (2) or fewer
unmarked HP, for two reasons that compound: marking it makes them Vulnerable, so
every adversary rolls against them with Advantage for the rest of the fight, and
it also shuts off every *other* card that costs a Stress — which for a loadout
built around them is most of what the character does. Neither cost is worth one
card's use, and both stop mattering once the PC is a hit from the floor.

That is the same line an adversary's last Stress slot opens at, and the same one
the near-death rate is reported at. One number, read from one place.

**It is one rule for all PC content**, asked through `will_spend_stress` on the
character rather than re-derived per card. Two cards had their own policies
before it existed and were moved onto it; the behaviour that changed is noted in
their rows above. `spend_stress` itself is deliberately *not* gated on it — that
is the payment, and whether to make it is the caller's decision.

A knob, like its adversary counterpart: the release line is the thing to sweep.

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

The same rule does second duty as the **odds that one particular combatant is in
range**, via `content/aoe.py` → `chance_within`. Some content isn't sweeping an
area at all but needs one named person to be close by — Luckbender rescues "a
willing ally within Close range". With no positions tracked the simulator has to
put a number on that, and **the number follows the area rules**: if a band
reaches `r` of a field of `n`, any one member of that field is within it `r / n`
of the time.

Both readings come from `reach_outcomes`, which is the single definition of what
a band does — the roller draws from it, `chance_within` takes its expectation.
They were two sets of numbers until this change, a rolled count beside three
hand-written shares (Far 1.0, Close 3/4, Very Close 1/3), and adding the spread
rolls moved one and not the other. Sharing one definition is what stops that
happening again. Two of the old shares were simply wrong once the spread rolls
existed: Far is 15/16 over four rather than a certainty, and Very Close is held
below a third by its cap.

**The one thing the two readings disagree about is the floor at 1, and they
should.** A *count* never catches nobody — a sweep that fizzled entirely would be
a rounding artefact rather than a decision. A *probability* must not inherit
that: floored, Close and Very Close would be certainties over a field of one, so
the Faerie could always reach the only other party member. `chance_within` asks
`reach_outcomes` with `floor=False` for exactly that reason.

> **Known degeneracy at a field of one.** Unfloored, Close's "never all of them"
> rule leaves nothing for it to reach when there is a single other combatant, so
> `chance_within(CLOSE, 1)` is 0.0 — a Faerie in a **two-PC party** could never
> rescue her only ally. Every field size from two upward is sensible (0.5, 2/3,
> 3/4 …), and the party this simulator is built around has four, so this has no
> effect on any encounter being tuned. It is recorded rather than clamped
> because picking a number for it is a balance decision.

> **The field is whoever the band has to reach, and that is not always the
> adversaries.** "Is my ally close by?" is measured over **the rest of the
> party** — how many adversaries happen to be alive says nothing about where the
> Faerie's allies are standing, and Luckbender previously asked the question that
> way. The effect on the numbers is small but real: over a four-PC party, Close
> now comes out at 2/3 rather than a flat 3/4.

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
beat. Bone's **I See It Coming** is the same shape and got the same ruling, and
it is the **larger** of the two — +1d4 averages +2.5 and it is repeatable while
Stress lasts, where Wings is a flat +2 once. If this rule is ever revisited, that
is the card whose numbers move most. Note the boundary — this covers information genuinely unavailable when the
choice is made, not content that is merely hard to optimise. A trigger the player
can see (their own failed roll, an announced critical, an ally already down) is
ordinary content and gets modelled with a stated policy. That's exactly why
**Not This Time** is implemented and Wings is not.

**It governs how a policy is written, too, and it applies to the GM.** The rule
above decides whether to implement something; the same test then decides what a
policy may look at. An expected-damage comparison fails it on both sides of the
screen — nobody at a table works out the mean of `1d4+4` and the mean of `1d12+2`
and subtracts them — which is what removed `CONDITION_ATTACK_EV_MARGIN`. What a
policy may read is what the combatant can see: their own resources and wounds, a
condition already announced on a target, a roll that has resolved, and the GM's
Fear pool, which is open at this table. The Fear pool is worth naming explicitly,
because two PC cards depend on it — **Slumber** declines below 3 Fear and
**Vicious Entangle** only buys its second Restrain while the GM has one to lose.
The SRD does not say whether the pool is public; this table plays it face up, so
both checks stand.

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

**Hidden is modelled: every roll against a hidden combatant has Disadvantage.**
Vulnerable's exact mirror, and **ruled by the user rather than read off a page** —
the two features that apply it (the Sylvan Soldier's *Blend In* and the Jagged
Knife Shadow's *Cloaked*) both say only "become Hidden", so what being Hidden is
worth had to be decided. `combat/state.py` → `is_hidden`, folded into the roll by
`items/weapons.py` on the party side and `combat/policy.py` on the GM's.

What is *not* modelled is the SRD's other use of Hidden — that it stops a
combatant being targeted at all. Focus fire still picks its target the same way,
and the Disadvantage is the whole of the cost. Declared as a gap on Cloaked.

**A condition can carry a roll somebody else spends a turn on**, through
`Condition.found_by` — `("instinct", 14)` for Blend In, which lifts when "a PC
succeeds on an Instinct Roll (14) to find them". Distinct from `end`, which the
holder is offered free at each announced moment: this one costs a whole action
roll, and the ruling is that the party spends **one** of them per hiding, taken
ahead of the shuffled options rather than among them (`combat/policy.py` →
`_search_for_hidden`). A condition with no `found_by` offers no such roll, which
is why a cloaked Shadow cannot be hunted — the page prints no roll for it.

**Shadowbind is the first party card whose whole value is the Fear it costs the
GM.** Midnight's level 2 area spell Restrains everything it beats within Very
Close, and Restrained does nothing by itself here (below) — so what the card
actually buys is one Fear per adversary bound, spent on the GM's turn to shake
it off, or nothing at all if the GM would rather leave them bound. That falls out
of two rulings made long before the card, and it is worth naming because the
result is a Fear-burner rather than the control spell the page describes. If
Restrained is ever given an effect, this is the card that changes most.

**Restrained is recorded, and still does nothing by itself.** It stops a
combatant moving and no movement is modelled, so the condition has no effect of
its own — that ruling is unchanged. What *is* new is that a feature applying one
now writes it down, with `Condition.source` naming who applied it, because other
content asks: the Jagged Knife Kneebreaker's `I've Got 'Em` doubles the damage
its allies deal to creatures **it** has Restrained, and a condition nobody
recorded is one nothing can key on. Bite, Grab and Drag, Detain and Hold Them
Down all record theirs. What stays declared as a gap is the movement.

**A hold ends when the thing holding you leaves the fight.** Not printed
anywhere, and it has to be a rule: a condition with a `source` and **no `end` of
its own** is written to be lifted by something happening to whoever applied it -
Envelop ends when the Ooze takes Severe damage, Grab and Drag when the Defender
does - and an adversary that is dead or gone can never take any damage again. So
such a condition would sit on a PC for the rest of the fight with no way out,
which is harsher than anything the SRD prints. `combat/state.py` →
`release_conditions_from`, called from both exits: `remove` and the defeat check
in `Adversary.take_damage`.

Worth knowing how ordinary this case is rather than treating it as a corner. The
Green Ooze has thresholds of 5/10 on a 5 HP track, so **two Major hits kill it
and a Severe one never lands** - the printed release is the exception, not the
rule.

**A condition that carries its own ender is deliberately left alone**, which is
the half that stops this becoming "clear everything". The Minor Chaos Elemental's
Sickening Flux makes a PC Vulnerable "until their next rest or they clear a HP":
it names its own exit, so killing the Elemental must not cure it. The same spares
every hold that offers an escape roll - a PC Restrained by a dead Bear can still
roll out, and nothing is stranded.

**A printed way out of a hold is modelled, not skipped.** Where the SRD ends a
condition on a roll ("until they break free with a successful Strength Roll"),
the held PC attempts it as a Reaction Roll at each announced moment —
`features/adversaries.py` → `_breaks_free` — using the **best** of the traits the
text offers, since the player would choose. Where it ends on the holder being
hurt ("until the Defender takes Severe damage"), an `on_damaged` hook frees
everyone that adversary is holding — `_release_held`. What is not modelled is the
*cost* of trying: the attempt rides on the announced moments rather than
spending the PC's spotlight.

**Enraptured is Taunted's mirror**, and got the same ruling for the same reason:
Grace's *Enrapture* describes an adversary's attention being fixed on the caster
and attaches no mechanic, so the effect was ruled rather than read. An enraptured
adversary swings at whoever enraptured them until the GM pays a Fear. It is read
by the *GM's* targeting rule through `content/registry.py` →
`adversary_target_override`, the exact counterpart of the hook Taunted uses on
the party's side — kept as two hooks rather than one, because merging them would
let party content compel a PC.

**Taunted fixes its holder's target**, which is the third condition ruled rather
than read — the Weaponmaster's *Goading Strike* prints two different durations
for one clause, so the user settled the effect instead of choosing a sentence. A
Taunted PC swings at whoever taunted them until they land a hit. It is the first
condition read by the *party's* targeting rule, through
`content/registry.py` → `party_target_override`, and the first whose ender is an
attack roll succeeding rather than an announced moment — so it lifts from
`on_party_attack_roll` rather than from a `Condition.end`. It carries a source and
no `end`, so a dead Weaponmaster releases it like any other hold.

**A condition can be refused as it lands, which is not the same as immunity to
it.** The Valor card *Bold Presence* shrugs one off per rest, and that had to be
its own hook: `immunity` is a *standing* answer read wherever a condition's
effect is consulted — the Guardian's Unstoppable turns Vulnerable off while it
runs, and the condition is still there when it stops — where this is asked once,
at the moment the condition would land, and a refusal is permanent. Folding the
two together would have broken Unstoppable, since a condition applied while it
ran would never have come back. `content/registry.py` → `condition_refusal`,
`refuses_condition`, asked from `combat/state.py` → `apply_condition`. A refresh
of a condition already held is not offered, so a once-per-rest dodge is never
spent on one.

**Enraptured** is modelled as the target-fixing described above.

**On Fire is modelled, and it is the one condition that arrived with its own
mechanic.** Every other condition here had to be ruled on because the SRD gives
it a name and nothing else; Arcana's *Cinder Grasp* prints the rule on the card —
"when a creature acts while On Fire, they must take an extra **2d6** magic
damage if they are still On Fire at the end of their action" — so the burn is
simply what the page says. It rides `Condition.effect` at `WHEN_THEY_ACT`, and
it lasts until the GM spends a Fear to put it out, which is the standing reading
for a condition the party puts on an adversary. That makes the card a question
the GM has to answer, and it costs them either way.

Closing it needed one thing in the loop: `WHEN_THEY_ACT` was announced to a
**PC's** conditions only, and only for expiry. Both sides now get both halves —
effects first, then expiry, because "at the end of their action" puts the burn
before the chance to shake it off (`combat/fight.py` → `_take_pc_spotlight`,
`_take_gm_turn`). Nothing else changes: until On Fire existed, every condition an
adversary could carry either did nothing by itself or ended on a GM turn.

The rest — Stunned — has no representation and nothing applies it.

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

**Both sides make them, on different dice.** A PC rolls Duality Dice plus the
named trait. An **adversary rolls a flat d20 with no modifier**, because a stat
block carries no traits — the bare die against the Difficulty
(`features/adversaries.py` → `_reaction_roll`). Both results answer `is_success`
and `is_critical`, which is all any feature reads, so no feature has to know
which side rolled.

**Read the printed noun: "creatures" includes the adversary's own side,
"targets" does not.** The SRD alternates the two deliberately. The Minor Fire
Elemental's *Scorched Earth* and the Acid Burrower's *Earth Eruption* both say
"all creatures", so both catch allies — and those allies get a real d20 save.
The Minor Demon's *Hellfire* says "all targets" and reaches only the party. The
first two land in the same batch as the third, which is what makes the
distinction hard to put down to loose wording. It matters for encounter building:
a Fire Elemental is awkward to field beside anything fragile and a Demon is not,
and an Earth Eruption that knocks another adversary over hands the party
Advantage on every roll against it.

**A d20 Reaction Roll is checked against a Difficulty, passed as `evasion`.**
Ruled deliberately rather than renamed: `roll_d20` and `D20RollResult` keep the
specific name because it is right for the use they have almost everywhere — an
attack resolved against a PC's Evasion — and a Reaction Roll is the one caller
that puts a different number in the same slot. It is a number to beat either way,
and generalising the name would have traded clarity at dozens of call sites for
vagueness at all of them.

**A success can buy half rather than everything.** Scorched Earth and Hellfire
both read "targets who fail take X. Targets who succeed take half damage", which
is the first place a save is worth something short of a clean escape. Half rounds
down, and a critical still takes nothing — so "success" and "critical" have come
apart and each needs saying (`features/adversaries.py` → `_flames`).

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
| An attack rolled **against a whole area** ("against all adversaries within Close range") is one roll checked against each target's own Difficulty. The roll counts as a success if it beat the **lowest** Difficulty in the area | `content/aoe.py` → `area_difficulty`, `targets_beaten`; `domain_cards/sage.py` → `fire_flies`; `domain_cards/codex.py` → `wild_flame` | Such a spell has no single Difficulty, but the spotlight rules need to know whether the roll succeeded. Reading it as "you beat somebody" keeps the spotlight on a partial hit; reading it as the highest would hand the spotlight over whenever the toughest adversary shrugged it off. This is a different shape from Whirlwind, which rolls against one target and reuses that roll. |
| Extra damage dice a feature adds for how the attack roll came out (**Face Your Fear**) are rolled **as part of the same damage roll**, not applied afterwards | `content/registry.py` → `extra_damage`, `total_extra_damage`; `items/weapons.py` → `_attack_with` | The SRD says "you deal an extra 1d10 magic damage", which reads as one total. Applying it after the fact would measure it against the target's thresholds a second time and could mark an HP the rules never intended. |
| **Reinforced** (armor) applies to the hit that marked the last Armor Slot, not only to later ones | `features/armor.py` → `reinforced` | The SRD raises the thresholds "when you mark your last Armor Slot". By the time damage responses are consulted that slot has already been marked, so the wearer is in the state the feature describes. Reading it the other way would need the damage pipeline to remember what armor looked like before the hit, for a difference of one HP on one hit per fight. |
| A **weapon's** feature applies only to attacks made with that weapon; an **armor's** applies to everything that happens to its wearer | `items/weapons.py` → `attack_with`; `characters/player_character.py` → `named_features`, `weapon_features` | Not an ambiguity in the rules so much as one the code could easily introduce. Dispatch is holder-scoped by default, so registering a Broadsword's *Reliable* that way would silently add +1 to a Wizard's spell attacks. Armor genuinely is holder-scoped - Fortified changes what any hit costs - so the two reach a fight by different routes. |
| **Massive**/**Powerful** discard the lowest of the dice *the weapon* rolled. Dice a feature added are rolled alongside and added to the same total, out of the discard's reach - and the total is still checked against the thresholds once | `dice/damage.py` → `DiceGroup.discardable`, `dropped`, `critical_bonus` | "Roll an additional damage die and discard the lowest result" doesn't say whose dice. The feature belongs to the weapon, so its discard is read as reaching only the weapon's own pool; the other reading lets a Greatstaff throw away a Wizard's Face Your Fear die. |
| **At most one reroll applies to any roll.** The first piece of content willing to re-make it wins, and nothing else is asked | `content/registry.py` → `remake_action_roll`, `force_adversary_reroll` | Nothing in the SRD forbids a party stacking Luckbender on top of Adaptability for a third attempt at one roll, but no card describes a chain off a single trigger, and allowing it would make a failed roll cheap. |
| A reroll re-makes the **whole** roll, not only the Duality Dice — but re-rolls only the *dice*, never the decisions that fed them: bonuses, the Hope Die and any Experience are worked out once and reused | `items/weapons.py` → `attack_with`; the `_spellcast` helpers in `domain_cards/` | Luckbender and Adaptability both say to reroll the Duality Dice, which would leave an Advantage or Help die standing; re-making everything differs only on rolls that had one, and is declared as a gap on both. Holding the modifiers fixed is not optional — asking content for a roll bonus is the commitment, so several of them spend Hope or mark Stress on being asked, and re-asking would charge twice. |
| An adversary's **area attack** is one roll checked against each target's Evasion, with one damage roll applied to everyone it beat | `adversaries/adversary.py` → `area_attack`; `content/aoe.py` → `targets_hit` | The mirror of the reading already used for a PC rolling against an area, and of `Hold Them Off` reusing one roll against several. The roll's own success is measured against the *lowest* Evasion present, for the same reason the PC side measures against the lowest Difficulty: it either beat somebody or it beat nobody. |
| A feature keyed on "takes **Severe damage**" reads the number rolled; one keyed on "marks **2 or more HP**" reads what the hit cost | `features/adversaries.py` → `acid_bath`, `rampaging_fury`; `content/registry.py` → `on_damaged` | The SRD writes both kinds and means different things by them, so `on_damaged` is handed both figures and each feature reads the one its own text names. |
| Content that **worsens** a hit is asked after content that softens it, and **Weak Structure** fires only on a hit that actually marked HP | `content/registry.py` → `harden_damage`, `severity_increase`; `features/adversaries.py` → `weak_structure` | "When the Construct marks HP … they must mark an additional HP" doesn't say whether that's the HP the damage started at or the HP it ended at. Reading it as the final amount means a hit an Armor Slot or a domain card absorbed entirely marked nothing, so there is nothing to add to - which is what the trigger says on its face. Fixing the order in the dispatch rather than in each feature keeps the answer the same however many features register |
| An adversary feature's text is about **that adversary**: "when the Captain marks 2 or fewer HP" is the Captain marking it, not the Captain making a PC mark it | `features/adversaries.py` → `swashbuckler` | Daggerheart's design language throughout, and worth recording because the other reading is grammatically available and would turn a defensive quirk into a second attack. It also settles the lower bound: **adversaries have no Armor Slots**, so an attack that lands on one always marks 1 or 2 HP against a threshold band and the zero case cannot arise. A PC is the asymmetric case — the free slot means they routinely mark none — which is why content on the party side has to check for zero and this doesn't. |
| **No Quarter**'s "three or more Pirates" counts any living adversary with "Pirate" in its name, and asks the **area rule** how many are in range | `features/adversaries.py` → `no_quarter`, `PIRATE`, `NO_QUARTER_PIRATES` | The SRD writes the requirement as a *kind* rather than naming stat blocks, unlike On My Signal's "all Archer Guards" — so this is the one feature that matches on part of a name. The range half follows Pack Tactics exactly. Consequence worth knowing: the Melee band reaches at most 3, and only on a field of `MANY_ADVERSARIES` or more with the clustered roll, so **the feature cannot fire below six pirates**. That falls out of the printed 3 meeting the band; lowering it to 2 was offered and declined. |
| **Pack Tactics** asks the **area rule** whether the pack converged: of the wolves alive, `targets_reached(MELEE, ...)` says how many are on this target, and the feature needs 2 - the attacker and one more | `features/adversaries.py` → `pack_tactics`, `PACK_TACTICS_WOLVES` | "Another Dire Wolf within Melee range of the target" is positioning, and none is tracked. Reading it as "is another wolf alive anywhere?" would fire on every standard attack for as long as any packmate stood, which is far more than the page promises - so the Melee band answers instead. Since that band is rolled, a pair converges about half the time and a pack of six always does, and how often the band lets it through is the whole of what holds the feature back. |
| **Armor-Shredding Shards** reads "within Melee range" off the **attacker's weapon**: everyone is assumed to have attacked from the greatest range their weapon allows, so a Melee-only weapon triggers it and anything reaching further does not | `features/adversaries.py` → `armor_shredding_shards`; `items/weapons.py` → `attack_with` | No positions are tracked, so the trigger needs some handle on distance and the weapon is the only one there is. It makes the feature a tax on the front line and free for archers, which is the shape it has at a table - and it means a party's answer to the Glass Snake is a weapon choice. Only weapon attacks reach it; content that rolls an attack of its own has no weapon and no range, declared as a gap |
| A **Minion Group Attack** is **one activation** however many Minions it sweeps, but each Minion swept has its own spotlight consumed and doesn't act again that GM turn | `features/adversaries.py` → `group_attack`; `combat/state.py` → `consume_activation`; `combat/fight.py` → `_next_adversary` | "Spend a Fear to choose a target and spotlight all Giant Rats within Close range" - the SRD spotlights several combatants with one feature, which nothing in the loop had a shape for. Charging one activation follows from it being one shared attack roll; consuming the rest follows from them having been spotlighted. Reading it the other way (one activation each) would let a swarm act, then act again, and would empty the GM turn's budget into a single feature |
| **Resistance halves a hit *before* its thresholds are read**, so it changes how many HP the hit marks rather than only the figure rolled | `content/damage_types.py` → `reduced`; `characters/player_character.py` and `adversaries/adversary.py` → `take_damage` | Not really an ambiguity — the SRD says "reduce incoming damage of that type by half **before comparing it to their Hit Point Thresholds**" — but it is worth recording, because it is the whole size of the effect. Against the Minor Chaos Elemental's thresholds of 7 and 14, a 13-point spell goes from marking 2 HP to marking 1; halving afterwards would have been worth nothing at all. It is the same place `I've Got 'Em`'s doubling already lands. |
| Several resistances fold by taking the **strongest single** one, never by multiplying | `content/damage_types.py` → `strongest` | SRD: "the effects of multiple resistances to the same damage type do not stack." Multiplying would make a second resistance quarter the hit, and a resistance beside an immunity is simply the immunity. |
| **Untyped damage matches nothing.** It is never resisted, and it satisfies no type restriction either | `content/damage_types.py` → `damage_type_named`; `content/registry.py` → `resistance_to`, `severity_response` | Damage should always have a type, and after this change everything in the simulator states one bar the Beastbound companion. Where a type is nevertheless missing, the ruling is that it can only ever *fail* to apply an effect and never wrongly apply one — so a gap in the authoring shows up as nothing happening rather than as the wrong thing happening. A type that is **stated and misspelled** raises instead, because that is the case where the failure would otherwise be invisible. |
| An adversary feature that states **no damage type** deals the type of its stat block's **standard attack** | `adversaries/adversary.py` → `type_of_damage`; `features/adversaries.py` → `magical_reflection`, `on_my_signal_ticks` | The same shape as the damage rule below it, applied to the type, and ruled by the user in the same words. So the Minor Chaos Elemental's *Magical Reflection* rebound is **magic** — the Elemental's own, not the attacker's blow returning in kind — and the Archer Guards' countdown volley takes the *Archer's* type rather than the Head Guard's. A feature that states a type on the page overrides it, which is what makes the Construct's *Death Quake* magic out of a physical stat block. |
| An adversary feature that makes an attack deals **whatever damage it states, and otherwise the adversary's standard damage** | `features/adversaries.py` → `detain`; `adversaries/adversary.py` → `_damage_for` | The SRD prints all three cases and only two of them explicitly: dice of its own (Bite at 3d4+10), no damage at all (the Kneebreaker's Hold Them Down, which says "the target takes no damage"), and silence. Silence is read as the standard attack, and the corroboration is that Hold Them Down has to say otherwise — a clause only worth printing if damage is the default. Passing no dice keeps it true mechanically too, since `dice is None` is already the discriminator for "the printed attack", so a standard-damage swap reaches such a feature. |
| An **interrupting Reaction does not cancel the attack it interrupts** | `content/registry.py` → `before_attacked`; `features/adversaries.py` → `fall_back` | The Harrier's Fall Back fires "before the attack roll" and moves the Harrier out of Melee, which could be read as making the attack impossible. Nothing in the SRD says it is cancelled, and a PC can move within Close range as part of their own action, so one whose target backed off would simply follow. So the hook can't veto: what the Reaction buys is the counterattack it comes with. Reading it the other way would turn the Harrier's three Stress into three negated melee attacks and make the stat block far stronger. |
| **"Moves into Melee range to make an attack" is read off the attacker's weapon** | `features/adversaries.py` → `fall_back` | The same handle on distance Armor-Shredding Shards already uses, and the only one there is: a Melee weapon triggers it, anything reaching further does not. |
| **On My Signal** triggers **once**, every Archer Guard fires at the **same** PC, and their successes are **combined into one damage roll** | `features/adversaries.py` → `on_my_signal_ticks` | The SRD only re-arms a countdown that says it loops, and this one doesn't. "The nearest target within their range" is positioning; the standing targeting rule stands in for it, asked once on the Head Guard's behalf, which is also what leaves "if any attacks succeed on the same target, combine their damage" with anything to do. Combining is not a rounding detail: three separate hits of 7 mark 3 HP, while one combined 21 is Severe. |
| **Tactician does not cost the Lieutenant its action** | `features/adversaries.py` → `tactician` | The SRD files it as an Action, but the text triggers "when you spotlight the Lieutenant… to **also** spotlight two allies". Ruled as a rider on being spotlighted, so it registers on `on_spotlight` and the Lieutenant still attacks afterwards. Reading it the other way would make it one option among several and roughly halve how often a Jagged Knife band gets its extra activations. |
| **Magical Reflection** reads "within Close range" off the attacker's weapon, and halves the damage **rolled**, rounding down | `features/adversaries.py` → `magical_reflection` | The same handle on distance Armor-Shredding Shards uses, so Melee, Very Close and Close weapons trigger it and Far ones don't. "The damage they dealt" is read as the number rolled rather than the HP it cost, so a hit the Elemental shrugged off still rebounds at full size. The rebound's **type** is the Elemental's own — see the untyped-feature entry above. |
| **Split** takes the Green Ooze off the field **without defeating it** | `combat/state.py` → `remove`; `features/adversaries.py` → `split` | "Split them into two Tiny Green Oozes" leaves nothing said about what becomes of the original, and `is_defeated` was the simulator's only way for anything to leave. Marking its HP would have looked identical to the loop and lied to the reader — a play-by-play announcing the Ooze "defeated" as the field doubles reads as a win. A defeated Ooze also doesn't split, since a stat block that split as it died would let one Fear undo the kill. |
| **Parallela's second target takes the full damage roll**, and the spell is spent on the next attack that **lands** rather than on the next one attempted | `domain_cards/codex.py` → `parallela_doubles`; `content/registry.py` → `ally_on_hit`, `apply_ally_on_hit` | "They can hit an additional target within range that their attack roll would succeed against" says nothing about halving, so nothing is halved — the same reading Hold Them Off gets, and the opposite of Whirlwind, which says "half damage" outright. "The next time the target makes an attack" is the looser half: read as the next attack that connects, so a miss doesn't burn 2 Hope on a roll that hit nobody. Where the roll beat several adversaries, which one gets the second hit is random. |
| **Bolt Beacon's Hope is the delivery, not an upgrade**, so with none banked the spell isn't cast at all | `domain_cards/splendor.py` → `bolt_beacon` | "On a success, **spend a Hope** to send a bolt of shimmering light toward them, dealing d8+2" puts the entire damage clause inside the Hope. Read as: no Hope, no bolt — so the card declines before rolling rather than rolling and then failing to pay, which would waste the spotlight. The Vulnerable is stated as part of what the bolt does rather than bought separately, which is why nothing weighs whether to apply it. Contrast Forceful Push, where the attack lands either way and the Hope buys only the condition. |
| **A critical is its own outcome — neither "with Hope" nor "with Fear"** | `features/subclasses.py` → `face_your_fear`, `_press_the_advantage`; `domain_cards/valor.py` → `forceful_push_momentum` | The two dice matched, so neither won. Content keyed on "a success with Hope" or "with Fear" therefore doesn't fire on a crit, which is already paying out the maximum of every damage die. Asking for `outcome` rather than comparing the dice keeps this right for free at every site. |
| **Not Good Enough** rerolls each qualifying die **once**, after the dice are read and before any discard | `content/registry.py` → `damage_die_reroll`, `reroll_damage_dice`; `domain_cards/blade.py` → `not_good_enough`; `items/weapons.py` → `attack_with` | "Reroll any 1s or 2s" doesn't say whether a rerolled 2 can be rerolled again — read as one fresh throw per die, so a reroll can come up a 1 and stay there. Ordering against Massive/Powerful is unstated too: the reroll happens first and the discard then takes the lowest of the *new* results, which falls out of `dropped` being derived rather than stored. The other order would sometimes throw away a die that was about to improve. |
| A die discarded by **Massive**/**Powerful** doesn't count toward the critical bonus - a crit adds the maximum of the dice that were kept, not of every die rolled | `dice/damage.py` → `critical_bonus` | A crit "adds the maximum possible result of the damage dice"; the SRD doesn't say whether a discarded die is still one of "the damage dice". Counting it would pay for a die that was thrown away. |
| **Opportunist** counts every living adversary, the Skeleton Archer included, and asks the **area rule** how many of them are on the target | `features/adversaries.py` → `opportunist`, `OPPORTUNIST_ADVERSARIES` | "When two or more adversaries are within Very Close range of a creature" names a number of adversaries rather than "other adversaries", where Pack Tactics is explicit about "*another* Dire Wolf" — so the Archer counts itself, the same reading No Quarter takes of its three Pirates. The range half follows Pack Tactics and No Quarter exactly. Consequence worth knowing: Very Close reaches `n // 3` capped at 2, so **the feature cannot fire below six adversaries** — the No Quarter situation again, arriving from a printed 2 meeting the band rather than from any threshold of ours. It is also the mirror of `I've Got 'Em` on the same hook: that one belongs to a third party and doubles what *other* adversaries deal, this one belongs to the attacker and doubles only its own. |
| **Terrifying** hands the GM **one** Fear, not one per PC | `features/adversaries.py` → `terrifying` | "All PCs within Close range lose a Hope and you gain a Fear" is grammatically open to either. The corroboration is two entries further down the same page: the Patchwork Zombie Hulk's *Tormented Screams* has to write "you gain a Fear **for each**" to get the other reading, which is only worth printing if a bare "you gain a Fear" means one. The Hope loss is an *area* and so goes through `targets_in_area`, where the Minor Demon's All Must Fall asks `chance_within` because its trigger is one particular PC's roll. |
| **Dig Two Graves** fires however the Knight died, and really does prioritise the creature who killed it | `features/adversaries.py` → `dig_two_graves`; `combat/policy.py` → `_make_the_roll` | Registered on `on_damaged` rather than `on_attacked` so a Knight killed by a spell, an area effect or another adversary's splash still gets its parting swing — the attack-side hook only ever sees a PC's weapon. The priority then needed one thing moving: the targeting memory behind "whoever hit this adversary last" was written *after* an attack resolved, so at the moment of death it still named whoever hit the Knight the time before. It is now written **before** the attack instead. Nothing outside an attack can tell the difference — an adversary picks its target on the GM's turn, long after either write — but content firing from inside one can, and this is the first thing to ask. |
| **A hit that is both physical and magic is resisted if the target resists *either***, and satisfies a restriction naming either | `content/damage_types.py` → `BOTH`, `includes`, `types_in`; `content/registry.py` → `resistance_to`; `features/adversaries.py` → `arcane_steel` | The Spellblade's *Arcane Steel* says its standard attack is "considered both physical and magic", which is grammatically open both ways: counting as both for everything, or resisted only by something resistant to both. The second would have made the feature an upgrade; the first makes it a liability against a resistant target, and is what was ruled. The pair is a frozenset rather than a third `DamageType` member, because a third member would have answered False to every `damage_type is DamageType.PHYSICAL` check in the codebase — precisely the checks that ought to pass. Those five sites now ask `includes` instead. |
| **Pack Tactics carries its printed difference in its parameter**: `Pack Tactics (1d6+5, Fear)` on the Dire Wolf, `Pack Tactics (1d8+5)` on the Sylvan Soldier | `features/adversaries.py` → `pack_tactics`, `PACK_TACTICS_FEAR`; `adversaries/srd.json` | The SRD prints the same feature name on two stat blocks with two different texts — different dice, and only the Wolf's pays the GM a Fear. Parameterising the damage alone and dropping the Fear was offered and declined, because that changes a stat block already ported rather than changing how one is authored. So the argument carries two terms, and the printed difference lives in the JSON where a reader can check it against the page. |
| **Forest Control hits one creature, not an area** | `features/adversaries.py` → `forest_control`, `FOREST_CONTROL_DIFFICULTY` | "A creature hit by the tree must succeed on an Agility Reaction Roll (15)" is singular, and the SRD is careful to write "all targets" or "all creatures" when it means an area — Suppressing Blast does so on the same page. Reading it as an area was offered and declined. Its Difficulty is **printed** (15) rather than falling back on the Soldier's own 11, which is one of the few reaction rolls in the catalogue to state one. |
| **Suppressing Blast is a clean escape, not a save for half**, and pays the GM a Fear **per target who marked HP** | `features/adversaries.py` → `suppressing_blast` | Scorched Earth and Hellfire both print "targets who succeed take half damage" and share `_flames`; this one prints nothing of the kind, so a successful roll takes nothing and it is deliberately not written through that helper. The Fear clause is also its own shape — "for each target who **marked HP**", where Hail of Boulders pays once for beating more than one target — so a hit an Armor Slot swallowed whole earns the GM nothing. |
| **Drain and Multiply merges Minions into a Horde whose HP is the count**, not the Swarm's printed 6 | `features/adversaries.py` → `drain_and_multiply`; `combat/state.py` → `remove`, `summon` | "The Horde's HP is equal to the number of Minions combined" — spawned with an override, the way an encounter tunes a stat block. The mirror of the Green Ooze's *Split*: that is one becoming two smaller, this is several becoming one larger, and both leave the field through `remove` rather than by being defeated so the play-by-play never claims the party won something. Note the GM can make itself *frailer* by using it; nothing holds that back, since weighing it would be a comparison of what a combatant is worth. |
| **Encumber's two ways out are not equivalent**: the Finesse Roll spawns Minions, Major damage to the Swarm does not | `features/adversaries.py` → `encumber`, `_bramble_escape`, `encumber_releases` | Printed exactly that way, and it is the tactical shape of the stat block — cutting the brambles is cleaner than struggling out of them. The escape Difficulty is the only one in the catalogue that **moves**: 12 + the current token count, so a PC who waits gets harder to free and lets more Minions loose when they finally are. |
| **Won't Stay Dead**'s "you can spotlight them" is an **activation, charged as usual**; a Warrior that comes back has not spent it | `features/adversaries.py` → `wont_stay_dead`, `wont_stay_dead_waits`, `wont_stay_dead_skips`; `combat/fight.py` → `_next_adversary` | The page makes the spotlight the thing that buys the d6, without saying what it costs. Ruled as an ordinary activation: it waits for a GM turn with a spotlight to spare, costs the usual Fear for every activation past the turn's first, and counts against the party size + 1 cap. So a Warrior cut down on a PC's spotlight lies there until the GM comes round, and a busy field with an empty Fear pool may never get the roll. The stricter reading — that re-forming *spends* that spotlight, the `Slow` shape — was offered and declined, so a Warrior that rolls a 6 acts on the same activation. Two smaller readings go with it: **only HP is cleared**, since the page says HP and only HP, so a Warrior that spent its Stress comes back with it still spent; and the feature is **uncapped**, since the page prints no limit. It cannot stall a fight, because the roll needs another adversary standing and the last thing on the field therefore never returns. |

## 3. Not implemented

Real rules we knowingly skip. Listed so a result is never mistaken for a
complete simulation of the game.

> **Per-combatant content is tracked in code, not here.** Domain cards,
> ancestries, communities, classes, subclasses, gear features and adversary
> features each declare their own state in `content/registry.py` — *modelled*
> (optionally with declared gaps), *no combat effect*, *insignificant combat
> effect* (both with a reason), *out of combat*, or *unimplemented*. Every run
> prints the breakdown per combatant, so this section covers only the rules that
> apply to everyone. Never leave content silently absent when the answer is "it
> can't matter" or "it barely matters": declare it, so a judgement never looks
> like a gap — and never park a decision in *unimplemented*, which reports it as
> work nobody has done.

- **Abilities used between fights, not in them.** *Out of combat* is a state of
  its own and deliberately not a third dismissal: the effect is real and fully
  representable, it simply never happens inside an encounter. The Blade card **A
  Soldier's Bond** is the first — once per long rest, complimenting an ally gives
  you both 3 Hope, which nobody stops mid-fight to do. Nothing runs today because
  encounters are simulated one at a time; when they are run in **sequence**, this
  state is the list of what the party does in the gaps. `content/registry.py` →
  `out_of_combat_ability`, and see `combat/rest.py` for the rest machinery it
  will hang off. Three cards are in it: **Blade's A Soldier's Bond** (3 Hope each
  to two PCs off a compliment), **Splendor's Mending Touch** (2 Hope for a HP or
  a Stress, gated on "a few minutes to focus"), and **Grace's Inspirational
  Words** (a pool of tokens equal to Presence, each clearing a Stress or a HP or
  handing over a Hope). Together they are most of a support character's
  contribution between fights, which is the point: none of them is small, and all
  of them are waiting on the same machinery

- **Massive Damage** (SRD-optional: 2× Severe marks 4 HP instead of 3) — `characters/player_character.py`
- **Range and positioning entirely.** Every range band ("Melee", "Very Close", "Far") is treated as always satisfied. This is why `I Am Your Shield` never checks distance, and why adversary features keyed to position are skipped.
- **All conditions except Vulnerable, Hidden, On Fire and the trait hobble** — see the conditions section above. Restrained is *ruled* to have no combat effect here rather than merely absent; Stunned has no representation and nothing applies it. *Cursed* (the Jagged Knife Hexer's) is a named condition whose whole effect is its own feature's, so it needs nothing from this list.
- **Direct damage bypasses the Armor Slot only.** `characters/player_character.py` → `take_damage(direct=True)`; `content/registry.py` → `direct_damage`, `deals_direct_damage`. Thresholds still decide how many HP it costs, and damage responses still get their say — the SRD's restriction is on armor. Against this party it's worth close to a whole HP per hit, since the policy otherwise marks a free slot against everything
- **Adversary Fear features** — no adversary has one implemented yet. Note this is distinct from features that merely *cost* the GM Fear, several of which are modelled (Ramp Up charges to spotlight, Grab and Drag spends on a hit)
- **Adversary Experiences — ruled out, not outstanding.** The SRD gives adversaries optional Experiences the GM can spend a Fear on, "to raise their attack roll or increase the Difficulty of a roll made against them". The user has decided not to model them, and the reason is the Fear economy rather than the effort: this simulator already commits a great deal of Fear to extra activations, and an Experience competes for that same Fear while buying a comparatively minor bonus on a single roll. A GM in this simulator would essentially never take that trade, so implementing it would add a branch that never fires. They stay recorded in each catalogue entry's `notes` so an entry remains checkable against the printed page, and there is deliberately no field and no mechanic. This is a decision, so it does not belong on anyone's list of work to do
- **Adversary `type` is data only.** The SRD gives a type no rules of its own — "an adversary's type represents the role they play in a conflict", then one descriptive line each. Everything mechanical that sounds like a type is printed as a named *feature* (`Minion (X)`, `Horde (X)`, `Relentless (X)`, `Slow`, `Arcane Form`, `Armored Carapace` are all SRD example passives), so the fight loop never reads `Adversary.type`. It is carried because it's on the printed page and because it's what "Social adversaries aren't ported" keys on — see `adversaries/PORTED.md`
- **Adversary passive features** — named in `adversaries/srd.json` rather than sitting in a code comment, so they reach the coverage block. All three Jagged Knife passives are assessed in `features/adversaries.py`: *Climber* has no combat effect, and *From Above* (+1 expected damage) and *Unseen Strike* (+2) are declared **insignificant**, because damage reaches HP through threshold bands and a bump that size lands within a band far more often than across one. Neither is left *unimplemented* — that state is for work nobody has done, not for a decision
- **Most of the SRD armor table.** Only what the current sheets equip is catalogued in `items/srd.json`. Fortified, Resilient, Shifting, Impenetrable, Painful, Hopeful, Burning and the rest are real mechanics with nothing behind them yet — an armor naming one reports as unimplemented the moment it's equipped
- **Armor Score and armor thresholds are never read from the catalogue.** A sheet carries them already resolved (see the standing rule on sheet-resolved values), so `items/*.json` records them as provenance only. The consequence is that a sheet whose numbers don't match the armor it names will not be caught
- **Subclass features above the foundation tier.** Specialization (level 5) and mastery (level 8) features are declared as gaps on each subclass rather than implemented, since the current party has neither tier
- **Nothing ever attacks the Beastbound companion**, so its Stress, and dropping out of the scene when its last Stress is marked, don't exist here. It contributes damage and carries no risk
- **One damage roll carries one type.** Where a feature adds dice of a *different* type to an attack's own roll, the whole total takes the weapon's type. The School of War's **Face Your Fear** is the case — an extra 1d10 of magic riding a swing that may be physical — and the two readings are mutually exclusive: splitting the roll in two would measure each half against the target's thresholds separately, which is the exact error `extra_damage` exists to avoid. The type loses, the single threshold comparison wins, and it is declared as a gap where the feature is registered
- **The Beastbound companion's damage is untyped.** The companion sheet says "physical or magic as the player chose" and no choice has been ruled, so its bite is the one thing left in the simulator that deals damage without stating a type — and therefore the one thing no resistance is ever applied to. Declared as a gap on Beastbound; awaiting a ruling
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
- **GM-side content can hobble a PC's attack based on who they chose to attack** — `content/registry.py` → `party_attack_disadvantage`, `party_attack_is_hobbled`; `items/weapons.py` → `attack_with`. The Swarm of Rats' *In Your Face* ("all targets within Melee range have disadvantage on attacks against targets other than the Swarm") is the first, and `Condition.disadvantage_on` cannot say it: that hobbles a named *trait*, and the trait is the same whichever adversary is being swung at. So the hook takes the attacker **and** the target. One call site, folded in with `combined` so a PC who would have had Advantage comes out even. The Weaponmaster's *Goading Strike* in a later batch is the same shape and will reuse it
- **Content can override the type its holder's standard attack deals** — `content/registry.py` → `standard_damage_type`, `standard_attack_damage_type`; `adversaries/adversary.py` → `type_of_damage`. The Spellblade's *Arcane Steel* is the only user. Asked only where nothing was stated, the same discriminator `standard_damage` uses for dice, so a feature that prints its own type is never touched — the Construct's Death Quake stays magic out of a physical stat block
- **A defeated adversary can be a spotlight candidate** — `content/registry.py` → `spotlight_while_defeated`, `spotlights_while_defeated`; `combat/fight.py` → `_next_adversary`. Until the Skeleton Warrior, the GM's list of candidates was simply `living_adversaries`, and nothing could reach a combatant that was down. `Won't Stay Dead` needs a spotlight to roll the d6 that brings it back, so the hook exists to say "this one is still on the GM's list". It grants **permission only**: the activation is charged and capped exactly like any other, and a defeated adversary still cannot be targeted, still counts for nothing toward victory, and is never picked unless something it carries answers True. One hook, one call site, and for every other stat block the answer is False and the list is what it always was
