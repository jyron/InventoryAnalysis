# Inventory Health — Executive Summary
**Prepared for the CFO · 2024 data pull · 1-page**

## The headline

**$20.5M of next-month revenue is at stockout risk, $49K of working capital is parked in products you never launched, and your own ops team doesn't trust your inventory system — they're keeping a shadow count in a spreadsheet.**

---

## What we found

| Finding | Size | Why it matters |
|---|---|---|
| **250 of 265 SKUs have <14 days of cover** at current sell-through. Ten are effectively stocked out today. | ~$20.5M in potential lost 30-day revenue | Every day you're out of a fast-mover is pure margin walking out the door. |
| **15 "New Product" SKUs stocked but never activated.** | $49K of idle working capital | Something is broken in your product-launch workflow — inventory is arriving before the go-to-market does. |
| **Ops team is overriding the system.** 39 SKUs carry a handwritten "physical count" in a Notes field that disagrees with the system. | $13K immediate inventory variance; much larger trust problem | Decisions based on the inventory system are being made on numbers ops already knows are wrong. |
| **A SKU literally named `SAMPLE` generated $10,000 of real POS revenue.** | $10K orphan revenue, hard to quantify the rest | Either it's a register-test SKU operators used for live sales, or a real product no one set up. Both are control-environment issues. |
| **Online is only 4% of revenue** vs. ~15% for comparable US retailers. | Either the export is incomplete, or the channel is materially under-invested | Worth 15 minutes with the e-commerce vendor to confirm. |

## What the data told us about your systems

- **25% of POS transactions have no customer attached.** Operators are skipping the loyalty step. You cannot analyze repeat-purchase behavior until this is fixed.
- **8% of POS rows have negative quantities** with no flag for return vs. error. Your finance team can't tell the difference without pulling the original ticket.
- **SKU formats are inconsistent** across POS (`SKU-50128`, `SKU50128`, `50128`, `050128`, `50128C` all appear). Enforce one format at entry.
- **Three different date formats** in a single column of the POS export. This is a vendor-side bug.

## What to do Monday morning

1. **Expedite purchase orders for the top 10 stockout-risk SKUs.** List attached. Worth ~$1M in recovered 30-day revenue.
2. **Liquidate or return the 15 unlaunched "New Product" SKUs** unless launch dates are imminent. Recovers ~$49K of working capital immediately.
3. **Reconcile the 39 ops-override SKUs** against the physical counts your team already did. Free accuracy.
4. **Fix three POS data-entry rules:** one SKU format, customer-ID required, explicit return flag.

---

## What we built

A Python package (`retail_reconcile/`) that ingests your three source systems, normalizes identifiers, reconciles discrepancies, and produces this report. Written to be reused on your next retail engagement — client-specific rules are isolated to one config file. Full methodology in the accompanying notebook.
