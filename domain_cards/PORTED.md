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

**Levels 1 to 5, all nine domains** - 99 cards, complete. That is every card a
level 5 party of any class combination could hold, so a new party composition can
be simulated without writing code first. Levels 6+ wait until a party reaches
them.

The scope grew from levels 1-2, then to 3, then to 4, then to 5, each time the
previous one was finished. Cards are ported **by level** rather than by domain: a level is the
slice a party actually occupies, and finishing one means no loadout at that level
can name a card nobody has written.

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

### Order it was done in



The five domains the Immareth sheets already draw from first - **Blade, Codex,
Sage, Splendor, Valor**, 14 cards - so every card landing was a loadout the
current party could actually swap to. Then the four that had no module at all:
**Arcana, Bone, Grace, Midnight**.

### What's next

**Levels 1 to 5 are complete.** **Level 6** is the next slice - two cards per
domain, eighteen more, and nothing needs them until a party reaches level 6. Every
domain's page has been read several times now, so the printed-page check is a
re-read rather than a hunt, and levels 6 to 10 all sit on the pages already used.

Worth knowing before starting it: **level 5 cost far more machinery than level 4
did**, which is the opposite of what the level 4 notes predicted. Four of the four
batches brought a new hook or a change to the fight loop - `move_rescind`, the
Hope Die swap's second reader, `damage_scaling`, `damage_typing`, a `dice/` field
and two loop changes. The cards stopped being variations on shapes that already
existed some time ago, and levels 6+ should be planned as two domains at a time
with a machinery bill expected rather than hoped against.

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
