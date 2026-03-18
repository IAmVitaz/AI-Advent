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
<details open>
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
