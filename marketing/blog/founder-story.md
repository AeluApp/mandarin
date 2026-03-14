# I Built a Chinese Learning App. Here's What I Learned About Language Acquisition.

*I started learning Chinese and couldn't find a tool that worked the way my brain needed it to. So I built one. Along the way, I learned more about how memory works than I expected — and made every mistake in the product-development playbook.*

---

## How this started

About two years ago, I decided to learn Chinese. Not "learn a few phrases for a trip" — actually learn it. Read a newspaper. Have a conversation. Understand what's being said in the Chinese dramas my partner watches.

I downloaded Duolingo first, because everyone does. It was fine for about a week. The gamification kept me opening the app, but after a few days I realized I was optimizing for streaks, not learning. I'd match pictures to words, tap the right answer in a multiple-choice lineup, and feel good about a green progress bar — but when I tried to recall anything without the app's scaffolding, it was gone. The game mechanics were working exactly as designed. They just weren't designed for retention.

I tried Anki next. Anki is powerful — genuinely powerful — but it asks you to build your own curriculum. You import decks, or make your own cards, and the spaced repetition engine handles the scheduling. The problem is that good Anki decks require good content design, and content design is a separate skill from language learning. I spent more time formatting cards than studying them. Every decision — should I include pinyin? Audio? Example sentences? Both directions or just one? — was a rabbit hole.

I tried HelloChinese and a few others. They were better. The content was sequenced. The exercises made sense. But they still felt like textbooks with touchscreens. And none of them solved the problem I kept running into: I'd study vocabulary in the app, then try to read something real — a WeChat message, a news headline, a restaurant sign — and the gap between "studying Chinese" and "using Chinese" felt enormous.

Nothing connected what I was reading and hearing in the real world to what I was drilling in an app. That gap is where I started building.

## What the research actually says

Before I wrote a line of code, I spent weeks reading cognitive science papers on memory and learning. Not because I'm an academic — I'm not — but because I figured if I was going to build something, I should understand why existing tools worked or didn't.

A few findings shaped everything:

**Spaced repetition works, but the intervals matter.** This goes back to Hermann Ebbinghaus in the 1880s, who first mapped the forgetting curve — how quickly we forget new information without review. Pimsleur refined this into specific intervals for language learning. Modern algorithms like FSRS (Free Spaced Repetition Scheduler) take it further, adjusting intervals based on your personal forgetting patterns. The core insight is simple: review something just as you're about to forget it, and the memory strengthens. Review too early and you're wasting time. Review too late and you're re-learning from scratch.

**Interleaving beats blocked practice.** This one surprised me. If you're learning vocabulary for food, clothing, and transportation, your instinct is to study all the food words, then all the clothing words, then transportation. That feels organized. It also doesn't work as well. Research by Rohrer and Taylor (2007) and others shows that mixing topics and drill types in a single session — even though it feels harder and messier — produces significantly better long-term retention. The difficulty is the point.

**Desirable difficulty is a real thing.** Robert Bjork's work on this concept changed how I think about practice. Making something harder — within reason — makes the learning stick better. If a drill is easy, you're not growing. If it's impossible, you're just frustrated. The sweet spot is that slightly-too-hard zone where you have to work for it.

**The testing effect: retrieval beats review.** Actively trying to recall something is more effective than passively re-reading it. This is why flashcards work better than highlighting a textbook. And it's why varied, active drills work better than flashcards alone.

## Why I built 44 drill types

When I explain that the app has 27 different drill types, people sometimes laugh. It sounds like over-engineering. But each one exists for a reason grounded in how memory works.

Not all practice is equal. Recognizing a character when you see it uses different neural pathways than producing it from memory. Hearing a tone and identifying it is different from producing the correct tone yourself. Reading a sentence with a missing word (cloze deletion) forces you to understand the grammar and context, not just the vocabulary.

Here's a sample of what I mean:

**Tone pair drills** force you to distinguish between similar sounds. The difference between 买 (*mǎi*, to buy, third tone) and 卖 (*mài*, to sell, fourth tone) is a single tone — and if you get it wrong, you've said the opposite of what you meant. You don't build that discrimination by reading; you build it by listening and choosing, over and over, with pairs that are specifically designed to be confusing.

**Cloze deletion** gives you a sentence with a blank: 我想___一杯咖啡 (I want to ___ a cup of coffee). You have to produce 喝 (*hē*, drink) from context. This is harder than recognizing 喝 on a flashcard, and that's exactly why it works better.

**Audio-to-hanzi matching** forces you to connect what you hear to what you read — bridging the listening-reading gap that trips up so many learners.

**Register-aware drills** teach you the difference between formal and casual Chinese. Textbook Chinese and street Chinese diverge significantly, and most apps only teach you one.

The science of varied practice says that switching between these drill types in a single session — even though it feels disorienting — strengthens memory traces by forcing your brain to re-contextualize the same information in different ways. It's like training a muscle from multiple angles instead of doing the same exercise on repeat.

## The cleanup loop

The feature I'm most proud of isn't flashy. I call it the cleanup loop, and it works like this:

You read something in Chinese — a graded reader, a news snippet, whatever's at your level. When you hit a word you don't know, you tap it and get an inline gloss: pinyin, meaning, example. That unknown word automatically becomes a drill item. The next time you practice, it shows up in your spaced repetition queue, mixed in with your other items, across multiple drill types.

Read real Chinese. Look up what you don't know. Drill those specific words. Repeat.

This sounds simple, and it is. But it bridges the gap that frustrated me with every other tool I tried. It connects the experience of reading Chinese to the discipline of drilling vocabulary, without requiring you to manually create cards or maintain a word list.

