# Presentation Script
## Walkthrough for the Data/AI Lead + Non-technical Consultant

**Target: 15 min walkthrough + Q&A. Lead with the dollar figure, end with the question.**

---

### Slide 1 — The one sentence (30 sec)

> "Before I show you any code: the client is sitting on $20.5 million of next-month revenue at stockout risk, $49 thousand of inventory they bought and never launched, and an ops team that has stopped trusting their own system. Here's how I got to those numbers."

**Speaker note:** Don't lead with methodology. Lead with the dollar. Methodology earns its keep only if the numbers are interesting.

---

### Slide 2 — The problem in one picture (1 min)

*Show a three-box diagram:* POS (CSV, messy) → ??? → Inventory (Excel + Notes) — and off to the side, E-commerce (JSON, separate ID space).

Script:
> "Three systems, three people extracted them at different times, none of them agree. No shared identifier between e-commerce and the other two. My first job was: can I even trust a single unified view? If I can't, none of the rest matters."

---

### Slide 3 — How I reconciled them (2 min)

Three bullets:
- **SKU normalization.** POS SKUs came in five flavors: `SKU-50128`, `SKU50128`, `50128`, `050128`, `50128C`. A single function canonicalizes all of them. ~96% of POS SKUs match inventory after that.
- **E-commerce has a totally different ID namespace.** `ECOM-634885` means nothing to the POS system. The only bridge is product name. I used fuzzy string matching with an 88/100 cutoff — matched all 212 unique e-commerce products to inventory. I tuned that threshold by hand-reviewing the close calls.
- **Conflict resolution.** When systems disagree on quantity, I use a documented priority: ops notes > inventory system > derived. It's configurable per client.

**For the non-technical consultant:** "Think of it like reconciling three ledgers from three different bookkeepers, each using different abbreviations. The boring part is getting the names to match; that's 80% of the work."

---

### Slide 4 — Finding 1: $20.5M at stockout risk (2 min)

Show the top-10 table from `stockout_risk.csv`.

> "These ten products are effectively out of stock right now. They're moving 30-to-40 units a day and have zero to eight on hand. Expediting these POs alone is worth about a million dollars in recovered 30-day revenue. The full list of 250 at-risk SKUs is in the notebook."

**If asked how we computed velocity:** last-30-days sell-through, both channels, returns netted, then `qty_on_hand / daily_velocity = days of cover`. Anything under 14 days flagged.

---

### Slide 5 — Finding 2: The unlaunched-product story (1 min)

Show the dead-inventory table — every row literally says "New Product N — Not Yet Active."

> "Fifteen products they paid for and stocked but never put on sale. It's only $49K of capital — small compared to the stockout number. But it's a *tell*. Something in their launch workflow is broken: inventory arrives before marketing, merchandising, or pricing is ready. Worth a conversation with the CMO."

**Why this matters in the interview:** shows judgment. You're recognizing the small dollar finding is a bigger organizational story.

---

### Slide 6 — Finding 3: The shadow accounting system (2 min)

Show 3-4 rows from the Notes column:
- `Physical count: 89 (system wrong)`
- `Reserved for customer order`
- `Display only - do not sell`
- `Adj: -14 per Lisa 1/14`

> "Their ops team stopped trusting the inventory system. They're running a parallel accounting system in a spreadsheet Notes field. 39 SKUs have hand-written counts that disagree with the system by $13K. And notice the second and third notes — *'reserved for customer order'* and *'display only'* — those units shouldn't be counted as sellable at all, but the system counts them. This is a control environment issue, not a data issue."

**Then drop the bomb:**
> "Also: there's a SKU literally called `SAMPLE` that moved ten thousand dollars of real revenue through the POS. Either it's a register-test SKU cashiers have been using for live transactions, or a real product that was never set up properly. Either way, somebody needs to know."

---

### Slide 7 — The AI component (2 min)

> "You asked to see how I use AI. I use it where it actually helps and avoid it where it doesn't."

Two places:
1. **Triaging the ops Notes column.** 80% of notes match the `Physical count: N` pattern — that's a regex. But the long tail — *'Reserved for customer order'*, *'Awaiting vendor credit'*, *'Adj: -14 per Lisa 1/14'* — is genuine free text. The LLM classifies those into a typed taxonomy with a recommended action. Output is Pydantic-validated so I can trust the shape.
2. **CFO narrative.** I pass the raw numbers dict in, the LLM produces a paragraph. The numbers never come from the LLM — only the prose.

