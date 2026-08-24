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

**Levels 1 and 2, all nine domains** - 45 cards. That is every card a level 2
party of any class combination could hold, so a new party composition can be
simulated without writing code first. Levels 3+ wait until a party reaches them.

## How porting works

The same process the adversary port settled on, and for the same reasons:

- **Batches of five.** One domain's level 1-2 slice is exactly five cards, so a
  batch is a domain.
- **Card text is taken from `.reference/abilities.json` and checked against the
  printed page** in the SRD PDF before the batch lands. The domain sections start
  at printed page **118**. The PDF renders two printed pages per sheet, so PDF
  page `n` shows printed `2n-2` and `2n-1` - to reach printed page `p`, read PDF
  page `(p + 2) / 2`. Roughly:
  Bone 122, Codex 124, Sage 130, Splendor 132 are **confirmed**; Arcana, Blade,
  Grace, Midnight and Valor fall either side of them at roughly 118, 120, 126,
  128 and 134. Adversaries are printed 80-100, equipment 50-53.
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

### Order it was done in

The five domains the Immareth sheets already draw from first - **Blade, Codex,
Sage, Splendor, Valor**, 14 cards - so every card landing was a loadout the
current party could actually swap to. Then the four that had no module at all:
**Arcana, Bone, Grace, Midnight**.

### What's next, when a party levels

**Level 3** is the natural next slice: two cards per domain, eighteen in all.
Nothing needs it until a party reaches level 3, which is why the scope stops
here. The batch process below applies unchanged.

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

**Not verified against the SRD PDF.** Card text came from
`.reference/abilities.json` only - the printed-page check the adversary port does
per batch hasn't been done for these five.

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
parameter this session). Worth pulling into one place.

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
