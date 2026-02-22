# Press Kit -- Mandarin

Last updated: 2026-02-21

This document contains everything a journalist, blogger, or podcast host needs to cover Mandarin. If anything is missing, contact press@mandarin.app.

---

## 1. Company/Product Overview

### Short Boilerplate (for tight placements)

Mandarin is a desktop and web application for adult Chinese learners who want honest progress tracking and serious drill-based study. It covers HSK levels 1 through 9 with 12 drill types, a graded reader, extensive listening, and per-skill diagnostics -- all running deterministically with zero AI tokens at runtime. Free for HSK 1-2. Pro access is $12/month.

Mandarin was built by a solo developer who started learning Chinese as an adult and could not find a tool that distinguished between words you recognize and words you actually know. The result is a system where reading feeds drilling, every metric is defensible, and nothing exists to manufacture a feeling of progress that is not real.

### Expanded Boilerplate

Mandarin is an adaptive Chinese learning application built for adults who treat language study as a serious, long-term project. The app tracks learner progress across vocabulary, listening, reading, tone accuracy, and grammar as separate skills -- not a single blended score -- and uses a modified FSRS scheduling algorithm with Bayesian confidence dampening to ensure that mastery is earned, not inflated by a few lucky sessions.

The product's defining feature is its "cleanup loop": words encountered during graded reading flow directly into drill sessions across 12 exercise types, including tone discrimination, cloze deletion, audio matching, sentence construction, and speaking drills with tone grading. This closes the gap between passive reading and active recall that most language apps leave open.

At runtime, Mandarin uses zero calls to large language models. All scheduling, scoring, content selection, and feedback is deterministic -- computed from the learner's own data using algorithms derived from memory science research. The content library includes 299 hand-curated vocabulary items with context notes, 30+ dialogue scenarios, 45+ graded reading passages, 26 integrated grammar points, and a media shelf with level-matched recommendations for Chinese podcasts, shows, and books.

The app runs as a web application and a desktop application (via Tauri), with all learner data stored locally on-device. There is no account creation required to start. The free tier includes full functionality for HSK 1-2 content. Pro access ($12/month) unlocks HSK levels 1 through 9, all drill types, and all features. There is no annual upsell, no tiered pricing, and no feature gating on the free plan beyond content scope.

---

## 2. Fact Sheet

| Category | Detail |
|---|---|
| **Product name** | Mandarin |
| **Character** | 漫 (man) |
| **Tagline** | Patient Chinese study |
| **Launch date** | TBD |
| **Platforms** | Web (any modern browser), Desktop (macOS, Windows, Linux via Tauri) |
| **Pricing** | Free (HSK 1-2, all drill types) / Pro $12/month (HSK 1-9, all features) |
| **Tech stack** | Python, SQLite, Flask, Web Audio API, Tauri (desktop) |
| **AI at runtime** | None. Zero LLM API calls. All logic is deterministic. |
| **Drill types** | 12 (recognition, production, cloze, tone pair, sentence construction, audio matching, speaking, and more) |
| **HSK coverage** | Levels 1-9 (aligned to HSK 3.0 standard) |
| **Grammar points** | 26, integrated into drills |
| **Vocabulary items** | 299 seed items (HSK 1-3) with hand-written context notes |
| **Reading passages** | 45+ graded passages |
| **Dialogue scenarios** | 30+ |
| **Scheduling algorithm** | Modified FSRS with Bayesian confidence dampening |
| **Data storage** | Local, on-device. No cloud account required. |
| **Offline support** | Yes |
| **Team size** | 1 |
| **Founded** | 2026 |
| **Website** | mandarin.app |
| **Press contact** | press@mandarin.app |

---

## 3. Founder Story

The founder began studying Mandarin as an adult, starting from zero -- no heritage connection, no immersion environment, no university program. Just evening study sessions after work, using whatever tools were available.

