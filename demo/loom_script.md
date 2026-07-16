# PolicyLens AI — 3-Minute Demo Script
### For Loom recording | Target: AI PM hiring managers

---

## SETUP (before hitting record)

- Terminal 1: backend running on port 8000
- Terminal 2: simulated agent running on port 8001
- Terminal 3: ready to run `python demo/run_demo.py`
- Browser: have `localhost:3000` open showing the rule review UI
- Font size bumped to 18pt in terminal
- Clear all terminal history

---

## [0:00 – 0:20] Hook

**Show:** blank terminal, nothing running yet

> "Most teams find out their AI agent violates company policy the hard way —
> a customer gets the wrong refund, a ticket goes to the wrong team, someone
> screenshots it and posts it on Twitter.
>
> PolicyLens catches those violations before the agent ever touches production.
> Let me show you how it works."

---

## [0:20 – 0:45] The problem — one sentence setup

**Show:** split screen — left: shopfast_policy.txt open in editor, right: terminal

> "This is a real scenario from a design partner session.
> ShopFast has a 7-section returns policy — nuanced rules around Final Sale items,
> Apple products, marketplace sellers, loyalty points purchases.
>
> They built an AI refund agent. Smart model, well-written prompt.
> But the agent had never been grounded in *this* specific policy.
> Nobody had tested it against these exact rules.
>
> Here's what PolicyLens does in under two minutes."

---

## [0:45 – 1:15] The demo — run it live

**Action:** run `python demo/run_demo.py` in Terminal 3

**Show:** watch the output scroll — narrate the steps as they happen

> "First, it uploads the policy as plain text — you can also drop in a PDF
> or a Notion URL. Then it calls Claude to extract structured, testable rules."

*[pause while extraction runs — ~8 seconds]*

> "Seven rules extracted. One ambiguity flag — the loyalty points rule has
> conditional logic that two engineers might interpret differently.
> PolicyLens surfaces that *before* you test against it.
> We resolve it in plain language, then approve all rules."

*[scroll to scenario generation]*

> "Now it generates test scenarios — normal cases, edge cases, and adversarial
> scenarios that combine two rules at once. Eighteen scenarios total,
> each with an expected action the agent must match."

*[scroll to evaluation starting]*

> "And now the evaluation. PolicyLens calls the simulated agent —
> this is a stand-in for any real agent endpoint — once per scenario.
> It uses a deterministic checker first, then an LLM judge for anything
> inconclusive or critical-tier."

---

## [1:15 – 1:50] The findings — the money moment

**Show:** evaluation results printing, then findings section

*[wait for findings to print — point at each one]*

> "Five violations. Two critical.
>
> Look at this first one — Final Sale item arrives damaged.
> Policy says store credit only. The agent issued a full cash refund.
> That's a real financial loss on every ticket where this happens.
>
> Second critical: loyalty points purchase. Policy requires a split refund —
> cash portion back to the card, points portion as store credit.
> Agent issued the full amount as cash. Every single time.
>
> Two major violations: Apple products get a January 31 holiday deadline,
> policy says January 15. And marketplace items — the agent processed a
> direct refund instead of routing to the seller, which creates a dispute
> liability ShopFast can't recover."

**Show:** recommendation printing — NOT READY

> "PolicyLens verdict: Not Ready. Do not launch."

---

## [1:50 – 2:20] The report and sign-off

**Show:** release report and dual sign-off section

> "It builds a launch-readiness report: decision accuracy, critical violation
> rate, scenario coverage. And it requires dual sign-off before the release
> can be marked approved — QA lead plus VP Operations.
>
> Both sign here. The release is approved — but the recommendation is locked.
> The team knows exactly what to fix before this agent goes to production."

**Show:** browser — switch to localhost:3000, rule review table

> "On the frontend, the rule review table gives the policy team visibility
> into every extracted rule, its source citation, and its test status.
> No more 'we think it's compliant' — every rule has a test result attached."

---

## [2:20 – 2:50] The insight

**Show:** back to terminal — final summary printed

> "Here's the thing that matters for an AI PM role:
>
> This agent *sounded* correct on every one of these violations.
> It was polite. It gave a reason. The response looked fine in a manual review.
> You would not catch these without systematic, policy-grounded testing.
>
> PolicyLens makes that testing repeatable. You run it before every deploy.
> When the team fixes the prompt, you re-run the evaluation and watch
> the recommendation flip from Not Ready to Ready.
> The version comparison shows exactly which failures were resolved
> and whether any new ones appeared.
>
> That's the loop: extract, test, find, fix, verify, ship."

---

## [2:50 – 3:00] Close

**Show:** terminal with final output visible

> "PolicyLens AI. Pre-production compliance testing for AI agents.
> Built in six sprints — FastAPI backend, Claude API for extraction and judging,
> Next.js rule review UI, full audit log, dual sign-off workflow.
>
> The code is on GitHub. Thanks for watching."

---

## RECORDING NOTES

- Speak slower than feels natural — demos always sound rushed on playback
- Pause for 1–2 seconds after each finding prints before narrating it
- If extraction or evaluation runs longer than expected, that's fine — fill with
  "Claude is working through the policy…" rather than silence
- The "money moment" is the two critical findings — slow down there, let them land
- Don't apologize for terminal output — it reads as confidence

## TITLE FOR LOOM

`PolicyLens AI — Catching AI Agent Policy Violations Before Production (3 min)`

## THUMBNAIL SUGGESTION

Pause on the frame where "✗ NOT READY — DO NOT LAUNCH" prints in red.
That's the visual that tells the whole story.
