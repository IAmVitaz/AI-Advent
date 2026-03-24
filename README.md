# AI Advent

## Table of Contents

**Week 1**
- [Day 1 — Script to Anki Deck](#day-1)
- [Day 2 — Response Control Comparison](#day-2)
- [Day 3 — Reasoning Mode Comparison](#day-3)
- [Day 4 — Temperature Comparison](#day-4)
- [Day 5 — Model Strength Comparison](#day-5)

**Week 2**
- [Day 6 — First Agent](#day-6)
- [Day 7 — Persistent Agent](#day-7)

---

<a name="day-1"></a>

## Day 1 — Script to Anki Deck

[↑ Back to top](#ai-advent)

A Python web app that converts scripts into Anki flashcard decks for spaced repetition learning.

[![Watch on YouTube](https://img.youtube.com/vi/R2LU-wSdPQg/0.jpg)](https://www.youtube.com/watch?v=R2LU-wSdPQg)

[GitHub →](https://github.com/IAmVitaz/ScriptToAnkiDeck)

---

<a name="day-2"></a>

## Day 2 — Response Control Comparison

[↑ Back to top](#ai-advent)

A simple Python web app with a split-panel chat interface that sends the same question to Claude twice — once with no constraints, once with explicit format, length limit, and stop sequence.

https://github.com/user-attachments/assets/549311e9-9428-47a9-8ea5-03430cdb5ad4

---

<a name="day-3"></a>

## Day 3 — Reasoning Mode Comparison

[↑ Back to top](#ai-advent)

A Python web app that takes one problem and solves it four different ways simultaneously, comparing the results side by side in a 2×2 panel grid.

The test problem: *"I have a metal cup with the bottom missing and the top sealed. How can I use this cup?"*

**The four approaches:**
1. **Direct** — plain prompt, no extra instructions
2. **Step-by-step** — prompt instructs the model to reason step by step
3. **Metaprompt** — model first generates an optimal prompt for the task, then solves using it
4. **Expert panel** — Analyst, Engineer, and Critic each provide their own solution

**Result:** Only the Expert panel (approach 4) surfaced the key insight — *inverted use* (turn it upside down and use it as a tube or funnel). The other three approaches listed conventional uses or declared the cup broken/unusable. Structured role diversity unlocked a creative angle that direct and chain-of-thought prompting missed.

https://github.com/user-attachments/assets/a4392ef7-f0a0-45fb-bed6-e8fc80dabe7c

---

<a name="day-4"></a>

## Day 4 — Temperature Comparison

[↑ Back to top](#ai-advent)

A Python web app that sends the same prompt to Claude 15 times simultaneously — 5 runs at each of three temperatures — and displays all results side by side so the effect of temperature is immediately visible.

**What temperature does:** at every generation step the model has a ranked list of candidate next words. Temperature controls how strictly it follows that ranking. At 0 it always picks the top word, producing the same output every time. As temperature rises it becomes willing to pick lower-ranked words, introducing variation and surprise.

**The three settings:**
- **0** — fully deterministic. Best for factual Q&A, code generation, classification.
- **0.5** — slight variation between runs; responses feel natural but consistent. Best for emails, summaries, translations.
- **1.0** — noticeable differences across every run; word choice, structure, and angle all vary. Best for creative writing, brainstorming, copywriting.

**Prompt used:** *"Continue with just ONE word: Once upon a time there lived a..."*

**Result:** the model is heavily biased toward "dragon" as the most probable completion. Over 25 runs per temperature the numbers made the effect undeniable:

| Temperature | Dragon | Other | Non-dragon rate |
|-------------|--------|-------|-----------------|
| 0.0 | 25 | 0 | 0% |
| 0.5 | 24 | 1 | 4% |
| 1.0 | 15 | 10 | 40% |

At temperature 0 the model locked onto "dragon" with zero deviation across all 25 runs. Temperature 0.5 broke out once. Temperature 1.0 escaped 10 times — producing words like "wizard", "princess", "witch", and others. The 5-runs-per-column layout turned an abstract concept into a concrete, countable experiment.

https://github.com/user-attachments/assets/593d5c09-75ad-4986-baf0-d84cb36c472f

---

<a name="day-5"></a>

## Day 5 — Model Strength Comparison

[↑ Back to top](#ai-advent)

A Python web app that sends the same prompt to three Claude models simultaneously — Haiku (weak), Sonnet (medium), and Opus (strong) — and displays each response side by side along with measured metrics: response time, token count, and estimated cost.

**The three models:**
- **Claude Haiku 4.5** — fast and cheap. In: $1.00/MTok · Out: $5.00/MTok
- **Claude Sonnet 4.6** — balanced. In: $3.00/MTok · Out: $15.00/MTok
- **Claude Opus 4.6** — most capable. In: $5.00/MTok · Out: $25.00/MTok

**Prompt used:** *"Explain the concept of black holes in simple terms. Include how they form, what happens at the event horizon, and one surprising fact."*

**Results:**

| Model | Time | Input tokens | Output tokens | Est. cost |
|-------|------|-------------|---------------|-----------|
| Haiku 4.5 | 8.19s | 35 | 267 | $0.001370 |
| Sonnet 4.6 | 15.08s | 35 | 357 | $0.005460 |
| Opus 4.6 | 15.06s | 35 | 332 | $0.008475 |

**Key observations:**
- Haiku finished nearly **2× faster** than Sonnet and Opus, and cost **6× less** than Opus
- All three models grasped the topic correctly — quality differences were stylistic, not factual
- Haiku used bullet points and short paragraphs; Sonnet structured numbered steps with bold emphasis; Opus wrote in flowing prose with richer analogies
- For factual explanation tasks at this complexity level, Haiku delivers comparable accuracy at a fraction of the cost and latency

https://github.com/user-attachments/assets/8b2e0cc5-b7af-45c1-838c-5cd3bcc0a8c6

---

<a name="day-6"></a>

## Day 6 — First Agent

[↑ Back to top](#ai-advent)

A Python web app implementing a simple stateful chat agent. Unlike previous days where each route made a raw API call, here the LLM interaction is fully encapsulated in an `Agent` class — it owns the conversation history, system prompt, and streaming logic. Flask acts as a thin HTTP adapter on top.

**Architecture:**
- `agent.py` — the agent entity: holds history, calls the API, yields streamed chunks and final stats. No Flask dependency — usable from CLI or any other context.
- `app.py` — three routes: serve UI, proxy chat through the agent, reset history.
- Chat UI with user/assistant bubbles, real-time streaming, and a metrics row after each response.

**Metrics shown after every message:** input tokens · output tokens · response time · memory (JSON size of full conversation history in KB)

https://github.com/user-attachments/assets/0d45c3c8-995a-4aa9-8bb7-4bd209f2f3ac

---

<a name="day-7"></a>

## Day 7 — Persistent Agent

[↑ Back to top](#ai-advent)

Extends the Day 6 agent with persistent conversation history. The agent saves the full message history to `history.json` after every reply and reloads it on startup — so a restart is invisible to the conversation.

**What changed from Day 6:**
- `Agent` writes history to disk after every assistant turn and loads it back on `__init__`
- `reset()` deletes the file alongside clearing memory
- New `GET /history` endpoint lets the frontend restore the chat UI on page load
- On browser open/refresh, all previous messages are re-rendered from saved history

**How persistence works:**
1. User sends a message → agent appends to `self.history`, streams reply, saves `history.json`
2. Server restarts → `Agent.__init__` reads `history.json`, history is fully restored
3. Next message is sent with the complete prior context — the model has no idea there was a restart

**Key insight:** the LLM itself is stateless — it has no memory between calls. "Persistence" is entirely about what you pass in `messages`. Saving and replaying that list is all it takes to make the agent feel continuous.

https://github.com/user-attachments/assets/afcb4fb9-c771-43af-afea-e179252a455e