The frustration came gradually. Flashcard apps could drill vocabulary but had no way to connect reading to recall. Gamified apps reported progress that did not match reality -- high streaks and green progress bars, but an inability to understand a simple WeChat message. Diagnostic tools did not exist; no app could say "your vocabulary is HSK 3 but your listening is HSK 2, and here is what to do about it." The gap between studying Chinese and actually knowing Chinese was structural, and no combination of existing tools closed it.

So the founder opened a text editor and started building. Not a startup -- a tool. First for personal use: a system that would track what was actually known versus what had merely been seen, schedule reviews based on real recall data, and connect the experience of reading Chinese directly to the discipline of drilling it. The core insight was simple: if you look up a word while reading, that word should become practice -- not a flashcard, but multi-skill practice across different cognitive demands.

What started as a personal study tool became something more complete over months of daily use. Every feature was added because the founder needed it: tone grading because tones were slipping without feedback, per-skill diagnostics because listening was falling behind reading and the data made that visible, adaptive scheduling because some evenings allowed thirty minutes and others allowed ten. The result is a product shaped entirely by one learner's real needs, tested against daily use, with no feature that exists to satisfy a product roadmap or an investor's growth metric. It is a tool built by someone who uses it every day and has no reason to make it dishonest.

---

## 4. Product Screenshots Spec

The following six screenshots represent the product's core experience. All screenshots should be captured from the running application, not mocked up. Capture both light and dark mode variants of each.

**Screenshot 1: Dashboard**
The main session view after login. Shows today's study plan: items due for review, skill balance summary, and session length estimate. The "Civic Sanctuary" aesthetic should be visible -- warm stone background, Cormorant Garamond headings, clean typographic hierarchy. No cartoon elements, no mascots, no gamification artifacts.

**Screenshot 2: Drill in Action**
A tone pair drill or cloze deletion drill mid-session. The learner has answered a question; the screen shows the result with the correct answer, pinyin, and the learner's response. Feedback is factual (correct/incorrect with the right answer shown), not celebratory. The interleaving indicator should be visible if present.

**Screenshot 3: Graded Reader**
A reading passage at HSK 2 or 3 level with one word tapped for inline gloss. The gloss shows pinyin, definition, and a brief context note. The passage text should be set in Noto Serif SC. The surrounding UI should demonstrate the reading-to-drill connection -- a visible indicator that looked-up words will appear in upcoming drills.

**Screenshot 4: Progress and Diagnostics**
The multi-skill diagnostic view showing separate HSK-level estimates for vocabulary, listening, reading, and tone accuracy. At least two skills should show different levels (e.g., vocabulary at HSK 3, listening at HSK 2) to demonstrate the honest, per-skill tracking. Include the HSK projection timeline if visible.

**Screenshot 5: Dark Mode**
Any core view (dashboard or reading) in dark mode. The warm dark palette (not pure black) should be clearly distinct from the light mode. Demonstrates that the app is designed for evening study sessions -- warm tones, readable contrast, no bright UI elements.

**Screenshot 6: HSK Projection**
The forecasting view showing estimated dates for reaching upcoming HSK levels, based on current pace and accuracy. The projection should include the multi-criteria breakdown (vocabulary readiness, listening readiness, etc.) to show that readiness is not a single number.

**Technical specs for screenshots:**
- Resolution: 2560x1600 (retina) or 1280x800 (standard), PNG format
- No browser chrome unless showing the web app specifically
- No personal data visible (use a demo account or redact)
- File naming: `screenshot-[name]-[light|dark].png`

---

## 5. Logo and Brand Assets

All logo files are located in `marketing/assets/`. The following files are available for press use:

### Available Files

| File | Use case |
|---|---|
| `logo-mark.svg` | App icon / standalone mark (漫 character) |
| `logo-mark-dark.svg` | Mark for use on dark backgrounds |
| `logo-horizontal.svg` | Full logo with wordmark, horizontal layout |
| `logo-horizontal-dark.svg` | Horizontal logo for dark backgrounds |
| `logo-wordmark.svg` | Text-only wordmark ("Mandarin") |
| `logo-wordmark-dark.svg` | Wordmark for dark backgrounds |
| `logo-monochrome.svg` | Single-color version for limited-color contexts |
| `logo-app-icon.svg` | Square app icon for store listings and favicons |
| `logo-favicon-16.svg` | 16px favicon |
| `logo-favicon-32.svg` | 32px favicon |

