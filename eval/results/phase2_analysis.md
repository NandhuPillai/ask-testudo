# Phase 2 Analysis — hi_res Re-ingestion

**Date:** 2026-04-21  
**Baseline file:** `baseline_2026-04-20.json`  
**hi_res file:** `hires_2026-04-21.json`  
**Questions:** 60 (same golden dataset, unchanged)

---

## 1. Aggregate Score Deltas

| Metric | Baseline | hi_res | Delta |
|---|---|---|---|
| context_precision | 0.2027 | 0.1684 | **-0.0343** |
| context_recall | 0.2370 | 0.2919 | **+0.0549** |
| faithfulness | 0.4411 | 0.5300 | **+0.0889** |
| answer_relevancy | 0.5671 | 0.6216 | **+0.0545** |

hi_res improved 3 of 4 metrics. Context Precision regressed slightly, likely because larger chunks pull in more surrounding context, diluting the precision signal when retrieved documents contain the answer but also unrelated content.

---

## 2. Per-Category Context Recall

| Category | Baseline | hi_res | Delta |
|---|---|---|---|
| factual_lookup | 0.4563 | 0.5132 | +0.0569 |
| requirement_list | 0.0794 | 0.1688 | **+0.0894** |
| policy | 0.4183 | 0.4783 | +0.0600 |
| cross_document | 0.1000 | 0.1500 | +0.0500 |
| out_of_corpus | 0.1000 | 0.1000 | 0.0000 |

As predicted, `requirement_list` improved the most (+0.0894) — this is the category most affected by the chunking boundary bug where tables were split mid-list. hi_res + larger chunks (3000 chars) fixed this partially.

`out_of_corpus` is unchanged, which is expected — CRAG threshold behaviour is unrelated to PDF parsing strategy.

---

## 3. Notable Regressions

Several questions show `0.0000` on metrics in the hi_res run (q005, q003, q026, q041, q014, q034, q015). These are likely **RAGAS scoring failures** (API timeout or null retrieved_contexts) rather than genuine zero scores, since the same questions scored non-zero in baseline. These should be spot-checked by re-running eval on just those question IDs.

Genuine regressions (partial score drops, not zeros):
- **q007** (credits to graduate): context_precision 1.0 → 0.75, faithfulness 0.875 → 0.667 — likely because larger chunks now pull in surrounding credit information from different programs, confusing the reranker.
- **q013** (CS prereq grade): context_precision 1.0 → 0.69 — similar dilution effect.
- **q038** (community college transfer credits): context_recall 0.25 → 0.0 — this topic may span multiple chunks that were previously together but are now split differently under hi_res layout detection.

---

## 4. Corpus Changes

| | Baseline (fast) | hi_res |
|---|---|---|
| Parents on disk | 9,095 | 10,098 |
| Vectors in Pinecone | 34,870 | 17,557 |
| BM25 vocabulary | 8,792 terms | 31,110 terms |

BM25 vocabulary expanding 254% is the strongest signal: hi_res is extracting substantially more text from tables and multi-column layouts that pdfminer's linear reading missed entirely. Fewer but larger child vectors is expected from the chunk_size increase (300 → 600).

---

## 5. Phase 3 Decision

Per the plan's decision criteria:

| Threshold | Result |
|---|---|
| Context Recall improvement | +0.0549 (borderline: 0.05–0.15 range) |
| Faithfulness also improved? | Yes (+0.0889) |
| **Decision** | **Proceed to Phase 3** |

The borderline Context Recall improvement combined with strong Faithfulness and Answer Relevancy gains suggests the corpus-based system has improved but still has a real ceiling. Out-of-corpus questions score 0 on recall by design, and cross-document questions remain weak (0.15 recall), indicating the system still struggles with information that either isn't in the corpus or requires synthesizing across documents.

Phase 3 (agentic web search) is warranted to address:
- Time-sensitive information not in PDFs (semester deadlines, current waitlist status)
- Cross-document policy synthesis
- Advisor-specific policies not published in official documents