**What I didn't trust the LLM for:**
- Any numeric output. All dollars are pandas.
- Picking which SKU matters. That's a deterministic sort.
- Cross-source fuzzy matching. RapidFuzz is deterministic, tunable, and good enough at this N.

**What to flag for the reviewer:** "I ran it offline first. The offline fallback produces the same structured output, just less nuanced recommendations. This was deliberate — the notebook works without an API key so your reviewers can run it."

---

### Slide 8 — The reusable design (2 min)

Show a table:

| Module | Reusable? |
|---|---|
| `normalize.py` (SKU, dates, names) | Yes — industry-generic |
| `reconcile.py` (cross-source matching) | Yes — works on any two-namespace product system |
| `insights.py` (stockout, dead, gaps) | Yes — thresholds are config |
| `ai_insights.py` (LLM + Pydantic) | Yes — no client facts hardcoded |
| `config.py` | **Client-specific** — intentionally isolated |
| `load_inventory` column renames | **Partially** — would factor into YAML for production |

> "The brief said 'evidence that you think in components,' not 'build a framework.' So I isolated the per-client stuff into one file. The next consultant changes `config.py` and the column-rename dict; everything else just works."

---

### Slide 9 — What I didn't do / would do next (1 min)

> "I stopped at the three-hour mark. Things I consciously skipped:"
- Unit tests for `normalize_sku` — it has enough branches to regress.
- Per-client loader config as YAML (today the column renames are hardcoded in Python).
- A proper reorder-point calculator keyed to service level rather than the client's flat reorder numbers.
- A dashboard. You didn't ask for one, and the notebook + CSVs in `outputs/` cover the narrative.

---

### Slide 10 — Recommendations for Monday (30 sec)

1. Expedite POs for the top 10 stockout SKUs. ~$1M recovered.
2. Return or liquidate the 15 unlaunched products. ~$49K working capital.
3. Reconcile the 39 ops-override SKUs to physical counts.
4. Fix three POS entry rules: one SKU format, customer-ID required, explicit return flag.

> "That's the week-one action list. Questions?"

---

## Q&A prep — likely questions

**"Why 14 days cover? Why 60 days dead?"**
Industry rules of thumb for a 2-week reorder lead time and a seasonal sell-through window. Both are `config.py` constants — change them per client.

**"How do I know your fuzzy match is right?"**
Spot-checked the close calls at threshold 85 and found false positives ("Classic Pen Holder" vs "Classic Pencil Holder"). Bumped to 88 until false positives disappeared. 100% of e-com products matched — which also means I should sanity-check for false-positive over-matching; worth a second pass with more time.

**"What if the e-commerce data is just incomplete rather than the channel being under-invested?"**
Can't tell from this data alone. That's exactly why I flagged it as "worth 15 minutes with the e-commerce vendor" rather than as a conclusion. Showing the distinction between a finding and a hypothesis.

**"Why Anthropic and not OpenAI / local model?"**
Either works — the Pydantic contract makes the provider swappable. I used Anthropic because that's what I had an API key for. For a real engagement I'd default to whatever the client's data-governance posture allows.

**"What's the biggest risk in your pipeline?"**
The fuzzy-match threshold. 88 worked on this client; a different product catalog with more near-duplicates could produce false joins that poison downstream analytics. I'd add a manual review step for any new client until the threshold is validated.

**"What would you want if you had more time?"**
Unit tests for `normalize_sku`, YAML per-client config, a service-level reorder-point calculator, and a tiny Streamlit dashboard for ops — the notebook is right for me, a dashboard is right for them.

---

## One last thing — for the non-technical consultant

When they ask anything, reframe it in business terms before the answer. Example:

Q: "How did you match the e-commerce products?"
A: "Nobody entered a lookup table. I had the software compare product names and accept matches that were close enough — like a fuzzy spell-checker. I set the strictness so 'Classic Pen Holder' wouldn't get confused with 'Classic Pencil Holder.' That's how we got from three disconnected systems to one unified view."

The interview is partly a test of whether you can switch registers. Practice it.