### Usage Guidelines

**Clear space:** Maintain a minimum clear space around the logo equal to the height of the 漫 character on all sides. No other graphic elements, text, or edges should intrude into this space.

**Minimum size:** The horizontal logo should not be reproduced smaller than 120px wide (digital) or 30mm wide (print). The mark alone should not be smaller than 24px (digital) or 6mm (print).

**Do not:**
- Stretch, compress, or distort the logo in any direction
- Rotate the logo
- Apply drop shadows, glows, or other effects
- Recolor the logo beyond the provided variants (light, dark, monochrome)
- Place the light logo on a light background or the dark logo on a dark background
- Crop or partially obscure the logo
- Recreate or approximate the logo using other typefaces

**Background guidance:** The standard logo is designed for light, warm backgrounds (#F2EBE0 or similar). Use the dark variant on backgrounds darker than 50% luminance. Use the monochrome variant when color reproduction is limited (newsprint, single-color contexts).

**Raster exports:** If you need PNG or JPG versions at specific resolutions, contact press@mandarin.app with the required dimensions.

---

## 6. Press Release Template

*For use on launch day. Fill in bracketed fields before distribution.*

---

**FOR IMMEDIATE RELEASE**

### Mandarin Launches as a Quiet Alternative to Gamified Chinese Learning Apps

*A solo-built study tool for adults who want honest progress tracking, not streaks and leaderboards*

**[CITY], [DATE]** -- Mandarin, a Chinese learning application built by a solo developer, launches today as a desktop and web tool for adult learners studying HSK levels 1 through 9. The app offers 12 drill types, a graded reader, extensive listening practice, and per-skill diagnostics -- with zero artificial intelligence at runtime.

Unlike gamified language apps that blend progress metrics into a single encouraging score, Mandarin tracks vocabulary, listening, reading, and tone accuracy as separate skills, each with its own HSK-level estimate. The system uses a modified FSRS scheduling algorithm to determine review timing based on each learner's actual recall data, and applies Bayesian confidence dampening to prevent premature mastery ratings.

The app's core mechanism -- what the developer calls the "cleanup loop" -- connects reading directly to drilling. Words looked up during graded reading passages automatically appear in subsequent drill sessions across multiple exercise types. The intent is to close the gap between encountering a word in context and being able to recall, produce, and hear it reliably.

**[Founder quote placeholder:]** *"[Insert a 1-2 sentence quote from the founder about why they built the app and what makes it different. Keep the tone factual, not promotional.]"*

**Availability and Pricing:**
Mandarin is available now at mandarin.app. The free tier includes full functionality for HSK 1-2 content across all drill types. Pro access is $12/month and unlocks HSK levels 1 through 9 with all features. There is no annual plan requirement, no tiered pricing, and no feature limitations on the free tier beyond content scope.

**About Mandarin:**
Mandarin is a Chinese learning application for adults who want measurable, honest progress in reading, listening, and speaking Mandarin Chinese. Built by a solo developer who studies Mandarin daily, the app uses deterministic algorithms -- not generative AI -- to schedule reviews, score performance, and select content. All learner data is stored locally on-device. More information at mandarin.app.

**Press Contact:**
press@mandarin.app

---

## 7. Media Contact

**Press inquiries:** press@mandarin.app

**Response commitment:** All press inquiries receive a response within 24 hours. For time-sensitive requests (same-day deadline), note the urgency in the subject line.

**What we can provide on request:**
- High-resolution logo files in any format (SVG, PNG, JPG, EPS)
- Product screenshots at specific resolutions or showing specific features
- A written Q&A on any aspect of the product, technology, or development process
- A call or video interview with the founder (scheduling dependent on availability)
- Access to a demo account for hands-on review
- Advance access to the product under embargo (see Section 10)

**What we ask:**
- Please use the official product name "Mandarin" (capital M, no article -- not "the Mandarin app")
- Please link to mandarin.app when referencing the product online
- If quoting the founder, please use "the founder of Mandarin" rather than a personal name

---

## 8. Talking Points

For interviews, podcast appearances, and media conversations. These are not scripted answers -- they are the core ideas worth communicating, in whatever order fits the conversation.

1. **The gap between studying and knowing.** Most language apps optimize for engagement -- time in app, daily streaks, completion rates. These metrics correlate loosely, at best, with actual language ability. Mandarin was built to track what you can actually do: recall a word under time pressure, hear a tone correctly, read a sentence without help, produce a phrase from memory. These are different skills, and the app measures them separately.

2. **Why zero AI at runtime matters.** Generative AI is useful for building content. It is unreliable for delivering it. A drill that gives you a different answer depending on when you ask it is not a drill -- it is a guess. Every piece of feedback in Mandarin is computed deterministically from the learner's data. The answer is the same at 2am as it is at 2pm. That consistency is the foundation of trust.

3. **The cleanup loop.** The single most important feature is also the simplest to explain: when you read Chinese in the app and look up a word, that word becomes your next practice session. Not a flashcard -- multi-skill practice across different exercise types. Reading feeds drilling. Drilling improves reading. The loop is the product.

4. **No streaks, no guilt, no gamification.** Streaks measure dedication to an app, not progress in a language. Mandarin has no streaks, no XP, no hearts, no leaderboards, and no push notifications. If you miss a day, the app does not comment on it. It adjusts your schedule and continues. The relationship between the learner and the tool should not include guilt.

5. **Built by a learner, not a team.** The founder studies Mandarin daily and uses the app as their primary study tool. Every feature exists because the founder needed it. There is no product committee, no A/B testing for engagement metrics, no growth team. The question that drives development is: "Does this make my study sessions more effective?" If the answer is no, it does not ship.

6. **Honest diagnostics over comfortable metrics.** The app will tell you that your vocabulary is HSK 3 but your listening is HSK 2. It will not average those into an encouraging "HSK 2.5." The per-skill breakdown is the most valuable data the app produces, because it tells you exactly where to spend your limited study time. Most learners discover their skills are more lopsided than they expected.

7. **The market is underserved, not empty.** There are many Chinese learning tools. There are very few that treat adult learners as adults, track multiple skills separately, connect reading to drilling, and do it all without gamification or AI hallucinations. The competition is not Duolingo -- it is the combination of Anki, Pleco, a textbook, and a spreadsheet that serious learners are already using. Mandarin replaces that stack with a single tool.

---

## 9. Common Questions from Press

**Q: Why no AI? Every edtech product is adding AI right now.**

A: AI was used during development -- for content creation, for testing, for research. At runtime, the app uses none. The reason is reliability. When a learner gets feedback on a drill, that feedback needs to be correct every time, computed from their actual data, and reproducible. Generative models are probabilistic; they give different answers to the same prompt. A scheduling algorithm cannot be probabilistic. A tone grading system cannot hallucinate. The things that matter most in a learning tool -- scoring, scheduling, feedback -- are exactly the things where deterministic computation outperforms generative AI.

**Q: How do you compete with Duolingo? They have hundreds of millions of users.**

A: We do not compete with Duolingo in the way that question implies. Duolingo is an engagement product with a language learning skin. It optimizes for daily active users and retention metrics. We optimize for measurable skill improvement. The audiences overlap less than you might expect. Our users are people who have already tried Duolingo and found that their streak did not translate into ability. They are looking for something more rigorous, and they know it.

**Q: Why is the free tier so generous? HSK 1-2 is a lot of content.**

A: Because the product should prove itself before asking for money. The free tier is not a crippled trial -- it includes all 12 drill types, the full adaptive scheduling algorithm, the graded reader, diagnostics, and every feature the paid tier has. The only difference is content scope. A learner working through HSK 1-2 gets the complete experience. If the app is good, they will pay to continue. If it is not good enough, they should not have to pay to find that out.

**Q: Can one person really build and maintain a product like this?**

A: The product is intentionally scoped for solo maintenance. The tech stack is simple: Python, SQLite, Flask. There is no microservice architecture, no complex cloud infrastructure, no machine learning pipeline to retrain. Content is hand-curated, not generated at scale. The tradeoff is that the content library grows slowly -- but it grows carefully, with context notes and usage information that automated systems do not produce. A solo developer who uses the product daily catches problems that a larger team with less direct engagement might not.

**Q: What is your business model? Is $12/month sustainable for a solo product?**

A: The cost structure is minimal. There are no AI API costs, no large engineering team, no office, no investor obligations. The infrastructure is a static site and a lightweight server. At even modest subscriber counts, the economics work. The goal is not venture-scale growth -- it is a sustainable product that serves its users well and supports its developer. That is a different business model than most edtech companies, and it requires a different scale to work.

**Q: Who is your target user?**

A: Adults, typically 25-45, who are studying Chinese seriously and have been at it long enough to know what their current tools lack. Many are using three or four tools simultaneously -- Anki for flashcards, Pleco as a dictionary, a textbook for structure, and a spreadsheet to track their own progress. They are spending more time managing their study system than actually studying. Mandarin replaces that stack with a single integrated tool.

**Q: Why Chinese specifically? Will you expand to other languages?**

A: Chinese has specific challenges that general-purpose language apps handle poorly: tonal discrimination, character recognition, the large gap between spoken and written registers, and the sheer volume of characters required for functional literacy. Building for Chinese specifically means the drill types, the scoring, and the diagnostics can be tailored to these challenges rather than abstracted to fit every language equally. There are no current plans to expand to other languages. Doing one language well is more valuable than doing ten languages adequately.

**Q: What happens to my data? Do you sell it?**

A: All learner data is stored locally on the user's device. The app does not require an account to use. There is no analytics pipeline collecting usage data, no third-party tracking, and no data sales. The founder's position is straightforward: study data is personal, and the app has no business model that requires monetizing it.

**Q: How is the content created? Is it AI-generated?**

A: The vocabulary items, context notes, dialogue scenarios, and reading passages are hand-curated. AI tools were used during the content creation process -- for drafting, for checking, for generating initial variations -- but every item was reviewed, edited, and approved by a human who studies Chinese. The distinction matters because AI-generated language content often contains subtle errors in register, collocation, or usage that a fluent reader would catch but a learner would absorb uncritically.

**Q: The design is unusual for an edtech product. Why does it look like this?**

A: The aesthetic -- what the project calls "Civic Sanctuary" -- is intentional. Most learning apps use bright colors, rounded corners, and cartoon elements to signal approachability. That visual language also signals that the product is not serious. Mandarin uses warm stone tones, serif typography, and clean layouts because those choices communicate what the product actually is: a serious tool for sustained use. The design influences include architecture and film more than other software products. The goal is a space that feels like a well-lit library, not a mobile game.

---

## 10. Embargo and Exclusivity Notes

**Embargo policy:**
We are willing to provide advance access to the product, screenshots, and briefing materials under embargo for launch coverage. Embargo dates and times will be communicated clearly in writing before any materials are shared. We expect all parties to honor the agreed embargo. If an outlet breaks embargo, we reserve the right to lift the embargo for all other outlets immediately.

**Exclusivity:**
We are open to offering a single outlet a launch-day exclusive -- first access to the product, a founder interview, and the first published review. Exclusive arrangements are negotiated individually and confirmed in writing. An exclusive applies to the initial launch story only; other outlets are free to cover the product after the embargo lifts.

**Review copies:**
Journalists and content creators covering the product may request a complimentary Pro account for review purposes. Review accounts remain active for 90 days. We do not require editorial approval or advance review of coverage.

**Corrections:**
If published coverage contains factual errors about the product, we will reach out with a correction request. We ask that outlets update digital articles when factual errors are identified. We understand that editorial independence means we have no control over opinions, framing, or conclusions -- only factual accuracy.

**To arrange embargo access, exclusives, or review copies:** press@mandarin.app

---

*This press kit is maintained by the Mandarin team. For the most current version, contact press@mandarin.app.*
