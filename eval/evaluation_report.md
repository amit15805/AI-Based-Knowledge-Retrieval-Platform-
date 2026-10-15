# End-to-End Evaluation Report (Milestone 4 / M4.2)

- Generated: 2026-10-08 20:16:55
- Server: http://127.0.0.1:8000
- Domains tested: 2 (python_notes, rag_paper)
- Total queries: 10  |  request failures: 0  |  LLM errors (e.g. rate limits): 0

## Overall

| Scope | Queries | Routing | Clarification | Unneeded clarif. | Evidence hit | Unavailable handled | Avg conf. | Avg time (s) |
|---|---|---|---|---|---|---|---|---|
| ALL | 10 | 100% | 100% | 0% | 67% | 50% | 66% | 2.14 |

Response time: avg 2.14s, median 1.93s, max 3.37s per query (includes 3 LLM calls).

## By domain

| Domain | Queries | Routing | Clarification | Unneeded clarif. | Evidence hit | Unavailable handled | Avg conf. | Avg time (s) |
|---|---|---|---|---|---|---|---|---|
| python_notes | 5 | 100% | 100% | 0% | 100% | 0% | 74% | 2.08 |
| rag_paper | 5 | 100% | 100% | 0% | 33% | 100% | 58% | 2.20 |

## By query type

| Expected type | Queries | Routing | Clarification | Unneeded clarif. | Evidence hit | Unavailable handled | Avg conf. | Avg time (s) |
|---|---|---|---|---|---|---|---|---|
| factual | 4 | 100% | 100% | 0% | 50% | 50% | 71% | 2.40 |
| procedural | 2 | 100% | 100% | 0% | 100% | n/a | 58% | 2.10 |
| comparative | 2 | 100% | 100% | 0% | 50% | n/a | 68% | 2.58 |
| ambiguous | 2 | 100% | 100% | n/a | n/a | n/a | n/a | 1.24 |

## What the columns mean

- **Routing** - Query Understanding Agent predicted the expected query type.
- **Clarification** - ambiguous queries triggered a follow-up AND clear queries did not.
- **Unneeded clarif.** - share of clear queries that wrongly asked a follow-up (lower is better).
- **Evidence hit** - at least one expected keyword appeared in the document answer or retrieved excerpts.
- **Unavailable handled** - queries whose answer is NOT in the documents were flagged low-confidence / ungrounded.
- **Avg conf.** - mean grounding confidence on answerable queries.

## Per-query detail

| # | Domain | Query | Expected | Predicted | Status | Conf. | Top source | Routing | Evidence | Time (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | python_notes | What is Python? | factual | factual | answered | 79% | PYTHON PROGRAMMING NOTES.pdf #14 | ok | yes | 2.73 |
| 2 | python_notes | How do I define a function in Python? | procedural | procedural | answered | 71% | PYTHON PROGRAMMING NOTES.pdf #74 | ok | yes | 2.37 |
| 3 | python_notes | What is the difference between a list and a tuple? | comparative | comparative | answered | 70% | PYTHON PROGRAMMING NOTES.pdf #208 | ok | yes | 1.79 |
| 4 | python_notes | Tell me more | ambiguous | ambiguous | needs_clarification | 0% | - | ok | - | 1.5 |
| 5 | python_notes | What is the capital of France? | factual | factual | answered | 36% | Large Language Models ConceptsAtkinson.pdf #354 | ok | - | 2.03 |
| 6 | rag_paper | What does RAG stand for? | factual | factual | answered | 63% | Retrieval-Augmented_Generation_RAG_Advances_and_Ch.pdf #12 | ok | NO | 3.26 |
| 7 | rag_paper | How does the RAG pipeline work step by step? | procedural | procedural | answered | 46% | Retrieval-Augmented_Generation_RAG_Advances_and_Ch.pdf #154 | ok | yes | 1.83 |
| 8 | rag_paper | Compare RAG with fine-tuning | comparative | comparative | answered | 65% | Retrieval-Augmented_Generation_RAG_Advances_and_Ch.pdf #138 | ok | NO | 3.37 |
| 9 | rag_paper | Explain it | ambiguous | ambiguous | needs_clarification | 0% | - | ok | - | 0.98 |
| 10 | rag_paper | What is the boiling point of water? | factual | factual | answered | 0% | - | ok | - | 1.56 |

## Items to investigate

- [python_notes] "What is the capital of France?" - out-of-document query was answered with high confidence
- [rag_paper] "What does RAG stand for?" - expected evidence not found
- [rag_paper] "Compare RAG with fine-tuning" - expected evidence not found
