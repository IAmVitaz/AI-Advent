# AI Advent

<a name="day-1"></a>
<details>
<summary><strong>Day 1 — Script to Anki Deck</strong></summary>
<br>

A Python web app that converts scripts into Anki flashcard decks for spaced repetition learning.

[![Watch on YouTube](https://img.youtube.com/vi/R2LU-wSdPQg/0.jpg)](https://www.youtube.com/watch?v=R2LU-wSdPQg)

[GitHub →](https://github.com/IAmVitaz/ScriptToAnkiDeck)

</details>

---

<a name="day-2"></a>
<details>
<summary><strong>Day 2 — Response Control Comparison</strong></summary>
<br>

A simple Python web app with a split-panel chat interface that sends the same question to Claude twice — once with no constraints, once with explicit format, length limit, and stop sequence.

https://github.com/user-attachments/assets/549311e9-9428-47a9-8ea5-03430cdb5ad4

</details>

---

<a name="day-3"></a>
<details>
<summary><strong>Day 3 — Reasoning Mode Comparison</strong></summary>
<br>

A Python web app that takes one problem and solves it four different ways simultaneously, comparing the results side by side in a 2×2 panel grid.

The test problem: *"I have a metal cup with the bottom missing and the top sealed. How can I use this cup?"*

**The four approaches:**
1. **Direct** — plain prompt, no extra instructions
2. **Step-by-step** — prompt instructs the model to reason step by step
3. **Metaprompt** — model first generates an optimal prompt for the task, then solves using it
4. **Expert panel** — Analyst, Engineer, and Critic each provide their own solution

**Result:** Only the Expert panel (approach 4) surfaced the key insight — *inverted use* (turn it upside down and use it as a tube or funnel). The other three approaches listed conventional uses or declared the cup broken/unusable. Structured role diversity unlocked a creative angle that direct and chain-of-thought prompting missed.

https://github.com/user-attachments/assets/a4392ef7-f0a0-45fb-bed6-e8fc80dabe7c

</details>

---

<a name="day-4"></a>
<details open>
<summary><strong>Day 4 — Temperature Comparison</strong></summary>
<br>

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

</details>
