# SRD domain cards: what's ported

The SRD prints **189 domain cards** - nine domains of 21 each, three at level 1
and two at every level from 2 to 10. This file tracks which of them the simulator
runs, for the reason `adversaries/PORTED.md` exists: without a list there is no
way to tell a card nobody has got to from a card that isn't in the book.

**It matters more here than it does for adversaries.** A card only reaches the
coverage block if some character sheet names it, because coverage answers "how
much of *this character* do we run?". A card no PC carries is not reported as a
gap anywhere - it is simply absent. This file is the only place that gap is
visible.

## Scope

**Levels 1 to 8, all nine domains** - 153 cards, complete. That is every card a
level 8 party of any class combination could hold, so a new party composition can
be simulated without writing code first. What is left of the SRD is levels 9 and
10.

The scope grew from levels 1-2, then to 3, then to 4, then to 5, then to 6, then
to 7, then to 8, each time the previous one was finished. Cards are ported
**by level** rather than by domain: a level is the slice a party actually
occupies, and finishing one means no loadout at that level can name a card nobody
has written.

## How porting works

The same process the adversary port settled on, and for the same reasons:

- **Batches of about five cards.** One domain's level 1-2 slice was exactly five,
  so a batch was a domain. A *level* is only two cards per domain, so a level 3
  batch is two or three domains instead. The size is what matters - five or six
  cards is one hand-over of rulings and one round of review.
- **Card text is taken from `.reference/abilities.json` and checked against the
  printed page** in the SRD PDF before the batch lands. The domain sections start
  at printed page **118**. The PDF renders two printed pages per sheet, so PDF
  page `n` shows printed `2n-2` and `2n-1` - to reach printed page `p`, read PDF
  page `(p + 2) / 2`. **Confirmed**: Arcana 119, Blade 121, Bone 122-123,
  Codex 124, Grace 126, Midnight 128, Sage 130, Splendor 132, Valor 134 - every
  domain now read at least once. Adversaries are printed 80-100, equipment 50-53.
  A domain's whole 1-10 range fits on one or two printed pages, so checking a
  domain once covers every level of it.
- **Mechanics are implemented; usage policies are ruled on.** What the card does
  is read off the page and written. *When a player would actually use it* is a
  judgement about the game and belongs to the user - handed over as a table
  before the code is written, never invented and quietly recorded as settled.
  Until a ruling, the placeholder is "fires whenever its cost can be paid", and
  it is labelled `USAGE POLICY - awaiting a ruling` in the docstring.
- **Dismissals are the user's call too.** A card with no combat effect and a card
  nobody has written are different states (see `content/registry.py`), and only
  the user decides which one a card is in.
- **Check for tests that used the batch's cards as examples of *unimplemented*.**
  Porting a card turns any such test red, and it has happened twice - Rune Ward
  was standing in for "nobody has written this" in both `tests/test_coverage.py`
  and `tests/test_name_matching.py`. Those now use made-up names; if a new one
  appears, fix the example rather than the assertion.

Cards are more policy-heavy than adversary features: nearly every one costs Hope
or Stress, and choosing to spend those *is* the decision the simulator is
measuring. Expect a longer ruling table per batch than the adversary batches had.

## Levels 1-2

✅ modelled · 🚫 no combat effect · ➖ insignificant · ⏸ out of combat ·
⬜ not implemented

| Domain | Level 1 | Level 2 |
|---|---|---|
| **Arcana** | ✅ Rune Ward · ✅ Unleash Chaos · 🚫 Wall Walk | ✅ Cinder Grasp · 🚫 Floating Eye |
| **Blade** | ✅ Get Back Up · ✅ Not Good Enough · ✅ Whirlwind | ⏸ A Soldier's Bond · ✅ Reckless |
| **Bone** | ➖ Deft Maneuvers · ➖ I See It Coming · 🚫 Untouchable | ✅ Ferocity · ✅ Strategic Approach |
| **Codex** | ✅ Book of Ava · ✅ Book of Illiat · ✅ Book of Tyfar | ✅ Book of Sitil · 🚫 Book of Vagras |
| **Grace** | 🚫 Deft Deceiver · ✅ Enrapture · ⏸ Inspirational Words | 🚫 Tell No Lies · ✅ Troublemaker |
| **Midnight** | 🚫 Pick and Pull · ✅ Rain of Blades · 🚫 Uncanny Disguise | ✅ Midnight Spirit · ✅ Shadowbind |
| **Sage** | 🚫 Gifted Tracker · 🚫 Nature's Tongue · ✅ Vicious Entangle | ✅ Conjure Swarm · ✅ Natural Familiar |
| **Splendor** | ✅ Bolt Beacon · ⏸ Mending Touch · ✅ Reassurance | 🚫 Final Words · ✅ Healing Hands |
| **Valor** | 🚫 Bare Bones · ✅ Forceful Push · ✅ I Am Your Shield | ✅ Body Basher · ✅ Bold Presence |

**31 modelled, 13 no effect, 2 insignificant, 3 out of combat, 0 outstanding.**

**Levels 1 and 2 are complete across all nine domains.** Every card a level 2
party of any class combination could hold is either running or assessed, and
nothing in the slice is in the *unimplemented* state.

The card counts hide how much is in a Codex card: the five books hold fifteen
spells between them, of which six change a fight. A book counts once in the
table above and its spells are declared individually.

## Level 3

| Domain | Level 3 |
|---|---|
| **Arcana** | ✅ Counterspell · 🚫 Flight |
| **Blade** | ✅ Scramble · ✅ Versatile Fighter |
| **Bone** | ✅ Brace · ✅ Tactician |
| **Codex** | ✅ Book of Korvax · ✅ Book of Norai |
| **Grace** | ✅ Hypnotic Shimmer · ✅ Invisibility |
| **Midnight** | ✅ Chokehold · ✅ Veil of Night |
| **Sage** | ✅ Corrosive Projectile · ✅ Towering Stalk |
| **Splendor** | ✅ Second Wind · ✅ Voice of Reason |
| **Valor** | ✅ Critical Inspiration · ✅ Lean on Me |

**17 modelled, 1 no effect, 0 outstanding.**

**Levels 1 to 3 are complete across all nine domains.** Every card a level 3
party of any class combination could hold is either running or assessed, and
nothing in the slice is in the *unimplemented* state. Batches 7 (Arcana, Blade,
Bone), 8 (Valor, Splendor, Sage) and 9 (Codex, Grace, Midnight) between them
cover eighteen cards - twenty-one things, since the two level 3 Codex entries are
Grimoires holding five spells between them.

## Level 4

| Domain | Level 4 |
|---|---|
| **Arcana** | 🚫 Blink Out · ✅ Preservation Blast |
| **Blade** | ✅ Deadly Focus · 🚫 Fortified Armor |
| **Bone** | ✅ Boost · ✅ Redirect |
| **Codex** | ✅ Book of Grynn · ✅ Book of Exota |
| **Grace** | ⏸ Soothing Speech · 🚫 Through Your Eyes |
| **Midnight** | ✅ Glyph of Nightfall · 🚫 Stealth Expertise |
| **Sage** | ✅ Death Grip · ✅ Healing Field |
| **Splendor** | 🚫 Divination · ✅ Life Ward |
| **Valor** | ✅ Goad Them On · ✅ Support Tank |

**12 modelled, 5 no effect, 1 out of combat, 0 outstanding.**

**Levels 1 to 4 are complete across all nine domains** - 81 cards. Every card a
level 4 party of any class combination could hold is either running or assessed,
and nothing in the slice is in the *unimplemented* state. Batches 10 (Arcana,
Blade, Bone, Codex), 11 (Grace, Midnight), 12 (Sage) and 13 (Splendor, Valor)
cover the eighteen, and the batch size shrank as it went because the rulings per
card grew.

**Grace is the first domain whose whole level reaches no fight**, and the two
cards land in different states, which is most of why the states exist: Soothing
Speech is a real heal that happens during a rest, and Through Your Eyes is
scouting. Filing the first as *no combat effect* would have lost the difference.

## Level 5

| Domain | Level 5 |
|---|---|
| **Arcana** | ✅ Chain Lightning · ✅ Premonition |
| **Blade** | ✅ Champion's Edge · 🚫 Vitality |
| **Bone** | 🚫 Know Thy Enemy · ✅ Signature Move |
| **Codex** | 🚫 Manifest Wall · 🚫 Teleport |
| **Grace** | ✅ Words of Discord · 🚫 Thought Delver |
| **Midnight** | ✅ Hush · 🚫 Phantom Retreat |
| **Sage** | ✅ Thorn Skin · ✅ Wild Fortress |
| **Splendor** | ✅ Smite · 🚫 Shape Material |
| **Valor** | ✅ Rousing Strike · ⏸ Armorer |

**11 modelled, 7 no effect, 1 out of combat, 0 outstanding.**

**Levels 1 to 5 are complete across all nine domains** - 99 cards. Every card a
level 5 party of any class combination could hold is either running or assessed,
and nothing in the slice is in the *unimplemented* state. Batches 14 (Arcana,
Blade), 15 (Bone, Codex), 16 (Grace, Midnight) and 17 (Sage, Splendor, Valor)
cover the eighteen.

**Level 5 dismisses more than any level below it.** Seven of the eighteen reach no
fight, where levels 1 to 4 together dismissed nineteen out of eighty-one. Nearly
all of them are repositioning or information, which is the same pair of reasons
that has always driven dismissals - what is new is only how many of them one level
holds.

## Level 6

| Domain | Level 6 |
|---|---|
| **Arcana** | 🚫 Rift Walker · ✅ Telekinesis |
| **Blade** | ✅ Battle-Hardened · ✅ Rage Up |
| **Bone** | ✅ Rapid Riposte · ⏸ Recovery |
| **Codex** | ✅ Sigil of Retribution · ✅ Banish |
| **Grace** | ✅ Never Upstaged · ✅ Share the Burden |
| **Midnight** | 🚫 Dark Whispers · 🚫 Mass Disguise |
| **Sage** | ⏸ Conjured Steeds · ⏸ Forager |
| **Splendor** | ✅ Restoration · ✅ Zone of Protection |
| **Valor** | ✅ Inevitable · ✅ Rise Up |

**12 modelled, 3 no effect, 3 out of combat, 0 outstanding.**

**Levels 1 to 6 are complete across all nine domains** - 117 cards. Batches 18
(Arcana, Blade, Bone), 19 (Codex, Grace, Midnight) and 20 (Sage, Splendor, Valor)
cover the eighteen.

**Two whole domains reach no fight at this level, in two different ways.**
Midnight is the second domain after Grace's level 4 to have both its cards
dismissed - Dark Whispers is a conversation and four questions for the GM, Mass
Disguise needs minutes of silence and pays out in Presence Rolls, and neither
would buy anything once encounters are sequenced either. **Sage is the first
domain with a whole level *out of combat***, which is the opposite claim: both of
its cards are real and representable and simply happen between fights, so they
are on the sequenced-encounter list rather than dismissed. Level 6 has three
cards in that state, which is more than any other level.

## Level 7

| Domain | Level 7 |
|---|---|
| **Arcana** | ✅ Arcana-Touched · ✅ Cloaking Blast |
| **Blade** | ✅ Blade-Touched · ✅ Glancing Blow |
| **Bone** | ✅ Bone-Touched · ✅ Cruel Precision |
| **Codex** | ✅ Codex-Touched · 🚫 Book of Homet |
| **Grace** | ✅ Grace-Touched · 🚫 Endless Charisma |
| **Midnight** | ✅ Midnight-Touched · ✅ Vanishing Dodge |
| **Sage** | ✅ Sage-Touched · ✅ Wild Surge |
| **Splendor** | ✅ Splendor-Touched · ✅ Healing Strike |
| **Valor** | ✅ Valor-Touched · ✅ Shrug It Off |