It's basically how a good tutor works. They notice what you struggle with, make a mental note, and circle back to it later. Except the app never forgets and never gets tired.

## What I got wrong

I'd love to say I had a clear vision and executed it perfectly. I didn't. I made mistakes that cost me months.

**I built an audio recording and tone grading system before anyone needed it.** It was technically interesting — record yourself speaking, compare your tone contours to reference audio, get a score. But I built it early, when the core drilling and content weren't mature enough. I was solving a cool engineering problem instead of the most important user problem. The lesson: build what's needed next, not what's interesting to build.

**I over-engineered the scheduling algorithm before I had data.** I spent weeks tweaking the spaced repetition parameters — optimal intervals, difficulty weights, interleaving ratios — before I had enough usage data to know if my tweaks were improvements. I was optimizing in the dark. Eventually I stepped back, picked sensible defaults from the research literature, and committed to tuning later when I had real data. That was the right call. I should have made it sooner.

**I spent too long on features and not enough on content quality.** This is the trap every developer falls into when building an educational product. The features are in your wheelhouse. The content is the hard part. But users don't care how elegant your scheduling algorithm is if the example sentences are awkward or the difficulty progression is wrong. The content is the product. The features are just delivery infrastructure.

**I underestimated how much curriculum design matters.** Deciding which 300 words to teach first, which grammar points to introduce at each level, which example sentences best illustrate usage — these decisions have more impact on learning outcomes than any technical feature. I wish I'd spent more time on curriculum and less time on code in the first six months.

## What actually moves the needle

After building this thing and using it daily for over a year, and after watching how the system tracks my own progress, here's what I've concluded actually matters:

**Consistency beats intensity.** Fifteen minutes every day produces better results than two hours once a week. This isn't motivational advice — it's a direct consequence of how the forgetting curve works. Spaced repetition requires regular contact. A two-hour session can't compensate for six days of silence because by day three, you've already forgotten most of what you reviewed.

**Active recall beats passive review.** Drilling — actively trying to produce or identify something — is more effective than re-reading notes or passively listening. This is the testing effect in action. It feels harder because it is harder, and that's why it works.

**Context beats isolation.** Learning a character inside a sentence is more effective than learning it on a flashcard by itself. Sentences give you grammar, usage patterns, collocations, and register cues that isolated vocabulary can't. This is why cloze deletion and sentence-level drills are worth the extra complexity.

**Honest diagnostics beat encouragement.** This is the one that feels counterintuitive. Most language apps lean heavily on positive reinforcement — confetti animations, streak celebrations, "Great job!" messages. That feels good in the moment, but it doesn't help you improve. Knowing that your listening comprehension is two levels behind your reading ability is uncomfortable but actionable. You can fix a specific weakness. You can't fix "keep up the great work!"

The app shows you exactly where you are: which tones you mix up, which grammar patterns you get wrong, where your listening lags your reading. The numbers are real and sometimes unflattering. That's the point.

## The "no AI at runtime" decision

People are often surprised when I tell them the app uses zero AI tokens at runtime. No GPT calls, no Claude calls, no language model generating anything on the fly. Every drill, every score, every recommendation is deterministic — computed from your data using algorithms that run locally.

This wasn't an ideological choice. It was a practical one.

**Reliability.** Language drills need to be instant. A 200ms API call to generate a response is fine for a chatbot; it's unacceptable for a flashcard drill where timing affects your flow state. And API calls fail. Servers go down. Rate limits hit. I wanted the app to work every time, immediately, with no dependencies on external services.

**Correctness.** AI-generated example sentences sometimes contain errors — wrong tones, unnatural phrasing, hallucinated words. In a language learning context, an error in the training material is worse than no material at all, because you'll memorize the error. Every sentence, every audio clip, every drill in the app has been verified. That's not possible at scale with generated content.

**Privacy.** Your learning data — what you get wrong, how often, which patterns you struggle with — is sensitive in a low-stakes but personal way. It stays on the system. It doesn't get sent to a third-party API for processing.

**Offline capability.** The core drilling works without an internet connection. On a train, on a plane, in a part of China with spotty wifi — it works.

I want to be clear: this isn't an anti-AI stance. I used AI extensively to help build the content — generating draft sentences, finding example contexts, identifying common learner errors. AI is an excellent tool for content creation. I just don't think it's the right tool for real-time drill scoring and scheduling, where determinism and reliability matter more than flexibility.

## Where this is going

I use this app every day. I'm at roughly HSK 3 in speaking, HSK 4 in reading, and somewhere in between for listening — which is a normal distribution of skills, by the way. The app knows this about me because it tracks each skill independently.

I'm still building it. The graded reading library is growing. The drill types are being refined based on what I see working in my own data. The curriculum is getting tighter. Every week, I find something that could be better, and I fix it.

If you're learning Chinese, I'd genuinely like you to try it. Not because I need users for a growth metric — I'm a solo developer, not a startup chasing Series A. But because the tool gets better when more people use it and tell me what's missing.

HSK 1-2 content is free, no time limit. Full access to all levels, all drill types, all diagnostics is $14.99/month. No annual upsell, no "premium tier," no in-app purchases.

If you're curious: [aelu.app](https://aelu.app)

And if you just read this whole thing and have thoughts — about the approach, the research, the mistakes — I'm at hello@aeluapp.com. I read everything.

---

*This post is part of a series on learning Chinese as an adult. More at [aeluapp.com/blog](https://aeluapp.com/blog).*