**16 modelled, 2 no effect, 0 outstanding.**

**Levels 1 to 7 are complete across all nine domains** - 135 cards. Batches 21
(Arcana, Blade, Bone), 22 (Codex, Grace, Midnight) and 23 (Sage, Splendor, Valor)
cover the eighteen.

**Every domain prints an *X*-Touched card at this level**, gated on holding four
or more cards of that domain, and all nine are now in. The user's ruling is that
carrying the card is proof of the loadout (SIMULATION-RULES.md), so none of them
counts anything - and between them they reach more separate hooks than any other
single level: a Spellcast bonus, an attack bonus, a trait doubling, a damage
bonus, a Fear conversion, an outright negation, two resource substitutions and an
Armor Slot refund.

**Level 7 cost the most machinery of any level.** Batch 21 added
`action_roll_advantage`, `spellcast_bonus`, `attack_failed` and
`Condition.untargetable`; batch 22 added `stress_instead_of_hp`,
`armor_instead_of_stress`, `fear_conversion` and the attack roll on `damage_pool`;
batch 23 added **the rolled trait**, threaded into `roll_duality` and through
`roll_bonus` for Sage-Touched, and **whether an Armor Slot was marked**, added to
`on_damaged` for Valor-Touched. Both of the last two are facts the hooks could not
previously see rather than new hooks, which is the cheaper shape when it is
available.

**Every domain prints an *X*-Touched card at this level**, gated on holding four
or more of that domain's cards in the loadout - so nine of the eighteen turn on
the same question. The user ruled that carrying the card is taken as proof of the
loadout rather than counting it (SIMULATION-RULES.md §1), which means the
remaining three domains inherit an answer rather than each needing one.

**Six of the six Touched cards so far are partial**, and always for the same
reason: each prints a list of bonuses, and at least one entry in every list is a
number a character sheet already carries. Blade's Severe threshold, Bone's
Agility, Codex's vault swap - the pattern is the level's, not any one card's.

## Level 8

| Domain | Level 8 |
|---|---|
| **Arcana** | ✅ Arcane Reflection · ✅ Confusing Aura |
| **Blade** | ✅ Battle Cry · ✅ Frenzy |
| **Bone** | ✅ Breaking Blow · 🚫 Wrangle |
| **Codex** | 🚫 Book of Vyola · ⏸ Safe Haven |
| **Grace** | 🚫 Astral Projection · ✅ Mass Enrapture |
| **Midnight** | 🚫 Shadowhunter · ✅ Spellcharge |
| **Sage** | ✅ Forest Sprites · ✅ Rejuvenation Barrier |
| **Splendor** | ✅ Shield Aura · ✅ Stunning Sunlight |
| **Valor** | ✅ Full Surge · ✅ Ground Pound |

**13 modelled, 4 no effect, 1 out of combat, 0 outstanding.**

**Levels 1 to 8 are complete across all nine domains** - 153 cards. Batches 24
(Arcana, Blade, Bone), 25 (Codex, Grace, Midnight) and 26 (Sage, Splendor, Valor)
cover the eighteen. Codex's *Book of Vyola* is a Grimoire and carries two spells,
so its one card is three declarations.

**Level 8 is where the domains stop being defensive about the same thing.** Six
of the eighteen answer an incoming attack and each does it differently - reflect
it, wear it down a layer at a time, shrug the armor off and take it, put a
barrier up, thicken an aura, or simply be harder to see. The last of those,
Midnight's *Shadowhunter*, is the one that turned out not to be an answer at all
here: it is gated on darkness, and the simulator holds no fact about where a
fight happens.

**It is also the level that filled in the party's side of the hook table.** Five
of the eighteen give their whole effect to somebody else, and between them they
cost four party-wide twins of hooks that had only ever been holder-scoped:
`ally_attack_advantage` (Battle Cry), `ally_roll_bonus` and
`ally_extra_armor_slot` (Forest Sprites), and `ally_severity_response` (Shield
Aura). Before this level the party could ward an ally's damage and add dice to
their attack, and could do nothing about their roll, their armor or their
thresholds.

**It dismisses four**, and no two for the same reason. Wrangle and Astral
Projection are position and remote sensing, the two oldest reasons in the file.
Shadowhunter is a trigger with no representation, the Gifted Tracker reading.
*Shared Clarity* inside the Book of Vyola is the new one, and it is worth reading
carefully: the user's ruling is that what it changes has no representation in an
outcome, because the effect is **symmetrical** - a pooled pair still marks the
same total Stress, and all the card decides is which of the two tracks fills
first.

### Order it was done in



The five domains the Immareth sheets already draw from first - **Blade, Codex,
Sage, Splendor, Valor**, 14 cards - so every card landing was a loadout the
current party could actually swap to. Then the four that had no module at all:
**Arcana, Bone, Grace, Midnight**.

### What's next

**Levels 1 to 8 are complete across all nine domains** - 153 cards, so every card
a level 8 party of any class combination could hold is either running or assessed.
What remains of the SRD is **levels 9 and 10**, thirty-six cards, and both sit on
the pages every batch has already read.

Worth knowing before picking them up, from a read of those pages during batch 24:
level 9 and 10 print the domains' capstones, and several are shaped like
machinery that does not exist. Blade's *Battle Monster* and Valor's *Unbreakable*
both reach a **death move**, which `death_move_ward` already covers; Codex's
*Disintegration Wave* kills outright rather than dealing damage, which nothing
does; Grace's *Copycat* mimics **another player's card**, which would need a
loadout that can be read across the party; and Sage's *Force of Nature* is a
second Frenzy-shaped transformation, so the condition machinery built at level 8
should carry it.

Level 8 cost more machinery than any level since 7, and all of it in one
direction - four party-wide twins plus two facts on existing hooks
(`damage_type` on `on_damaged`, and `denies_armor` on `Condition`) plus the
trait-bonus record on `PlayerCharacter`.

One thing batch 18 surfaced that is not a domain card: **secondary weapons do not
exist in the simulator**, so *Paired* and dual wielding contribute nothing to
anybody's damage. The gap is now written out in `SIMULATION-RULES.md` §3, and
Rapid Riposte is built so the bonus reaches it for free when it lands.

### What the modelled ones cover

Every ✅ above is registered with a hook and runs. Several are partial and
declare their gaps where they're registered (`unmodelled=[...]`), which reaches
the coverage report - Whirlwind's range band, I Am Your Shield's armor slots,
Healing Hands' Stress option. The two Grimoires carry three spells each;
Telepathy inside the Book of Illiat is separately dismissed as having no combat
effect.

## Batches

### Batch 1 — Blade and Valor (5 cards)

Both domains finished. Five rulings came back; the policies are in
`SIMULATION-RULES.md` §1 and the interpretations in §2.

| Card | Hook | Ruling |
|---|---|---|
| **Not Good Enough** (Blade 1) | `damage_die_reroll` | None needed - no cost, no limit, so optimal play rerolls every 1 and 2. Each die gets **one** fresh throw |
| **Reckless** (Blade 2) | `attack_advantage` | Marks the Stress whenever the shared last-slot rule allows |
| **A Soldier's Bond** (Blade 2) | — | **Out of combat.** Used between encounters, not during one |
| **Forceful Push** (Valor 1) | `action` + `extra_damage` | Spends its Hope on every successful hit, skipping a target already Vulnerable or one the hit just killed |
| **Bold Presence** (Valor 2) | `condition_refusal` | The condition dodge is modelled; the Hope-for-Strength clause is declared a gap, ruled an insignificant effect |

Four pieces of shared machinery came out of it:

- **A fifth content state, `out_of_combat_ability`.** Real effect, used between
  fights. Not a dismissal - it is the to-do list for when encounters are
  sequenced. `content/registry.py`, printed by `simulation/coverage.py`.
- **`PlayerCharacter.will_spend_stress`** - one rule for every PC Stress cost:
  freely, except the last slot, which waits for 2 or fewer unmarked HP. **Get
  Back Up and Conjure Swarm's beetles were retrofitted onto it** and both change
  behaviour slightly; the rows in `SIMULATION-RULES.md` say how.
- **`damage_die_reroll`** - the first hook that reaches individual dice *after*
  they are rolled. The three existing damage hooks all run before the throw.
- **`condition_refusal`** - stops a condition landing at all, deliberately
  separate from `immunity`, which suppresses one that is still there.

Two smaller changes: a PC's weapon swing now consults `granted_attack_advantage`
the way an adversary's standard attack always has (`items/weapons.py`), and
`FightState.apply_condition` asks whether the condition is refused.

**Verified late, and now complete.** Card text came from
`.reference/abilities.json` only when this batch landed. Blade's page was read in
batch 7 (SRD p. 121) and Valor's in batch 8 (p. 134), since both batches needed
those pages anyway. All five match.

### Batch 2 — Codex (3 cards, 9 spells)

The domain is finished. **Verified against the printed page** (SRD pp. 124-125):
all nine spells match `.reference/abilities.json` word for word.

Two spells changed a fight and seven didn't:

| Spell | Book | Disposition |
|---|---|---|
| **Wild Flame** | Tyfar 1 | Modelled. One roll against up to three adversaries in Melee, each checked against its own Difficulty; 2d6 magic **and a forced Stress** on every one it beats |
| **Parallela** | Sitil 2 | Modelled. 2 Hope, hung on an ally; their next landing attack also hits a second adversary its roll would beat, at full damage |
| Magic Hand, Mysterious Mist | Tyfar 1 | No combat effect |
| Adjust Appearance, Illusion | Sitil 2 | No combat effect |
| Runic Lock, Arcane Door, Reveal | Vagras 2 | No combat effect - and so is the **book**, which is declared under its own name. A Grimoire with no spell registered would report the card as unimplemented |

**Wild Flame is the first PC card that marks an adversary's Stress**, which is
the resource its Action features are paid from and the one its desperation rule
reads. Worth watching what that does to how often a stat block gets to use its
features.

**Reveal was the one worth arguing about.** The simulator models Hidden and the
Jagged Knife Shadow's *Cloaked* deliberately prints no way to be found, so
reading "anything magically hidden" as reaching creatures would have handed the
party a no-cost answer to it. Ruled to find objects instead.

One piece of shared machinery: **`ally_on_hit`**, the first party-wide on-hit
hook. `on_hit` is holder-scoped, which is right for Whirlwind and wrong for a
spell one PC hangs on another - holder-scoping Parallela would have meant it only
ever worked cast on yourself, which is the one target the user ruled out. Called
from `combat/policy.py` beside `apply_on_hit`.

### Batch 3 — Sage and Splendor (6 cards)

Both domains finished, and with them every domain the Immareth sheets draw from.
**Verified against the printed page** (SRD pp. 130 and 132).

| Card | Disposition |
|---|---|
| **Bolt Beacon** (Spl 1) | Modelled. Proficiency d8+2 magic at a target, leaving it Vulnerable. Declines without a Hope - the Hope is what sends the bolt, not an upgrade to it |
| **Reassurance** (Spl 1) | Modelled. Once per rest, rerolls any failed roll by an **ally**. The card's own trigger, so no floor of any kind |
| **Natural Familiar** (Sage 2) | Modelled. A Hope to summon; its d6 rides an attack when the area rule says the familiar is beside that adversary |
| **Mending Touch** (Spl 1) | **Out of combat** - gated on "a few minutes to focus", so it runs when sequenced encounters do. The second card in that state |
| **Gifted Tracker** (Sage 1) | No combat effect. The +1 Evasion is real and representable, but it applies only against creatures the party tracked and nothing records that they did |
| **Final Words** (Spl 2) | No combat effect |

**No new machinery.** Natural Familiar's positional half is answered by
`chance_within`, which already existed for exactly this shape of question, and
Reassurance is the second registrant on the `reroll` hook after Luckbender.

Worth knowing about **Gifted Tracker**: the dismissal rests on the *trigger*
having no representation, not on the effect being small. Modelling it as always
on, and as a flag on the encounter, were both offered and declined - so if
encounters ever grow a "the party tracked these" field, this is the card waiting
for it.

Splendor now has a third copy of the `_spellcast` helper that Codex and Sage each
carry, and the three have already drifted once (Codex's grew a `difficulty`
parameter this session). Worth pulling into one place. *(Done - see "Consolidating
`_spellcast`" at the end.)*

### Batch 4 — Arcana (5 cards)

The first of the four domains with no module at all. **Verified against the
printed page** (SRD p. 119, where the Domain Card Reference appendix begins).

| Card | Disposition |
|---|---|
| **Rune Ward** (1) | Modelled. Held by the frailest ally, who spends a Hope to take 1d8 off an incoming hit; a Ward Die of 8 burns it out for the rest of the fight |
| **Unleash Chaos** (1) | Modelled. Every token on every cast for that many d10s, refilled with a Stress when the shared rule allows |
| **Cinder Grasp** (2) | Modelled. 1d20+3 magic and **On Fire**, which now burns for 2d6 every time its holder acts |
| **Wall Walk**, **Floating Eye** (1, 2) | No combat effect - movement and information |

Two pieces of shared machinery, and both closed a real gap rather than serving
one card:

- **`ally_damage_reduction`** - the first hook that reaches the **damage number**
  itself. An Armor Slot and `severity_response` both work in threshold bands and
  `damage_multiplier` can only scale, so "reduce incoming damage by 1d8" could
  not be expressed at all. It lands after any resistance and before the
  thresholds, which is what lets a ward drop a hit a whole band or take it away
  entirely. Party-wide, like `ally_on_hit`, because the ward is held by somebody
  other than the PC whose card it is. An adversary that reduces its own incoming
  damage (the Fallen Warlord's *Faltering Armor*) will want a holder-scoped twin.
- **`WHEN_THEY_ACT` is now announced on both sides of the table**, and for
  *effects* as well as expiry. It had only ever reached a PC's conditions, and
  only to end them - which was fine while no condition did anything when its
  holder acted. On Fire is the first that does.

**On Fire is the one condition that arrived with its own mechanic.** Every other
condition in the simulator had to be ruled on because the SRD gives it a name and
nothing else; Cinder Grasp prints the burn on the card. It lasts until the GM
pays a Fear, so the card poses the GM a question that costs them either way.

### Batch 5 — Bone (5 cards)

Bone is the Evasion domain, and that turned out to be the whole story of the
batch. **Verified against the printed page** (SRD p. 122).

| Card | Disposition |
|---|---|
| **Ferocity** (2) | Modelled. 2 Hope after a landed hit buys Evasion equal to the HP it marked, spent on the next attack that comes in |
| **Strategic Approach** (2) | Modelled. A token per adversary, always buying the d8; empty if the party took no long rest |
| **Untouchable** (1) | No combat effect - a sheet carries Evasion resolved, so running it would count it twice |
| **Deft Maneuvers** (1) | Insignificant - +1 on one attack roll, once per rest |
| **I See It Coming** (1) | Insignificant - the Wings ruling, and it is the **larger** of the two |

One piece of shared machinery: **`evasion_bonus`**. Evasion was a fixed number
until this batch - a sheet carries it resolved and `Adversary.attack` read it
straight off - so nothing could change it once a fight had started. Asked once
per attack and outside the reroll closure, because Ferocity's bonus lasts only
"until after the next attack made against you" and asking twice would spend it
twice. Area attacks don't consult it, which is declared as a gap.

**Three of these five are about not being hit, and only one is modelled.** Worth
knowing why they split the way they did, because the reasons are all different:
Untouchable is already in the sheet's number, I See It Coming asks the holder to
decide against a roll they cannot see, and Ferocity asks them to decide off their
own landed hit - which is why it is the one that runs.

### Batch 6 — Grace and Midnight (10 cards)

The last two domains, taken together to finish the slice. **Verified against the
printed page** (SRD pp. 126 and 128).

| Card | Disposition |
|---|---|
| **Enrapture** (Gr 1) | Modelled. The target's attacks are fixed on the caster until the GM pays a Fear, plus a once-per-rest Stress forced on them |
| **Troublemaker** (Gr 2) | Modelled. A **Presence** Roll - the only action card that rolls a named trait rather than Spellcast - forcing Stress equal to the highest of Proficiency d4s |
| **Rain of Blades** (Mid 1) | Modelled. The Fire Flies shape, declining below two targets, with the Vulnerable rider rolled **per target** |
| **Midnight Spirit** (Mid 2) | Modelled. A Hope, then Spellcast-trait d6s of magic; summon and attack are one action |
| **Shadowbind** (Mid 2) | Modelled. Restrains everything it beats - which here means one Fear per adversary for the GM to undo |
| **Inspirational Words** (Gr 1) | Out of combat - the third card in that state |
| **Deft Deceiver**, **Tell No Lies**, **Pick and Pull**, **Uncanny Disguise** | No combat effect - social and exploration rolls the simulator never makes |

One piece of shared machinery: **`adversary_target_override`**, the exact mirror
of the `party_target_override` a Weaponmaster's Taunt uses. Kept as two hooks
rather than merged into one, because a single hook would let party content compel
a PC, which nothing should.

**Two cards are worth reading the numbers of carefully.** Enrapture is the first
party card whose point is *being attacked* - it moves danger onto its caster - and
Shadowbind's entire effect turns out to be the GM's Fear pool, since Restrained
does nothing by itself here. Neither is what the page appears to promise, and
both follow from rulings made long before the cards.

`_spellcast` is now duplicated across six modules and has drifted in three
directions (a `bonus`, a `difficulty`, a `trait`). Consolidating it is a small
mechanical change and should be its own, since it touches every one of them and
one test patches `roll_duality` through a module that would stop calling it.
*(Done - see "Consolidating `_spellcast`" at the end.)*

### Batch 7 — Arcana, Blade and Bone at level 3 (6 cards)

The first level 3 batch, and the one that cost the most outside the cards
themselves. **Verified against the printed page** (SRD pp. 119, 121 and 123) -
which also closed batch 1's outstanding check, since Blade's whole domain is on
p. 121.

| Card | Disposition |
|---|---|
| **Scramble** (Bl 3) | Modelled. Once per rest, the first incoming hit of the fight is avoided **entirely** - the whole damage is returned, so no Armor Slot is spent either |
| **Versatile Fighter** (Bl 3) | Modelled. A Stress buys the top face of one damage die, always the die furthest from its own maximum. The trait clause is declared a gap - it is authored in the weapon catalogue |
| **Brace** (Bo 3) | Modelled. A Stress marks a second Armor Slot, but only where that slot would actually save an HP |
| **Tactician** (Bo 3) | Modelled, partial. Lends the holder's best Experience to an ally they are helping. Its Tag Team clause is a declared gap |
| **Counterspell** (Ar 3) | Modelled. Interrupts one incoming **magic-damage** hit party-wide on a Spellcast Reaction Roll, then vaults itself - and buys itself back for its printed Recall Cost in Stress |
| **Flight** (Ar 3) | No combat effect - nothing represents a PC being off the ground |

**Help an Ally was built first, as its own piece of work.** Tactician has no
trigger without it, and it turned out not to be a gap in the *dice* at all:
`roll_duality` has taken `help_dice` since it was written, resolving to the
single best die and correctly refusing to cancel against Disadvantage. Nothing
had ever called it. So the move now lives in `content/help.py` and is asked at
every action-roll site - a weapon swing, all six `_spellcast` helpers, Healing
Hands, and the search for a hidden adversary. It is in `content/` rather than the
turn policy because helping is a reaction to somebody else's roll, and because
several of those call sites are domain cards.

Three pieces of shared machinery, each closing a real gap:

- **`help_bonus`** - holder-scoped on the **helper**, which is what makes it a
  hook rather than a use of `roll_bonus`: the Experience being lent belongs to
  somebody other than the roller.
- **`damage_die_maximum`** - the neighbour of `damage_die_reroll`, and kept
  separate from it on purpose. A reroll is a gamble and a maximum is a purchase,
  and content paying a Stress has to know what it bought. Dispatch offers the
  dice worst-first and stops at the first one claimed, so the card always gets
  the largest gain the roll has to give.
- **`extra_armor_slot`** - the first thing that can mark more than the one free
  Armor Slot `take_damage` marks by itself. Asked inside that same branch, which
  is the card's trigger read literally: no first slot, nothing to be additional
  to. So it never reaches direct damage.

Plus one small addition to the fight loop: **`FightState.spotlighted`**, the
adversary taking a spotlight right now. Damage arrives at a PC with no attacker
attached - `take_damage` carries an amount and a type - and Counterspell needs
the attacker's Difficulty to roll against. Threading an attacker through
`take_damage` would have changed that signature on both sides of the table and in
every stand-in, so the fight carries it instead, exactly as it already carries
`acting_free`. A `None` there is meaningful: the magic is the party's own.

**Counterspell is the first card to model the vault.** It puts itself there as
its own printed cost, so without a way back it would be a one-shot; the ruling is
that it alone buys itself back for its Recall Cost of 2 Stress. No other card
gains a recall, and the state is a token on the caster rather than machinery
anything else can reach.

`EXPERIENCE_HOPE_FLOOR` moved from `combat/policy.py` to `content/rolls.py`,
because helping reads the same number and `content/` may not import `combat/`.
The rule it states is unchanged.

### Batch 8 — Valor, Splendor and Sage at level 3 (6 cards)

**Verified against the printed page** (SRD pp. 130, 132 and 134). Page 134 also
closed the **last** of batch 1's outstanding check: Bare Bones, Forceful Push, I
Am Your Shield, Body Basher and Bold Presence all match. Every ported card is now
checked against the print except the level 3 half of Codex, Grace and Midnight,
which batch 9 will read.

| Card | Disposition |
|---|---|
| **Critical Inspiration** (Val 3) | Modelled. Once per rest, a critical attack clears a Stress on each ally in Very Close - or hands them a Hope if they have none marked |
| **Lean on Me** (Val 3) | Modelled. Once per long rest, an ally's failed roll clears 2 Stress on both of them, and only when both have 2 to clear |
| **Second Wind** (Spl 3) | Modelled. Once per rest, a landed attack clears 3 Stress or an HP; on a success with Hope, the same for one ally in Close |
| **Voice of Reason** (Spl 3) | Modelled. +1 Proficiency on weapon damage while every Stress slot is marked. The social clause is a declared gap |
| **Corrosive Projectile** (Sage 3) | Modelled. Proficiency d6+4 magic, plus 2 Stress to take a permanent point off the target's Difficulty |
| **Towering Stalk** (Sage 3) | Modelled. Once per rest, a Stress buys a Close-band area attack for Proficiency d8 physical |

One piece of shared machinery, and one change to an existing dispatch:

- **`ally_on_roll`** - the party-wide mirror of `on_roll`. Nothing let a PC
  respond to *another* PC's roll except by rerolling it, and `reroll` could not
  be borrowed: its contract is that the first offer wins and the rest are never
  asked, so content that only wanted to watch would have to decline with side
  effects. Watching and rewriting stay apart, exactly as `on_party_attack_roll`
  and `convert_party_roll` do on the GM's side.
- **`adjust_damage_pool` is now asked holder-wide as well as weapon-scoped**, the
  way `total_roll_bonus` already was. Until this, a *card* could not change the
  shape of a damage roll at all - only a weapon feature could - which is what
  Voice of Reason needs, since +1 Proficiency is one more of the weapon's own
  dice rather than a die of its own. Holder first, so a Massive discard sees the
  bumped pool.

**Corrosive Projectile is the first card that moves an adversary's Difficulty.**
It writes the new number into the spawned stat block rather than carrying a
condition, which is where `Flying (X)` already resolves and for the same reason -
Difficulty is read in four places that have no fight to dispatch with. The card
says *permanently*, so nothing needs an ender, and stacking comes for free.

**Valor needed no change when Help an Ally landed**, which is worth recording
because it looks like an omission: the domain has no Spellcast Roll anywhere in
its first three levels. Forceful Push attacks through `items/weapons.py`, which
asks for help on the party's behalf, and its other cards are a damage bonus, a
guard, an `extra_damage` rider and a condition refusal.

### Batch 9 — Codex, Grace and Midnight at level 3 (6 cards, 8 spells)

The last of level 3. **Verified against the printed page** (SRD pp. 124-125, 126
and 128). Every ported card is now checked against the print.

| Spell or card | Disposition |
|---|---|
| **Rune Circle** (Korvax) | Modelled. A Stress, **no roll**, 2d12+4 magic to everything the Melee band holds. "Or who enter Melee range" is a declared gap |
| **Mystic Tether** (Norai) | Modelled. Restrained plus a forced Stress; the Restrain costs the GM a Fear to clear and does nothing else |
| **Fireball** (Norai) | Modelled. Proficiency d20+5 magic on a Reaction Roll (13), half on a success, nothing on a critical - and it catches **PCs** standing near the target |
| **Hypnotic Shimmer** (Gr 3) | Modelled. Once per rest, an area Spellcast that **Stuns** and forces a Stress |
| **Invisibility** (Gr 3) | Modelled. A Stress hides the frailest conscious PC for Spellcast-trait actions |
| **Chokehold** (Mid 3) | Modelled. A Stress, **no roll**, Vulnerable on the focus target - and 2d6 for anybody who attacks it |
| **Veil of Night** (Mid 3) | Modelled. Hidden plus Advantage on the caster's next attack |
| **Levitation**, **Recant** (Korvax) | No combat effect - repositioning and memory |

**Two conditions landed, and that completes the SRD's list.** *Stunned* was the
last one with no representation here at all, and *Invisible* is Hidden's second
name. Both were modelled for On Fire's reason and it is worth saying plainly,
because it is the third time it has decided a card: **a condition whose card
prints its own mechanic needs no ruling.** Every other condition here had to be
ruled on because the book gives it a name and nothing else.

A Stunned adversary loses its activation *and* the Fear that bought it. That is
read off `Condition.prevents_action` through `combat/state.py` → `cannot_act`, so
the fight loop never learns the word - and a second condition that stopped
somebody acting would need no change at all.

One piece of shared machinery:

- **`ally_extra_damage`** - dice a PC's content adds to *anybody's* attack.
  Chokehold says "when **a creature** attacks a target who is Vulnerable in this
  way", which the holder-scoped `extra_damage` cannot express: registered there
  it would have been a card that helps nobody but its owner. The same argument
  that gave Parallela `ally_on_hit`, arriving at damage instead of on-hit.

**Fireball is the first party spell that can hurt the party.** "All creatures
within Very Close range" is read the way the adversary features already read the
same noun - Scorched Earth catches its own allies, Hellfire does not - so an ally
beside the target saves against it too. It is also the first PC Reaction Roll
with no printed trait, ruled to the PC's best.

**Rune Circle and Chokehold both take no roll at all**, which makes them free
abilities: they cost a Stress and don't spend the spotlight's action, so a PC can
use one *and* attack. Rune Circle is the first damage anywhere in the simulator
that no roll can turn away.

`_spellcast` drifted further in this batch - the Grace copy grew a `difficulty`
parameter on top of the `trait` it already had - and was consolidated straight
afterwards. See below.

### Batch 10 — Arcana, Blade, Bone and Codex at level 4 (8 cards, 5 spells)

The first half of level 4, and **four domains rather than three** at the user's
request. **Verified against the printed page** (SRD pp. 119, 121, 123 and 125),
which is a re-read of pages every earlier batch has already used.

| Card | Disposition |
|---|---|
| **Preservation Blast** (Ar 4) | Modelled. One Spellcast Roll against the Melee band, Spellcast-trait d8s + 3 magic to everything it beats. Never declines - the Wild Flame side of that split, since it costs nothing but the roll |
| **Deadly Focus** (Bl 4) | Modelled. Once per rest, one more weapon die against a single adversary until the holder attacks somebody else |
| **Boost** (Bo 4) | Modelled. A Stress vaults off an ally for a weapon swing with Advantage and a d10 riding on it |
| **Redirect** (Bo 4) | Modelled. A failed attack from beyond Melee range is turned into another adversary, on Proficiency d6s finding a 6 and a Stress |
| **Book of Grynn** (Cx 4) | Modelled, partial. *Arcane Deflection* negates a hit outright once per **long** rest; *Wall of Flame* burns the Far band for 4d10+3. *Time Lock* is dismissed |
| **Book of Exota** (Cx 4) | Modelled. *Repudiate* is Counterspell without the vault; *Create Construct* puts a 1 HP combatant into the party |
| **Blink Out** (Ar 4) | No combat effect - a teleport, and no positions are tracked |
| **Fortified Armor** (Bl 4) | No combat effect - a sheet carries its thresholds resolved, so running it would count the +2 twice |

**Create Construct is the largest thing in the batch, and it is not a spell so
much as a combatant.** The user's ruling is that the construct becomes a
temporary party member with 1 HP and thresholds nothing can reach: it takes its
own spotlights, attacks for 2d10+3 on a Spellcast Roll made with its caster's
traits, draws attacks that would otherwise land on a PC, and falls apart to the
first hit that connects. Two consequences follow from being a party member and
both are worth watching in the numbers - a fight is not lost while it stands, and
a GM turn is party size + 1 activations, so summoning one hands the GM an extra
activation each turn. It is deliberately kept **out of the report**, since a 1 HP
combatant in the per-member figures would say something untrue about the party.

Two pieces of shared machinery, and one small change to the turn policy:

- **`attack_missed`** - content on a *target* that responds to an incoming attack
  **failing**. The third moment in an incoming attack and the only one nothing
  announced: `before_attacked` fires before the dice and `on_attacked` once the
  attack has succeeded, and between them they had no way to say "and if it
  doesn't". Both of those are asked from `items/weapons.py`, which only ever sees
  the party swinging; this one is asked from the GM turn. Redirect needs it, and
  a miss is a real trigger in Daggerheart.
- **`FightState.summon_ally`** - the party-side mirror of `summon`. It **rebinds**
  the party list rather than appending to it, which is the whole trick: the loop
  holds the new list and the `FightResult` holds the old one, so the fight sees
  the construct and the report does not.
- **A PC with no weapon is not offered a weapon swing** (`combat/policy.py`).
  Every sheet in `characters/` names one, so nothing changes for a PC; what it
  makes possible is a party member who is not one.

**Deadly Focus is the one card whose hook is a compromise.** "+1 bonus to your
Proficiency" wants both the weapon (for the die's size) and the target (for
"until you attack another creature"), and no hook carries both - `damage_pool`
has the weapon, `extra_damage` has the target. It is registered on
`extra_damage`, reading the die off the holder's equipped weapon, and the two
things that costs are declared as gaps where it registers: the extra die sits
outside a Massive discard, and a card that rolls its own Proficiency dice does
not see the bonus at all.

**Arcane Deflection is the first content limited once per *long* rest by the
user's own instruction** rather than by the page being read that way. Nothing
carries between encounters yet, so today it behaves like any per-rest card; the
distinction is banked for when they run in sequence, which is exactly the case
the ruling was made for.

### Batch 11 — Grace and Midnight at level 4 (4 cards)

**Verified against the printed page** (SRD pp. 126-127 and 128). Grace's level 4
sits on p. 127 rather than p. 126, which is the first time a domain's slice has
crossed the sheet.

| Card | Disposition |
|---|---|
| **Glyph of Nightfall** (Mid 4) | Modelled. A Hope conjures a glyph that takes the caster's Knowledge off the target's Difficulty until the GM pays a Fear |
| **Soothing Speech** (Gr 4) | Out of combat - a Tend to Wounds downtime move, so it runs when sequenced encounters do. The fourth card in that state |
| **Through Your Eyes** (Gr 4) | No combat effect - remote sensing, the Floating Eye case |
| **Stealth Expertise** (Mid 4) | No combat effect - dismissed on its **trigger**, a stealth roll the simulator never makes, and not on the size of its effect |

**No new machinery**, which is the notable thing about the batch: everything
Glyph of Nightfall needed already existed, and it is the first card in a while
that could be written entirely out of parts.

**A temporary Difficulty reduction cost more to write than a permanent one.**
Sage's *Corrosive Projectile* says *permanently*, so it writes the smaller number
into the spawned stat block and nothing has to remember anything - which is where
`Flying (X)` already resolves, and for the reason `difficulty_bonus` gives:
Difficulty is read in four places with no fight to dispatch with. This card says
*temporarily*, so the points have to come back. The answer is a condition whose
**only job is to time it**: it carries no effect at all, the reduction is still
written into the stat block, and the ender restores exactly the number recorded
when the glyph landed. Two consequences worth knowing - the card does not stack
where Corrosive Projectile does, since the standing don't-re-apply rule skips a
target already glyphed; and the condition is applied *before* the Difficulty
moves, so content that refused it can never leave the reduction permanent.

**Stealth Expertise is worth reading the dismissal of carefully**, because the
effect is enormous and the dismissal is not about that. Turning a roll with Fear
into a roll with Hope decides who gains what *and* whether the party keeps the
spotlight; if the trigger were a combat roll this would be one of the biggest
cards in the domain. It is dismissed the way Gifted Tracker was - on the trigger
having no representation, not on the effect being small.

### Batch 12 — Sage at level 4 (2 cards)

One domain, which is where the batches have ended up: level 4's remaining
domains are two cards each and each one carries a real ruling. **Verified against
the printed page** (SRD p. 130).

| Card | Disposition |
|---|---|
| **Death Grip** (Sage 4) | Modelled, partial. A Spellcast Roll, then one of three printed effects, and the target is Restrained either way |
| **Healing Field** (Sage 4) | Modelled. Once per long rest, no roll, everyone in the Close band clears an HP - or 2 for 2 Hope |

**No new machinery.** Both cards are built out of parts that already existed,
which is the second batch running that has been true of.

**Death Grip is the first card that offers a menu**, and that is the whole of what
it cost to rule. Three printed effects, one chosen: a pull, a forced 2 Stress, and
vines catching everything between the caster and the target. The pull is pure
repositioning, so the user's ruling is that **the shuffle picks between the other
two** - Strategic Approach's precedent, where the token always buys the d8
because the other two options cannot be evaluated. The cost of that is declared
as a gap on the card and is worth restating here: a table would sometimes take
the pull, so this card comes out somewhat better in the simulator than it plays.
The vines are only a candidate when they reach somebody, so against a lone
adversary the card always constricts.

"Between you and the target" is ruled to the **Close band with the target taken
out** - the target is at Close, so anything between is inside that band, and the
target takes the Restrain rather than the vines. The save is a clean escape
rather than a save for half, because the card prints "succeed **or** be hit"
where Scorched Earth and Hellfire print "targets who succeed take half damage".

**Healing Field waits for two people.** One use a long rest spent to take a
single HP off a single PC is the shape of thing a party wishes they still had
later, so the field goes up when it would restore two or more - and the 2 Hope
upgrade is bought only when somebody in it actually has 2 HP marked, which is the
standing clearing-in-full rule.

### Batch 13 — Splendor and Valor at level 4 (4 cards)

The last of level 4. **Verified against the printed page** (SRD pp. 132 and 134).

| Card | Disposition |
|---|---|
| **Life Ward** (Spl 4) | Modelled. 3 Hope marks an ally; the next death move they would make becomes clearing a Hit Point, and the ward is spent doing it |
| **Goad Them On** (Val 4) | Modelled. A Presence Roll forces a Stress, then the adversary's next spotlight is spent attacking the taunter at Disadvantage |
| **Support Tank** (Val 4) | Modelled. 2 Hope rethrows **one** die of an ally's failed roll |
| **Divination** (Spl 4) | No combat effect - one yes-or-no question about the near future |

Three pieces of shared machinery, and this is the batch that cost the most since
batch 7:

- **`death_move_ward`** - party content that can stop a PC's death move
  happening at all. Nothing could reach that moment before: every damage hook
  fires while a hit is being worked out, and a death move is what happens once it
  has been. Asked from `mark_hp_and_check_death` before `avoid_death`, so a
  prevented death move leaves nothing behind - no unconsciousness, no tally, no
  scar roll. The reach is limited by what carries a `fight`, and that limit is
  declared as a gap on the card rather than hidden.
- **`adversary_attack_disadvantage`** - party content that hobbles an
  *adversary's* attack roll, which is the last empty corner of that four-way
  table. GM-side content could already hobble a PC's swing and aid an attack on
  one; the party could aid its own. Folded into `adversary_attack_advantage` with
  `combined`, so it cancels rather than overriding.
- **`DualityRollResult` now records the die sizes**, which is a `dice/` change
  and the reason is worth stating plainly: Support Tank re-rolls **one** die, so
  the replacement is built by changing a single field of the resolved roll, and
  that needs to know what the die was rolled on. The Hope Die is not always a d12.
  Both fields are defaulted, so every existing construction is unchanged.

**Support Tank is the first content anywhere that re-rolls a single die.** Every
other registrant on the `reroll` hook re-makes the whole roll, which
SIMULATION-RULES.md records as a reading of "reroll your Duality Dice"; this card
names one die, so it ignores `remake` entirely. The consequence is that it
re-rolls *less* and can therefore do more - the untouched die keeps its value, so
a rethrow landing equal to it is a critical.

**Life Ward is the first thing that reaches a death move**, and it is worth
reading its numbers knowing what it costs: 3 Hope is most of a pool, and the
ward does nothing at all until the moment it does everything. The user's ruling
holds it back until the frailest ally is near death, which is a real bet - a
party that never gets there has spent nothing, and one that gets there twice has
only the one ward.

### Batch 14 — Arcana and Blade at level 5 (4 cards)

The first of level 5. **Verified against the printed page** (SRD pp. 119-121);
Arcana's level 5 crosses the sheet the way Grace's level 4 did - Chain Lightning
sits at the foot of p. 119 and Premonition at the head of p. 120.

| Card | Disposition |
|---|---|
| **Chain Lightning** (Ar 5) | Modelled. 2 Stress, one Spellcast Roll over the Close band, and a flat-d20 reaction roll against that roll's own total for everyone it beat - then the same again, wave after wave, until a wave catches nobody |
| **Premonition** (Ar 5) | Modelled, partial. Once per long rest, a move that failed is taken back and the whole spotlight is chosen again |
| **Champion's Edge** (Bl 5) | Modelled. Up to 3 Hope cashed in on a critical, one for each of the card's three options that would actually do something |
| **Vitality** (Bl 5) | No combat effect - two of a Stress slot, an HP slot and +2 thresholds, all of them values a sheet carries resolved. The card then vaults itself permanently, so it does not even hold a loadout slot |

One piece of shared machinery, and it is the batch:

- **`move_rescind`** - content that takes its holder's move back and sends them
  through the whole spotlight again. **Deliberately not the `reroll` hook**, which
  re-throws the *dice* of the roll that was made: Premonition says "make another
  move instead", so the options are shuffled afresh and the second attempt can be
  an entirely different card. Folding it into the reroll hook, with the difference
  written up as a gap, would have been an existing simplification swallowing a
  card that disagrees with it - the trap Support Tank walked into one batch ago.
  One call site, in `combat/policy.py` → `take_pc_turn`, asked once per spotlight.

**What a rescind can take back is narrower than the card, and the boundary is
where the value is.** Only a move that dealt no damage is offered, because the
roll's Hope or Fear is spent by the loop *after* the move returns - so a rescinded
failure hands the GM no Fear and does not pass the spotlight, which is most of
what the card is worth. A success with Fear cannot be unmade, and nothing the
first attempt spent comes back; both are declared as gaps.

**Chain Lightning is the first ability whose reach depends on where the
*adversaries* are relative to each other** rather than relative to the caster.
Every area card so far asks "who is within X of me"; this one asks "who is within
X of the ones I just hit", and the ruling is that each wave draws the Close band
again over whoever the lightning has not reached. Waves stop when one catches
nobody. It is also the most expensive single cast in the catalogue at 2 Stress,
which is what puts it on the declining side of the area split.

**Champion's Edge is the first card that buys several things off one trigger.**
Three options, three Hope, no repeats - so the ruling is simply that every option
which isn't a no-op is bought while the Hope lasts, and the shuffle picks when
the Hope runs short. Worth knowing what it does *not* reach: `on_hit` is asked
where a landed attack rolled damage, so a critical that applies a condition
instead never sees it.

### Batch 15 — Bone and Codex at level 5 (4 cards)

**Verified against the printed page** (SRD pp. 122-123 and 124-125). Codex stops
printing Grimoires at level 5 and prints plain Spells instead, so for the first
time its two cards are cards rather than books.

| Card | Disposition |
|---|---|
| **Signature Move** (Bo 5) | Modelled. Once per rest, a **d20** replaces the Hope Die on an action roll, and a success clears a Stress |
| **Know Thy Enemy** (Bo 5) | No combat effect - an Instinct Roll while observing a creature, buying information the simulator's own policies already read |
| **Manifest Wall** (Cx 5) | No combat effect - terrain and a shunt, and no positions are tracked |
| **Teleport** (Cx 5) | No combat effect - travel, the Blink Out case at longer range |

**No new machinery**, which is the notable thing about the batch after the last
one: Signature Move is built entirely out of parts, and three of the four cards
are declarations.

**Signature Move is the first content anywhere to swap the party's Hope Die.**
The `hope_die` hook has existed since the Faerie, and until now nothing had
registered on it from a domain card. A d20 against a d12 Fear Die raises the
total by four on average and, more importantly, makes the roll come up with
**Hope** far more often - which is what decides whether the party keeps the
spotlight.

Two things about how it is built are worth knowing. Its Stress clear is a second
hook on the same name (the Ferocity arrangement), and **which roll to pay out on
is read off `DualityRollResult.hope_die_sides`** rather than a token the swap
left behind - because `hope_die_for` is asked at roll sites the on-roll hook never
hears about, so a token set on a Reaction Roll would sit there and fire on the
next action roll instead. That field exists because Support Tank needed it one
batch ago, which is the second use it has found.

**Know Thy Enemy is the dismissal worth reading carefully**, because half of it
is a real combat effect. "Mark a Stress to remove a Fear from the GM's Fear Pool"
drains a pool this simulator tracks closely, and a partial implementation - the
Fear clause running, the information declared a gap - was proposed and declined.
The user's ruling files the card whole, on its **trigger**: "when observing a
creature" is not a move the simulator makes, which is the Gifted Tracker and
Stealth Expertise reading. If encounters ever grow a scouting step, this is the
card waiting for it.

### Batch 16 — Grace and Midnight at level 5 (4 cards)

**Verified against the printed page** (SRD pp. 126-127 and 128-129).

| Card | Disposition |
|---|---|
| **Words of Discord** (Gr 5) | Modelled, partial. A Spellcast Roll (13) makes an adversary mark a Stress and attack one of its own |
| **Hush** (Mid 5) | Modelled, partial. A Hope Silences a target and the Very Close band around them, which stops the ones whose attacks are magic |
| **Thought Delver** (Gr 5) | No combat effect - reading minds, the Through Your Eyes case |
| **Phantom Retreat** (Mid 5) | No combat effect - a delayed teleport back to a marked spot, the Blink Out case |

**No new machinery**, and for Words of Discord that is the whole story of the
ruling. Making an adversary attack its own side had no representation anywhere,
and the natural reading - that it replaces the adversary's next activation - would
have needed a new hook for party content to take over an adversary's spotlight,
since the existing target-override hook returns a PC and would raise on an
adversary. The user ruled the attack **immediate**, resolved inside the cast, so
the card does it all itself. The mechanical consequence is worth carrying into any
reading of the numbers: the whisperer still takes its own spotlight afterwards, so
the party gains an attack on the GM's side rather than removing one aimed at
themselves.

The compelled attack is rolled directly rather than through `Adversary.attack` -
that measures against a PC's Evasion and would raise on an adversary target, and
an attack on an adversary is measured against **Difficulty**.

**Silenced is the first new condition since level 3**, and the first whose effect
is decided *per holder at the moment it lands*. "They can't cast spells" is
answered by the Counterspell rule - magic damage is the only magic represented
here - so the card asks each target whether its printed attack is magic and sets
`Condition.prevents_action` accordingly. A magic adversary is Stunned in all but
name; a physical one is Silenced and inert like Restrained, and the GM still pays
a Fear each to clear it.

**Hush also brings the first party-applied condition that can end without the GM
paying**, through its printed "or you take Major damage" clause. That reaches the
*caster* rather than the holder, so it hangs off `on_damaged` and clears only the
silences whose `source` is that PC.

Worth noting alongside it: the user flagged that the party is now **draining the
GM's Fear** through the standing "the GM pays a Fear to clear it" rule, and Hush
applies one condition per target across an area. Recorded in `SIMULATION-RULES.md`
under that rule as something to look at in the numbers rather than something to
change.

### Batch 17 — Sage, Splendor and Valor at level 5 (6 cards)

The last of level 5, and three domains rather than two at the user's request.
**Verified against the printed page** (SRD pp. 130-131, 132-133 and 134-135).

| Card | Disposition |
|---|---|
| **Thorn Skin** (Sg 5) | Modelled, partial. A Hope sprouts a pool of d6s that soak incoming damage and bite back at anything in Melee |
| **Wild Fortress** (Sg 5) | Modelled, partial. A dome two PCs shelter inside - it soaks everything aimed at them and costs them their spotlights |
| **Smite** (Sp 5) | Modelled, partial. 3 Hope charges a weapon blow that lands **doubled**, and as magic |
| **Rousing Strike** (V 5) | Modelled, partial. Once per rest, a critical clears a Hit Point on every conscious PC, or 1d4 Stress for anyone at full HP |
| **Shape Material** (Sp 5) | No combat effect - craft, and there are no objects here to shape |
| **Armorer** (V 5) | Out of combat - its +1 Armor Score is already in the sheet, and what remains is a downtime move that restores an Armor Slot on **every ally** |

Three pieces of shared machinery, and this is the batch that cost the most since
batch 13:

- **`damage_scaling`** - content that multiplies the damage its own holder deals,
  the party-side twin of the GM's `damage_multiplier`. None of the four existing
  damage hooks could say "double the result of your damage roll": two add to the
  roll, one reshapes the dice before the throw, and two touch a single die.
- **`DamageRollResult.multiplier`**, which is a `dice/` change and the reason the
  hook can be honest. Doubling has to reach the dice, the flat modifier **and**
  the critical bonus at once; doubling the dice count instead would land on the
  same mean with a different spread, which is a different card in a game where
  damage becomes HP through bands. A raw input beside `drop_lowest`, defaulted, so
  every existing construction is unchanged.
- **`damage_typing`** - content that retypes its holder's weapon hit. Deliberately
  not `standard_damage_type` next door, which says the same thing for an
  adversary and takes no `fight`: a charge that is spent or unspent is exactly the
  per-fight state that hook refuses to carry.

Plus one change to the fight loop: **a PC who cannot act is skipped rather than
spotlighted**, and the spotlight passes to the GM only when nobody in the party
can act. The two sides now answer `cannot_act` differently, and should - a GM paid
for the activation a Stunned adversary wastes, and the party's spotlight is not
bought. It is also what stops `_resolve` spinning, since a spotlight that resolves
into nothing never increments `pc_actions`.

**Wild Fortress is the first card that takes PCs out of the fight**, and the first
thing with a damage track that is not a combatant. The dome is a pair of tokens on
its caster: hits aimed at either occupant are returned in full by the card's own
damage-reduction hook and marked against the dome's printed 15/30, and it releases
both of them at 3. The `SHELTERED` condition carries no `end`, because what ends
it happens to the dome and a dome is never offered an announced moment.

**Armorer is the clearest case yet of a card whose two clauses want two different
states.** Its Armor Score bonus is a number the sheet already carries, and its
downtime clause restores an Armor Slot on every ally - which is neither
unrepresentable nor small. Filing it as *out of combat* keeps it on the
sequenced-encounter list rather than losing it to a dismissal.

### Batch 18 — Arcana, Blade and Bone at level 6 (6 cards)

The first of level 6, three domains at once. **Verified against the printed page**
(SRD pp. 120-121 for Arcana's level 6 and Blade's, and p. 123 for Bone's).

| Card | Disposition |
|---|---|
| **Telekinesis** (Ar 6) | Modelled, partial. Two Spellcast Rolls in one action - lift one adversary, throw them at another for Proficiency d12s + 4 physical |
| **Battle-Hardened** (Bl 6) | Modelled. Once per long rest, a Hope turns a death move into clearing a Hit Point |
| **Rage Up** (Bl 6) | Modelled, partial. Up to 2 Stress before a swing, each worth twice the holder's Strength on the damage |
| **Rapid Riposte** (Bn 6) | Modelled, partial. A Melee attack that missed you costs a Stress and takes the weapon's damage straight back |
| **Rift Walker** (Ar 6) | No combat effect - a marking on the ground and a rift back to it, which is passage rather than a fight |
| **Recovery** (Bn 6) | Out of combat - a long rest downtime move taken during a short rest, and a Hope lends it to an ally |

**No new machinery**, which is the first batch since 12 that has been true of and
is not what the level 5 notes led anyone to expect. All four modelled cards
registered on hooks that already existed - `action`, `death_move_ward`,
`damage_bonus` and `attack_missed` - and nothing in `combat/`, `dice/` or
`content/registry.py` changed.

**Telekinesis is the first card that prints two rolls inside one action.** The
lift goes through `spellcast()` and is the roll the spotlight resolves on; the
throw is rolled plainly on the caster's Spellcast trait. That split is forced
rather than chosen: `total_roll_bonus`, `help_with_roll` and `hope_die_for` all
keep the contract that being asked is the commitment, so asking them a second time
in one action would spend an ally's Hope twice and claim a per-rest use twice. The
throw therefore also earns no Hope or Fear and is not offered to reroll content,
and both halves are declared as gaps.

**Rapid Riposte is Redirect's twin.** The two answer the same trigger - an attack
on you that failed - split by the band it came from, which both read off
`Adversary.attack_band` rather than off any position. Its damage is built through
`adjust_damage_pool` the way `attack_with` builds a swing's, so a weapon feature
reaches the riposte; that is also what will pick up **Paired**'s bonus to primary
weapon damage without this card changing, once secondary weapons exist at all.
They do not today - `secondary_weapon` is loaded off the sheet and read by
nothing, and no secondary weapon is catalogued - which is now written out in full
in `SIMULATION-RULES.md` §3 rather than left as the one-line entry it was.

**Rage Up is the first card whose cost is paid before the roll it pays for.** The
`damage_bonus` hook is asked before the attack is rolled, which is exactly where
the card puts the decision, so up to 2 Stress goes whether or not the swing lands.
That is the page read literally rather than a simplification, and against a
Strength of 3 it is +12 on the number the target's threshold bands are read
against.

### Batch 19 — Codex, Grace and Midnight at level 6 (6 cards)

**Verified against the printed page** (SRD p. 125 for Codex's level 6, p. 127 for
Grace's, and p. 129 for Midnight's - all three levels sit on the right-hand page
of their domain's spread).

| Card | Disposition |
|---|---|
| **Sigil of Retribution** (Cx 6) | Modelled, partial. No roll: mark an adversary and hand the GM a Fear; every blow it lands on the party banks a d8, cashed into the next hit on it |
| **Banish** (Cx 6) | Modelled, partial. Two contests, and on the second failure the adversary leaves the field entirely - returning only as the party's own rolls with Fear wear the banishment down |
| **Never Upstaged** (Gr 6) | Modelled, partial. A Stress banks every Hit Point a hit cost, and the next landed attack cashes each token for +5 damage |
| **Share the Burden** (Gr 6) | Modelled, partial. No roll: take an ally's marked Stress onto your own track, and gain a Hope for each slot moved |
| **Dark Whispers** (Mn 6) | No combat effect - a private channel into somebody's mind, and four questions for the GM |
| **Mass Disguise** (Mn 6) | No combat effect - minutes of silence, then advantage on Presence Rolls to avoid scrutiny |

Two pieces of shared machinery:

- **`ally_on_damaged`** - party content that watches *anyone in the party* take
  damage, the party-wide twin of `on_damaged`. Sigil of Retribution needs it: the
  card charges when the marked adversary "deals damage to **you or your allies**",
  and holder-scoping it would have made the sigil charge only off hits the caster
  personally took. Asked from the same place its twin is, in
  `PlayerCharacter.take_damage`, and party-side only - "you or your allies" is the
  party.
- **`FightState.removed`**, with a `removed_adversaries` property on the state and
  on the `Fight` protocol. Banish takes an adversary off the field and the page
  prints a way back, so something has to hold the object while it is gone -
  `remove` previously kept nothing. It is not a graveyard: nothing in the loop
  reads it, an adversary in it is as absent as before, and holding the object alive
  incidentally closes the `id()`-reuse hazard `remove`'s docstring already warned
  about, for exactly the case that cares.

**Sigil of Retribution is the first party card that pays the GM.** Its cost is not
Hope or Stress but a Fear handed straight over, which is an extra activation the
GM would not otherwise have had - and it is spent up front, whether or not the
sigil ever charges. The user's ruling was explicitly **against** giving it a
trigger to earn that back: it joins the random selection like any other free
ability. Worth watching in the numbers, since every other Fear rule in the project
runs the other way, with the party draining the pool.

**Banish is the first thing that takes an adversary off the field and can put it
back.** The Green Ooze's *Split* removes and never returns; Codex's *More Where
That Came From* summons something new. This is the same object leaving and coming
home with the HP it left with. One consequence is worth reading numbers with in
mind and is declared as a gap: the party can **win** a fight while an adversary is
banished, because a removed adversary is not on the field.

**Never Upstaged found the last empty corner of the damage hooks.** "On your next
*successful* attack" rules out `damage_bonus`, which is asked before the dice and
would clear the tokens on a miss; "+5 for each token" is flat rather than dice,
which rules out `extra_damage`. `damage_pool` is the only hook asked after an
attack has landed and before its damage is rolled, and `DamagePool` carries the
flat modifier - so no new machinery was needed after all.

### Batch 20 — Sage, Splendor and Valor at level 6 (6 cards)

The last of level 6. **Verified against the printed page** (SRD p. 131 for Sage's
level 6, p. 133 for Splendor's and p. 135 for Valor's - the right-hand page of each
domain's spread, as batch 19 found).

| Card | Disposition |
|---|---|
| **Restoration** (Sp 6) | Modelled, partial. A pool of touches equal to the caster's Spellcast trait, refilled by a long rest; one token clears 2 Hit Points, 2 Stress, or a condition |
| **Zone of Protection** (Sp 6) | Modelled, partial. A Spellcast Roll (16) raises a ward that soaks 1, then 2, and on up to 6 before it goes out |
| **Inevitable** (V 6) | Modelled, partial. A failed action roll hands the next one Advantage. No cost, no limit, no policy |
| **Rise Up** (V 6) | Modelled, partial. Marking 1 or more Hit Points clears a Stress |
| **Conjured Steeds** (Sg 6) | Out of combat - mounts conjured on the road, whose rider modifiers are what the party would carry into a fight at the far end of it |
| **Forager** (Sg 6) | Out of combat - "as an additional downtime move", producing consumables that would each change a fight they were spent in |

One piece of shared machinery and one new reader on the fight state:

- **`action_roll_advantage`** - content that hands its holder Advantage on **any**
  action roll rather than on a standard attack. `attack_advantage` next door is
  asked only where a standard attack is rolled - the printed attack on the GM's
  side, the weapon swing on the party's - so Inevitable registered there would
  have reached a Guardian's swing and never a Wizard's Spellcast Roll. Two call
  sites, `items/weapons.py` → `attack_with` and `content/spellcast.py` →
  `spellcast`, which between them are every shape a PC's action roll takes bar
  the two that roll by hand. A **Reaction Roll is deliberately never offered it**:
  the SRD's action rolls and reaction rolls are different things.
- **`FightState.conditions_on`**, with a matching line on the `Fight` protocol.
  `has_condition` and `condition_on` both ask about a condition the caller already
  has in mind, and Restoration doesn't have one - it spends a token to lift
  *whatever* is there. The order the dict returns them in carries no meaning, so
  the card chooses at random rather than taking the first.

**Restoration is the first card that can lift a condition without naming one**,
and that turned out to need a scope nobody had asked for. Clearing any condition
at random would sometimes clear one the *party* put on a PC - Sage's *Wild
Fortress* shelters two of them deliberately - so the card only lifts an affliction
whose `Condition.source` is not a conscious party member. Read off the record
rather than off any name, so nothing here knows what Sheltered is; an unsourced
condition counts as an affliction, which errs toward spending a token rather than
undoing the party's own work.

**Zone of Protection is the first ward that gets better the more it works.** Every
other damage reduction in the project is a fixed amount or a roll - an Armor Slot,
Rune Ward's 1d8, Thorn Skin's pool - and this one starts at 1 and climbs to 6
before ending, for 21 damage over six hits. That is what makes casting it early
worth something, and it is why the user ruled it cast at the start of the fight.
The other half of that ruling is more unusual: **membership is rolled per hit**
rather than fixed when the zone goes up, since the zone is a *point* rather than a
person and `chance_within` is the tool for "is somebody within X of here". Over a
four-PC party that comes to a one-in-four chance each time somebody is hit.

**Sage's level 6 is the first whole level of a domain filed *out of combat*.**
Both cards were offered as dismissals and the user ruled against both. Conjured
Steeds is the interesting one: two of its three clauses are travel, but the third
is a real combat trade the simulator could express outright - a rider takes -2 on
attack rolls for +2 on damage - so *no combat effect* would have been false. What
is true of it is when it is cast. Forager names its own moment ("as an additional
downtime move"), and the user's ruling is that when sequenced encounters land it
is modelled as that downtime move, handing the party a consumable carrying one of
the six printed abilities.

**Two of the four modelled cards needed no policy at all**, which is worth
recording because it is rare here: Inevitable and Rise Up both cost nothing, have
no limit and state their own triggers exactly. Rise Up did need a *reading*
though, and it is one that will recur - see below.

**"From an attack" is now read as "from damage" throughout.** Rise Up clears a
Stress "when you mark 1 or more Hit Points from an attack", and the damage hooks
carry no attacker - damage reaches a combatant as an amount and a type. Declaring
the qualifier as a gap was the obvious move and the user ruled against it: in a
combat simulator everything that marks damage is an attack, a hurled fireball
included. The reading is in `SIMULATION-RULES.md` §2 once rather than restated on
every card that will want it.

### Batch 21 — Arcana, Blade and Bone at level 7 (6 cards)

The first of level 7. **Verified against the printed page** (SRD pp. 120-121 for
Arcana's level 7 and Blade's, and p. 123 for Bone's - the same spread batch 18
read for level 6).

| Card | Disposition |
|---|---|
| **Arcana-Touched** (Ar 7) | Modelled, partial. +1 on Spellcast Rolls, plus a once-per-rest switch of the Hope and Fear Dice |
| **Cloaking Blast** (Ar 7) | Modelled, partial. A Hope off a successful cast puts the caster out of reach until they next roll |
| **Blade-Touched** (Bl 7) | Modelled, partial. +2 on attack rolls; the +4 Severe threshold is a value the sheet carries |
| **Glancing Blow** (Bl 7) | Modelled, partial. A Stress turns a failed swing into weapon damage at half Proficiency |
| **Bone-Touched** (Bn 7) | Modelled, partial. 3 Hope makes one landed attack fail; the +1 Agility is a value the sheet carries |
| **Cruel Precision** (Bn 7) | Modelled, partial. Body Basher with the better of Finesse and Agility |

**Level 7 is the *X*-Touched level**, and the batch's largest decision was not to
build for it. Each of the nine cards is gated on "4 or more of the domain cards in
your loadout are from the *X* domain", and nothing records which domain a card
belongs to. Reading it off the module a card is defined in was proposed - the
domain is already expressed by which file the card lives in - and the user ruled
against the machinery: carrying the card is taken as proof the condition is met,
since a player who takes it has built for it. It errs generous, it is declared as
a gap on every Touched card, and the remaining six domains now inherit the answer.

Three pieces of shared machinery:

- **`spellcast_bonus`** - content that adds to a **Spellcast Roll** and nothing
  else. `total_roll_bonus` is asked from `items/weapons.py` and
  `content/spellcast.py` with nothing to tell the two apart, so Arcana-Touched's
  "+1 to your Spellcast Rolls" registered there would have added itself to a
  Wizard's Broadsword. One call site. It turned out to do second duty as the only
  place content can learn that **a cast is happening at all**, which is what
  Cloaking Blast reads for its trigger - `on_roll` fires for every action roll and
  cannot tell a spell from a swing.
- **`attack_failed`** - content on an **attacker** answering their own attack
  failing, and the mirror of `attack_missed`. That hook belongs to whoever was
  swung *at* - Redirect and Rapid Riposte both answer a miss made against you -
  and is asked from the GM turn; this one is asked from `items/weapons.py`, where
  a PC's own roll comes up short with the target still in hand. One word apart in
  English and opposite in every other respect, so neither is folded into the other.
- **`Condition.untargetable`**, with `FightState.cannot_be_targeted` and a filter
  in `combat/policy.py`'s targeting rule. The exact opposite number of
  `prevents_action`: one stops the holder acting, this stops anybody acting on
  them.

**Cloaking Blast is the first party content that reaches the GM's targeting
rule.** Its printed text is line of sight and standing still, neither of which is
tracked, so the user ruled the effect instead - and ruled it **stronger than
Hidden**: while Cloaked the holder cannot be aimed at, where Hidden only hands
rolls against them Disadvantage. Two things about it are worth carrying into any
reading of the numbers. A cloak protects **an individual, not the party**: when
every conscious PC is out of reach the targeting rule hands back the whole list
rather than nothing, since an activation that finds nobody would need a rule the
loop does not have. And the cloak breaks on **any** action roll rather than only
an attack, because `made_an_attack` means "this action rolled" - which errs
conservative, ending the cloak sooner than the page would.

**Sage's Wild Fortress prints the same "can't be targeted" clause and keeps its
declared gap.** The machinery to close it now exists, and closing it would be
changing a ruling the user made separately rather than implementing this one.

**Glancing Blow is the first card that pays out on the holder's own attack
failing**, and it is Rapid Riposte's damage off the opposite trigger - the pool
built through `adjust_damage_pool` so a Greatsword's *Massive* discards its lowest
on a miss exactly as it would on a hit. Half a Proficiency **rounds up**, which is
the user's rule and means the card can never come to no dice at all.

**Two clauses were filed against the sheet rather than run**: Blade-Touched's +4
Severe threshold, and Bone-Touched's +1 Agility. The second is the first *trait*
to fall under the resolved-values rule, which until now had only covered
thresholds, Evasion, Armor Score and slot counts.

### Batch 22 — Codex, Grace and Midnight at level 7 (6 cards, 2 spells)

**Verified against the printed page** (SRD p. 125 for Codex's level 7, p. 127 for
Grace's, and p. 129 for Midnight's - all three on the right-hand page of their
domain's spread, as batch 19 found for level 6).

| Card | Disposition |
|---|---|
| **Codex-Touched** (Cx 7) | Modelled, partial. A Stress buys the caster's whole Proficiency on a Spellcast Roll, below a ceiling of 3 marked |
| **Grace-Touched** (Gr 7) | Modelled, partial. An Armor Slot pays where a Stress would; an adversary's wound is taken as Stress instead |
| **Midnight-Touched** (Mn 7) | Modelled, partial. A Hope instead of the GM's Fear at 0 Hope; a Stress adds the Fear Die to a landed swing |
| **Vanishing Dodge** (Mn 7) | Modelled, partial. A failed physical attack buys Hidden until the PC's next action roll |
| **Book of Homet** (Cx 7) | No combat effect - Pass Through and Plane Gate are both passage |
| **Endless Charisma** (Gr 7) | No combat effect - dismissed on its trigger, a social action roll |

Three pieces of shared machinery, and one signature change:

- **`stress_instead_of_hp`** - party content that turns HP an adversary would mark
  into Stress. Asked from `Adversary.take_damage` after both severity hooks and
  before the marking, and party-wide, since the content belongs to a PC rather
  than to whoever is being hit.
- **`armor_instead_of_stress`** - content letting its holder pay a Stress cost with
  an Armor Slot. The **second hook in the project asked with no `fight`**, for
  `standard_damage_type`'s reason turned to the party's side: the answer is a
  standing fact about a sheet, and `spend_stress` is called from dozens of places
  that have no fight to pass.
- **`fear_conversion`** - party content that stops the GM gaining a Fear. One call
  site, in `_apply_duality_outcome` immediately before `gain_fear`, which is the
  one place a PC's roll hands the GM anything. `apply_on_roll` fires a step earlier
  and is only *told* how the roll came out.
- **`damage_pool` now carries the attack roll**, defaulted to None. A mechanical
  change touching its four existing registrants and three call sites.

**Grace-Touched is the first card anywhere that reaches the *resource* a mark
lands on** rather than its size, and it does it on both sides of the table at once
- armor paying for the party's Stress, Stress paying for an adversary's HP. That
is why it needed two hooks nothing else uses, and it is worth reading its numbers
knowing the first clause touches **every** Stress cost on the sheet rather than
one card.

**Its second clause was the batch's real correction.** "When you would force a
target to mark a number of Hit Points" was read as covering only effects that say
"mark an HP" outright - of which the project has exactly one - and proposed as a
gap on those grounds. The user's ruling is that it covers **damage**, which makes
it a far larger card, with one scope: HP an adversary marks *willingly* for its own
features is not somebody forcing it, so `will_spend_hp` is untouched. The general
lesson is in SIMULATION-RULES.md beside the "everything that marks damage is an
attack" row - do not narrow a trigger away from ordinary damage.

**One mismatch is recorded rather than resolved.** Grace-Touched's HP-to-Stress
policy was ruled partly on stressing an adversary out making them *Vulnerable*,
and `Adversary.is_vulnerable` is always False here - nothing in the SRD makes an
adversary Vulnerable of its own accord. The ruling stands as made and what it buys
is still real: an adversary with no Stress free cannot pay for its Action features.

**Midnight-Touched is the first card that stops the GM gaining a Fear.** Codex's
*Sigil of Retribution* pays one over and several cards drain the pool by making
the GM clear a condition; nothing had ever denied one at the moment it was
generated. Its second clause is what put the attack roll on `damage_pool`: "the
result of your Fear Die" is a **flat** amount that is only knowable from the roll,
and of the two hooks that could otherwise answer, `extra_damage` sees the roll and
can only return dice while `damage_pool` carried the modifier and could not see the
roll.

**Vanishing Dodge is the moment `WHEN_THEY_ATTACK` was really written for.**
Cloaking Blast, which it was built for last batch, means "until you attack" and
settles for "until your next action roll" as an approximation; this card prints
"until the next time you make an action roll" exactly. It is also the third card on
the missed-attack trigger after Redirect and Rapid Riposte, and the first to answer
a miss with something other than damage.

**Codex-Touched is the only Touched card whose bonus has a price**, and the only
Stress cost in the project that does not ask `will_spend_stress` - the user ruled a
ceiling of 3 marked instead, because a rider asked on *every* cast would otherwise
run the track dry in a few spotlights.

### Batch 24 — Arcana, Blade and Bone at level 8 (6 cards)

The first of level 8, and the first batch that does **not** close the level it
opens. **Verified against the printed page** (SRD pp. 120-123), a re-read of
pages every earlier batch has used - and the other six domains' level 8 pages
were read at the same time, which is why the table above can name what is
missing rather than only count it.

| Card | Disposition |
|---|---|
| **Arcane Reflection** (Ar 8) | Modelled. Every banked Hope buys that many d6s against an incoming magic hit; a 6 negates it outright **and** deals the same damage back to whoever is spotlighted |
| **Confusing Aura** (Ar 8) | Modelled. A Spellcast Roll (14) raises one layer, up to two more bought with Stress; each incoming hit rolls a d6 per layer, a 5 or 6 costs a layer and turns the attack away, and all 4s or lower ends the spell |
| **Battle Cry** (Bl 8) | Modelled. Once per long rest: every ally clears a Stress, gains a Hope, and swings with Advantage until any PC fails with Fear |
| **Frenzy** (Bl 8) | Modelled. Once every Armor Slot is marked, the Blade becomes *Frenzied* for the rest of the fight - no Armor Slots, +10 damage, +8 Severe threshold |
| **Breaking Blow** (Bo 8) | Modelled. A Stress on a landed hit; the next successful attack on that creature, **by anybody**, deals an extra 2d12 |
| **Wrangle** (Bo 8) | No combat effect - an Agility Roll and a Hope that move both sides around, and no positions are tracked |

Two pieces of shared machinery, one of each kind the project has:

- **`ally_attack_advantage`** - party content that hands *another PC's* attack
  Advantage, and the last empty corner of a four-way table that was otherwise
  full. GM-side content could already aid an attack on a PC and hobble a PC's
  swing; party-side content could hobble an adversary's swing and aid its own
  holder's. Nothing could aid an ally's, which is the whole of Battle Cry.
  Folded with `combined` in `items/weapons.py` beside the holder-scoped hook.
- **`Condition.denies_armor`**, plus `FightState.armor_is_denied` and one call in
  `PlayerCharacter.take_damage`. A **field rather than a hook**, which is the
  cheaper of the two shapes and the one `prevents_action` and `untargetable`
  already take: the answer belongs to the state a combatant is in rather than to
  content that has to be consulted. Because the additional-slot hook is asked
  inside the same branch, Bone's *Brace* is correctly shut off while Frenzied
  without knowing any of this exists.

**Frenzied is a condition, and that was the batch's correction.** *Frenzy* was
planned as a per-fight token on the holder, which would have worked; the user's
ruling is that a state the page **names and refers back to** is a condition, the
same call *Cloaked* got. What that buys is that the rest of the game can talk
about it - the play-by-play says what the PC is, other content can ask, and the
armor ban rides a field on the record rather than a private flag. It is also the
first condition on a PC that carries no ender at all: "until there are no more
adversaries within sight" is the whole fight in a simulator where a fight ends
with the field cleared either way.

**Frenzy's +8 Severe threshold is expressed as a band rather than as a number.**
Nothing reads a PC's thresholds through a hook - a sheet carries them resolved,
and every reader assumes a resolved value does not move mid-fight - so the card
registers on `severity_response` and takes one HP off a hit that lands inside the
window the bonus opens. That is exactly equivalent for the damage pipeline and
invisible to everything else, which is declared as a gap: Get Back Up's trigger
and Rune Ward's arithmetic both still see the printed number.

**Breaking Blow is Chokehold's shape at four times the size.** Both mark a
creature and pay out on whoever hits it next, and both therefore need
`ally_extra_damage` rather than the holder-scoped hook - registered there the card
would only ever pay its own owner. What is new is the ordering that stops a charge
collecting itself: the damage roll asks the payout hook, and `on_hit` lays the
charge afterwards, so the swing that marks the target never collects from it.

**Arcane Reflection is the first card that answers a hit on both sides at once.**
Scramble, Arcane Deflection and Bone-Touched all negate; this one negates *and*
deals the same damage to whoever threw it, which is `fight.spotlighted` - the same
handle Counterspell needed and the only one there is, since damage arrives at a PC
carrying an amount and a type and no attacker.

**Confusing Aura is the first defence that wears out.** Every other per-rest guard
in the project is limited by uses; this one stands for a counted number of attacks
and loses a layer to each one it turns away, so it can end by succeeding as well
as by failing. It is also the third card to read "once per rest **on a success**"
- Troublemaker and Hypnotic Shimmer got there first - so a failed cast costs the
spotlight and leaves the card available.

### Batch 25 — Codex, Grace and Midnight at level 8 (6 cards, 2 spells)

The second of level 8, and the batch with the **most declarations and the least
code** of any so far: six cards, of which two are built. **Verified against the
printed page** (SRD pp. 125, 127 and 129), read at the same time as batch 24's.

| Card or spell | Disposition |
|---|---|
| **Mass Enrapture** (Gr 8) | Modelled. One Spellcast Roll over the Far band, everything it beats *Enraptured* - then the Stress is spent at once to force a Stress on all of them and end the spell |
| **Spellcharge** (Mid 8) | Modelled. Magic damage banks a token per HP marked, capped at the Spellcast trait; the whole pool goes into the next attack that lands, a d6 apiece |
| **Book of Vyola** (Cx 8) | No combat effect, declared as the book and as both spells. *Memory Delve* is information; *Shared Clarity* is symmetrical, so a pooled pair marks the same total Stress either way |
| **Safe Haven** (Cx 8) | **Out of combat** - the extra downtime move is real and large, and "a few minutes of calm to focus" is a condition a fight never meets |
| **Astral Projection** (Gr 8) | No combat effect - remote sensing somewhere the party is not fighting, the Floating Eye case |
| **Shadowhunter** (Mid 8) | No combat effect, dismissed on its **trigger** - nothing records how a fight is lit |

One piece of shared machinery, and it is a *fact* rather than a hook:

- **`on_damaged` now carries the `damage_type`.** Spellcharge's trigger names the
  type and its payload names the HP finally marked, and this is the only hook that
  has both - `severity_response` sees the type while the figure is still being
  settled. The same shape `marked_armor` took one level ago, and for the same
  reason: inferring the type afterwards from `fight.spotlighted`'s printed attack
  would be wrong for any feature that states its own. Fourteen registrants took the
  parameter defaulted; both sides of the table pass the type they already resolved
  at the top of `take_damage`, so this hook and the two severity hooks can never
  disagree about what landed.

**Shadowhunter is the dismissal worth reading, because the effect is enormous.**
Advantage on *every* attack roll and +1 Evasion is among the largest things a card
could grant, and none of that is why it is filed here. It is dismissed on its
trigger - "while you're shrouded in low light or darkness" - which has no
representation at all: the simulator holds no fact about where an encounter
happens. Reading it as always on, which is the ruling **Sage-Touched's**
natural-environment clause got one level earlier, was offered and declined; so was
gating it on the holder being Hidden. The two cards are worth comparing, since the
same shape of clause got opposite answers: Sage-Touched's other benefit is a +2,
and this one's is Advantage on everything.

**Mass Enrapture is the first card ruled into a shape its own page does not
describe.** The card is a lasting compulsion with an optional Stress that ends it;
the ruling is that it is only ever cast when that Stress *can* be paid, and paid
at once - so the compulsion never survives to a spotlight and what runs is an area
attack on the GM's Stress tracks. That is recorded as a gap on the card rather
than hidden, and it leaves level 1's *Enrapture* as the card that keeps its
condition. Note the interaction the implementation has to avoid: without skipping
adversaries who are already Enraptured, a mass cast would clear a compulsion
Enrapture had bought and paid for.

**Spellcharge is the first card that turns damage taken into damage dealt.**
Never Upstaged banks wounds and pays them back, which is close, but that one keys
on HP marked by anything; this one is magic only, which is why it needed the type.
Worth knowing the cap is the caster's Spellcast trait, so a Wizard's pool is
larger than a Guardian's would be - and that the pool empties into the first
attack that lands rather than being saved.

### Batch 26 — Sage, Splendor and Valor at level 8 (6 cards)

The last of level 8, and the batch that cost the most machinery of any since
batch 7. **Verified against the printed page** (SRD pp. 131, 133 and 135).

| Card | Disposition |
|---|---|
| **Forest Sprites** (Sg 8) | Modelled. Spellcast (13), then Hope down to a floor of 2 for that many one-shot sprites - each spent on either +3 to an ally's swing or a second Armor Slot for an ally's hit |
| **Rejuvenation Barrier** (Sg 8) | Modelled. Spellcast (15) once per rest; everyone inside clears 1d4 HP, and physical damage is halved for whoever is inside for the rest of the fight |
| **Shield Aura** (Spl 8) | Modelled. A Stress puts an aura on the frailest ally; while it holds, a hit that marked an Armor Slot drops one further threshold, and it fades when it takes one to nothing |
| **Stunning Sunlight** (Spl 8) | Modelled. One Spellcast Roll over the Far band, then a Hope per target for a Reaction Roll (14) - 3d20+3 on a save, 4d20+5 and *Stunned* on a failure |
| **Full Surge** (Vlr 8) | Modelled. 3 Stress writes +2 into every one of the holder's traits for the fight |
| **Ground Pound** (Vlr 8) | Modelled. 2 Hope and a Strength Roll over Very Close, then a Reaction Roll (17) - 4d10+8 physical, half on a save |

Three pieces of shared machinery, all of them the **party-wide twin** of a hook
that had only ever been holder-scoped:

- **`ally_roll_bonus`** - a flat bonus on another PC's attack roll. The flat twin
  of `ally_attack_advantage`, and not interchangeable with it: Advantage is a d6
  added to a duality roll, so a card printing "+3" cannot be expressed as one.
- **`ally_extra_armor_slot`** - a further Armor Slot for another PC's hit. It
  inherits `extra_armor_slot`'s trigger exactly, being asked from inside the same
  branch, so it never fires against direct damage or against a PC whose armor a
  condition has denied.
- **`ally_severity_response`** - the HP another PC's hit marks, in threshold
  bands. The last thing the party side could not say. `ally_damage_reduction`
  reaches somebody else's hit but works on the raw number, which is right for a
  ward rolling 1d8 and wrong for a card that moves a band: subtracting enough to
  cross one would also change the figure every other reader sees, so an ally's Get
  Back Up would stop firing. It carries `marked_armor`, which its holder-scoped
  twin does not, because Shield Aura's trigger is exactly that.

And one thing that is not a hook: **`PlayerCharacter.gain_trait_bonus`**, with a
`trait_bonuses` record beside it.

**Full Surge is the first card that moves a character's traits**, and the ruling
on how is the interesting part. `traits` is already the effective mapping every
reader consults, so writing the +2 into it is what makes the card complete - it
reaches action rolls, the dice a Spellcast-trait spell counts, and the damage Body
Basher, Rage Up and Cruel Precision read off Strength, Finesse and Agility. A
`roll_bonus` of +2 instead was offered and declined, because a card that says *all
of your traits* is not a bonus to one kind of roll. What keeps the mutation
compatible with the standing sheet-carries-resolved-values rule is the record: the
authored numbers stay recoverable, so nothing later has to guess whether a 4 was
written down or bought.

**Ground Pound is the first card typed by ruling rather than by the page.** It
prints no damage type at all, which is unusual, and the user ruled it physical on
the fiction. The alternative is worth recording because it is not neutral:
untyped damage matches no resistance and no immunity, so leaving it as printed
would have made the card reliably better against exactly the adversaries built to
resist things.

**Rejuvenation Barrier is the first party-wide resistance**, and it is expressed
as a *reduction* - `damage_resistance` is holder-scoped and this barrier belongs
to whoever cast it. The two consequences are declared on the card rather than
hidden: it sums with other reductions instead of following the SRD's "strongest
single resistance" rule, and it lands after any real resistance the target carries
rather than being reconciled with it.

## Consolidating `_spellcast`

Six copies of the same twelve lines became `content/spellcast.py` →
`spellcast()`, called by all six domain modules. Flagged as worth doing since
batch 3 and put off three times; what forced it was **Help an Ally**, which meant
editing all six copies to add one line each.

The copies had drifted three ways: four took a `difficulty` for area spells,
Grace's took a `trait` because Troublemaker rolls Presence, and Codex's took a
flat `bonus`. **Nothing ever passed the `bonus`** - it had been dead for as long
as nobody had cause to look at all six side by side, which is the argument for
consolidating stated as plainly as it can be. It is not carried forward.

Everything after `fight` is **keyword-only**, deliberately: the six helpers
disagreed about what their fourth positional argument meant, so a positional call
is exactly the mistake worth failing loudly on.

Two consequences worth knowing:

- **A test that patched `roll_duality` through a domain module now reaches
  nothing**, since the domain modules no longer call it. `content.spellcast` is
  the module to patch. Neither of the two domain-card test files does this - both
  keep determinism by giving the target a Difficulty of 0 or 1 instead - but this
  was flagged as a risk when the consolidation was first proposed, so it is worth
  saying where the answer is.
- **Veil of Night's printed ender became implementable.** "Until you cast another
  spell" was ruled to "until the caster's next action resolves" *because* no one
  place existed for a cast to pass through. There is one now. The ruling stands
  as made rather than being quietly changed; the difference is that a veiled PC
  swinging a weapon would keep the darkness where they currently lose it.

**Two roll sites were deliberately left alone.** Splendor's *Healing Hands* and
Grace's *Invisibility* both roll `roll_duality` by hand against a flat printed
Difficulty, and both target a willing creature rather than making an attack. They
could be folded into `spellcast(..., difficulty=N)`, and the tidiness argument
says they should - but doing so would newly expose them to `total_roll_bonus` and
`remake_action_roll`, which is a **behaviour change** rather than a
consolidation: content that spends Hope for a roll bonus would start firing on a
heal. Left as they are, and recorded here so the inconsistency is a decision
rather than an oversight.
