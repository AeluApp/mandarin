# Discord Strategy — Aelu

Last updated: 2026-02-17

This document covers the complete Discord strategy: building our own server, engaging in existing communities, an 8-week content calendar, and metrics. Everything here should be consistent with the positioning document and brand voice guidelines.

---

## Part 1: Own Server Design

### Server Name & Branding

**Ranked options:**

1. **Aelu Study Hall** — Immediately communicates purpose. "Study Hall" signals a calm, focused environment where adults come to work, not play. Matches the Civic Sanctuary aesthetic. No one confuses it with a social hangout or gaming server.

2. **Aelu Practice Room** — "Practice Room" carries the same connotation as a music practice room: serious, personal, skill-building. Slightly less distinctive than Study Hall but equally clear.

3. **Aelu Drills** — Direct product tie-in. Unambiguous about what happens here. Risks sounding clinical to people unfamiliar with the app's terminology.

4. **The Cleanup Loop** — Insider reference that resonates with existing users and creates curiosity for newcomers. Downside: means nothing until someone explains it. Better suited as a channel name than a server name.

**Recommendation:** Aelu Study Hall.

**Icon design description:**

A square icon with a warm stone background (#E8DFD0) featuring a single Chinese character — perhaps 学 (xue, "to study") — rendered in the bright teal accent color (#2A9D8F) used throughout the Civic Sanctuary palette. The character is set in Noto Serif SC at a large weight, centered, with generous whitespace around it. No gradients, no drop shadows, no illustrations. The effect should be: a ceramic tile with a single character embossed on it. Calm, legible at small sizes, immediately signals "Chinese."

**Banner description:**

A wide horizontal banner (960x540px) with a warm stone gradient background transitioning from light (#F0E8DD) on the left to slightly deeper (#E0D4C4) on the right. On the left third, the text "Aelu Study Hall" in Cormorant Garamond, terracotta color (#C96B4F). Below it, in Source Sans 3 regular, smaller: "Honest practice. Real progress." On the right side, a subtle arrangement of faded Chinese characters (various HSK levels) in a lighter shade of the stone color, creating a texture without distraction. No illustrations, no mascots, no screenshots. The feel should be: the foyer of a well-lit library.

**Server description (for Discord Discovery):**

"A study community for adults learning Mandarin Chinese. Daily vocabulary, weekly challenges, HSK prep discussion, and honest progress tracking. Built around the Aelu app — but open to anyone serious about learning. No gamification, no streak anxiety, no gatekeeping."

---

### Channel Structure

#### Category: Welcome

**#welcome**
- Purpose: First thing new members see. Rules, getting started steps, and a pointer to role selection.
- Who posts: Admins only (read-only for members). The welcome message is pinned.
- Example content: The complete welcome message (see Welcome Flow section below).

**#introductions**
- Purpose: New members introduce themselves. Keeps the welcome channel clean while giving everyone a low-stakes first post.
- Who posts: Anyone.
- Example content: "Hey, I'm Maria. HSK 2, based in Toronto. Studying about 30 minutes a day after work. My listening is way behind my reading and I'm trying to fix that. Using Anki + the Aelu app."

**#roles**
- Purpose: Self-assign roles via reaction roles (Carl-bot). Contains one pinned message with reaction emoji mapped to roles.
- Who posts: Admins (pinned role message). Members react to self-assign.
- Example content: Pinned message with sections for HSK level, timezone, and learning goal — each with emoji reactions.

---

#### Category: Study

**#daily-practice**
- Purpose: Accountability. Members post what they studied today — duration, drills completed, items reviewed, anything concrete.
- Who posts: Anyone.
- Example content: "25 min session today. 40 items reviewed, 8 new. Tone pairs are still rough — got 5/12 on tone discrimination drills. Going to focus there tomorrow."

**#questions**
- Purpose: Ask any Chinese learning question — grammar, pronunciation, character meaning, study method, tool comparison.
- Who posts: Anyone. Helpers encouraged to cite sources.
- Example content: "What's the difference between 以为 and 认为? I keep mixing them up in cloze drills."

**#resources**
- Purpose: Share useful links, tools, articles, and methods. Curated, not a link dump. Each share should include a one-sentence description of why it is useful.
- Who posts: Anyone, but the team reviews periodically to pin the best.
- Example content: "This Mandarin Blueprint video on measure words actually clarified 条 vs 根 for me: [link]. Worth watching if you're around HSK 3."

**#hsk-prep**
- Purpose: HSK exam-specific discussion. Use Discord's thread feature to create sub-threads per HSK level (HSK 1 thread, HSK 2 thread, etc.) so the channel stays organized.
- Who posts: Anyone preparing for or who has taken an HSK exam.
- Example content: "Taking HSK 4 in April. The new listening section format has me worried. Anyone have tips for the short dialogue questions?"

**#tone-practice**
- Purpose: Share audio clips of your tones, ask for feedback, discuss tone training methods. Voice messages encouraged.
- Who posts: Anyone.
- Example content: [voice message] "Trying to nail the 2nd-4th tone pair in 'mingbai.' Does this sound right?" followed by community feedback.

**#reading-corner**
- Purpose: Share passages you are reading, discuss graded reading material, post screenshots of sentences you found interesting or confusing.
- Who posts: Anyone.
- Example content: "Found this sentence in a HSK 3 passage: 他虽然很累，但是还是坚持跑步。I kept reading 坚持 as jian1chi2 but it's actually jian1chi2. The cleanup loop caught it."

---

#### Category: The App

**#feedback**
- Purpose: Feature requests, bug reports, and suggestions for the Aelu app. the team reads everything here.
- Who posts: Anyone who uses the app.
- Example content: "Feature request: would be great to see a history of my weakest items over time, not just the current snapshot. Want to know if my tone accuracy is trending up."

**#changelog**
- Purpose: the team posts app updates. Read-only for members. Each post follows the same format: date, version, what changed, why it matters.
- Who posts: the team only.
- Example content:
  ```
  2026-02-15 — v2.4.1

  - Added playback speed control to listening drills (0.5x, 0.75x, 1x, 1.25x, 1.5x).
    Slower speeds help with tone discrimination at HSK 1-2.
    Faster speeds are useful for HSK 4+ learners building real-time comprehension.

  - Fixed a bug where context notes weren't displaying for items added via the cleanup loop.
  ```

**#tips-and-tricks**
- Purpose: How to get the most out of the app. Power-user techniques, configuration advice, workflow suggestions.
- Who posts: Anyone, but the team seeds initial content.
- Example content: "If you're short on time, try a 10-minute session with the 'focus' command. It narrows your queue to your 2 weakest skills and skips everything else. I do this on weekday mornings."

**#show-your-stats**
- Purpose: Share screenshots of your diagnostics, HSK projections, streak counts, or session summaries. Not for bragging — for honest comparison and discussion.
- Who posts: Anyone.
- Example content: [screenshot of HSK projection] "My vocabulary is tracking toward HSK 4 by June but my listening is lagging at HSK 2. Anyone else have a gap this wide? What helped?"

---

#### Category: Community

**#off-topic**
- Purpose: General conversation. Life in China/Taiwan, travel, culture, food, work, anything that is not directly about Chinese study.
- Who posts: Anyone.
- Example content: "Just got back from two weeks in Chengdu. The food is incredible but the Sichuan dialect is a whole different planet from what I've been studying."

**#language-exchange**
- Purpose: Find study partners, conversation buddies, or accountability pairs. Post your level, timezone, and what you are looking for.
- Who posts: Anyone looking for a partner.
- Example content: "HSK 3, US Pacific time, looking for someone to do 15-minute voice practice sessions 2-3x per week. I can help with English in return."

**#media-recommendations**
- Purpose: Share Chinese-language shows, movies, podcasts, music, books, and YouTube channels. Brief review or description required — not just a link.
- Who posts: Anyone.
- Example content: "Day of Becoming You (变成你的那一天) on Netflix — surprisingly good for HSK 3-4 listening practice. Contemporary dialogue, not too fast, and the subtitles are accurate."

**#wins**
- Purpose: Celebrate real milestones. Passed an exam. Read a full article without a dictionary. Had a conversation that actually worked. Genuine accomplishments, not participation trophies.
- Who posts: Anyone.
- Example content: "Ordered food entirely in Chinese for the first time today. The waiter responded in Chinese instead of switching to English. Small thing, but it felt real."

---

#### Category: Voice

**Study Together**
- Purpose: Silent co-working voice channel. Join, mute yourself, study alongside others. Pomodoro timer bot runs 25-min focus / 5-min break cycles. Camera optional.
- Who posts: Nobody speaks. Presence is the point.
- Example use: 3-4 people join after dinner, study for an hour, leave. No conversation necessary.

**Speaking Practice**
- Purpose: Open mic for Mandarin conversation practice. Any level welcome. Ground rule: no correcting mid-sentence (corrections go in text chat after).
- Who posts: Anyone willing to speak.
- Example use: Two HSK 3 learners practice ordering food scenarios. One HSK 5 learner joins and helps with pronunciation.

**Office Hours**
- Purpose: Scheduled time with the team. Weekly or biweekly. Q&A about the app, Chinese learning strategy, or building-in-public topics.
- Who posts: the team hosts, anyone attends.
- Example use: Thursday 7pm ET, 30 minutes. the team answers questions about recent app changes, discusses learning strategies, takes feature requests live.

---

### Role System

#### HSK Level Roles

| Role | Color | Emoji |
|------|-------|-------|
| Pre-HSK | #B0A89A (warm gray) | :seedling: |
| HSK 1 | #7FB685 (soft green) | :one: |
| HSK 2 | #5AAD8E (teal-green) | :two: |
| HSK 3 | #2A9D8F (teal) | :three: |
| HSK 4 | #3B7EC2 (blue) | :four: |
| HSK 5 | #6B5BAD (purple) | :five: |
| HSK 6+ | #C96B4F (terracotta) | :six: |
| Advanced (HSK 7-9) | #A0522D (sienna) | :star: |

#### Timezone Roles

| Role | Emoji |
|------|-------|
| Americas (UTC-10 to UTC-3) | :earth_americas: |
| Europe / Africa (UTC-1 to UTC+3) | :earth_africa: |
| Asia-Pacific (UTC+4 to UTC+12) | :earth_asia: |

#### Goal Roles

| Role | Emoji |
|------|-------|
| Casual (a few sessions per week) | :coffee: |
| Daily Practice (every day) | :calendar: |
| Exam Prep (targeting a specific HSK test date) | :pencil: |
| Heritage (filling reading/writing gaps) | :house: |

#### Special Roles

| Role | How assigned | Purpose |
|------|-------------|---------|
| Beta Tester | Invitation from the team | Tests pre-release features, provides early feedback |
| Contributor | Earned by sustained helpfulness | Members who consistently answer questions, share quality resources, help others |
| Partner | Manual assignment | Representatives from partner tools/channels (Chinese Zero to Hero, Du Chinese, etc.) |
| Moderator | Invitation from the team | Community moderation (Phase 2+) |

#### Assignment Method

All standard roles (HSK level, timezone, goal) are self-assigned via Carl-bot reaction roles in the #roles channel. One pinned message per category. Members react with the corresponding emoji to receive the role. They can change roles at any time by removing/adding reactions. Special roles are assigned manually by the team.

---

### Bot Setup

#### 1. Carl-bot (Reaction Roles + Moderation)

**What it does:** Reaction roles, auto-moderation, logging, custom commands.

**Setup:**
- Invite Carl-bot from https://carl.gg/
- Grant Administrator permission.
- In #roles, create three reaction role messages:
  - **HSK Level:** Post a message titled "What's your HSK level?" with the emoji-to-role mapping listed above. Use Carl-bot's reaction role builder: `/reactionrole` command or the web dashboard at carl.gg.
  - **Timezone:** Same format. "Where in the world are you?"
  - **Learning Goal:** Same format. "What's your goal?"
- Configure auto-mod rules:
  - Block messages with 5+ mentions (anti-spam).
  - Block messages with 3+ links (anti-spam).
  - Block known spam phrases ("free followers," "check out my OnlyFans," etc.).
  - Log deleted/edited messages to a mod-only #mod-log channel.
- Set up a welcome DM (see Welcome Flow section) that triggers when a new member joins.

**Cost:** Free for all features needed. Premium ($5/mo) adds custom branding — not necessary.

#### 2. Sapphire (Backup Moderation + Welcome)

**What it does:** Moderation, welcome messages, join/leave logging. A free alternative to MEE6 that does not paywall core features.

**Setup:**
- Invite from https://sapph.xyz/
- Configure welcome message to post in #welcome when a new member joins. Message: "Welcome, {user}. Head to #roles to pick your HSK level and timezone, then introduce yourself in #introductions."
- Enable join/leave logging to #mod-log.
- Configure auto-mod as a second layer behind Carl-bot (catches anything Carl-bot misses).

**Cost:** Free.

#### 3. Pomodoro Bot (Study Timer)

**What it does:** Runs pomodoro timers in the Study Together voice channel. Announces focus periods (25 min) and breaks (5 min).

**Recommended bot:** **Pomomo** (https://pomomo.us/)

**Setup:**
- Invite to server.
- Configure default timer: 25 minutes work, 5 minutes break, 4 cycles then 15-minute long break.
- Set the bot to announce timer events in the Study Together voice channel.
- Members can also start personal timers with `/pomo start`.

**Cost:** Free.

#### 4. Apollo (Event Scheduling)

**What it does:** Schedules events (Office Hours, study sprints, AMAs) with RSVP, reminders, and timezone conversion.

**Recommended bot:** **Apollo** (https://apollo.fyi/)

**Setup:**
- Invite to server.
- Create recurring events:
  - Office Hours: Weekly on Thursdays, 7:00 PM ET, 30 minutes.
  - Study Sprint: Monthly, first Saturday, 2:00 PM ET, 2 hours.
  - Monthly AMA: Last Friday of each month, 7:00 PM ET, 45 minutes.
- Apollo automatically converts times to each member's local timezone.
- RSVP reactions let the team gauge attendance before events.

**Cost:** Free for basic features. Premium ($5/mo) adds recurring events and custom branding — worth it once events are regular (Phase 2+).

#### 5. Custom Vocabulary Bot (Manual via Discord Webhooks)

Rather than relying on a third-party vocabulary bot that may not support Chinese well, the team posts the daily vocabulary challenge manually using a Discord webhook and a simple script.

**Setup:**
- Create a webhook in the #daily-practice channel (Server Settings > Integrations > Webhooks).
- Name it "Daily Word" with the server icon as the avatar.
- Write a simple Python script (or use a cron job with curl) that posts a formatted vocabulary entry each day at 8:00 AM ET.
- Format:

```
**Daily Word — Day 47**

**今天的词:** 坚持 (jiān chí)
**English:** to persist, to insist on
**HSK Level:** 3
**Example:** 他每天坚持跑步。(Tā měi tiān jiānchí pǎobù.) — He persists in running every day.

**Your turn:** Use 坚持 in your own sentence. Any level of complexity is fine.
```

**Cost:** Free (it is a webhook, not a bot subscription).

**Why not World Word Daily or a generic bot:** Most vocabulary bots support common European languages well but have limited or no Chinese support, especially for pinyin formatting, tone marks, and HSK alignment. A custom webhook gives full control over formatting and content selection, and the vocabulary can be drawn directly from the app's 10,000+ item library (HSK 1-9).

---

### Welcome Flow

The following is the complete welcome message, pinned in #welcome. New members also receive a condensed version via DM from Carl-bot upon joining.

---

**Welcome to Aelu Study Hall.**

This is a study community for adults learning Mandarin Chinese. It was started by the team behind the Aelu app. The server is open to anyone serious about learning — you do not need to use the app to be here.

**Getting Started**

1. Go to #roles and select your HSK level, timezone, and learning goal. This helps us match you with the right conversations and study partners.
2. Introduce yourself in #introductions. Tell us your current level, how long you have been studying, what tools you use, and what you are working on right now.
3. Join the daily vocabulary challenge in #daily-practice. A new word is posted each morning. Try using it in a sentence.

**Where to Find Things**

- **Study questions:** #questions
- **Share what you studied today:** #daily-practice
- **HSK exam discussion:** #hsk-prep
- **Tone practice and audio clips:** #tone-practice
- **Reading discussion:** #reading-corner
- **App feedback and feature requests:** #feedback
- **App updates:** #changelog
- **Find a study partner:** #language-exchange
- **Show/movie/podcast recommendations:** #media-recommendations
- **Celebrate a milestone:** #wins
- **Co-working (silent study):** Study Together voice channel
- **Speaking practice:** Speaking Practice voice channel
- **Q&A with the team:** Office Hours voice channel (scheduled — check events)

**Rules**

1. Be respectful. Disagreement is fine. Insults, hostility, and dismissiveness are not.
2. No spam or self-promotion without context. If you share your own content (blog, video, app), explain why it is relevant and be a community member first.
3. Use the right channels. Study questions go in #questions, not #off-topic.
4. English is the default language for discussion. Chinese is encouraged and welcome in study channels (#daily-practice, #tone-practice, #reading-corner, #hsk-prep), and expected in the Speaking Practice voice channel.
5. No gatekeeping. Never tell someone their Chinese is not good enough for something. Everyone is at a different level and everyone is welcome to participate.
6. Credit sources. When sharing resources, link to the original creator. Do not repost others' paid content.
7. Keep feedback constructive. Criticism of tools, methods, or the app itself is welcome — but "this sucks" is not feedback. Say what is wrong, why it matters, and ideally what would be better.

**About the App**

Aelu is an adaptive drilling and reading system for Mandarin Chinese. 27 drill types, honest per-skill diagnostics, FSRS-based spaced repetition, and a graded reader where every word you look up becomes practice. Free for HSK 1-2 content, $14.99/month for full access. Learn more: [link]

This server is not a sales funnel. It is a study community. The app comes up naturally because the team uses it and builds it, but nobody here is required or expected to use it.

---

### Server Rules (Expanded Reference for Moderators)

1. **Be respectful.** Treat every member the way you would treat a classmate. Disagreement on methods, tools, and approaches is normal and healthy. Personal attacks, sarcasm directed at a person, and condescension are not tolerated. This includes tone — "lol you're still at HSK 2?" is a violation even if technically phrased as a question.

2. **No spam or self-promotion without context.** Sharing your own blog post, YouTube video, or tool is allowed if you are an active member of the community and the content is genuinely relevant to the conversation. Joining the server solely to drop a link and leave is spam. Repeated promotion of the same thing is spam. Affiliate links require disclosure. When in doubt, ask a moderator first.

3. **Use the right channels.** Every channel has a stated purpose. Posting study questions in #off-topic or memes in #questions degrades the signal-to-noise ratio for everyone. If you are unsure where something belongs, ask in #off-topic and a moderator will direct you.

4. **English is the default; Chinese is encouraged in study channels.** General discussion channels (#off-topic, #language-exchange, #media-recommendations) default to English so everyone can participate. Study channels (#daily-practice, #questions, #tone-practice, #reading-corner, #hsk-prep) are bilingual — use as much Chinese as you can. The Speaking Practice voice channel is for Chinese conversation practice.

5. **No gatekeeping.** This server is for learners at every level, from Pre-HSK to advanced. Do not tell someone they should not attempt something because their level is too low. Do not mock beginner questions. Do not create an atmosphere where people feel they need permission to participate. Heritage speakers, self-studiers, and classroom learners are all equally welcome.

6. **Credit sources.** When sharing a resource (article, video, method, deck), link to the original creator. Do not repost copyrighted content (full textbook pages, paid course materials) in the server. Brief quotes for discussion are fine.

7. **Keep feedback constructive.** The #feedback channel exists because the team genuinely wants input on the app. "This feature is confusing because X" is constructive. "This is bad" is not. The same standard applies to discussing any tool, method, or resource — critique the work, not the person.

**Enforcement escalation:**
- First violation: Warning via DM from moderator.
- Second violation: 24-hour mute.
- Third violation: Kick from server with explanation.
- Severe violation (slurs, harassment, doxxing): Immediate ban, no warnings.

---

### Engagement Mechanics

#### Daily Vocabulary Challenge

**Format:** Posted every day at 8:00 AM ET via webhook in #daily-practice.

**Structure:**
```
**Daily Word — Day [N]**

**今天的词:** [hanzi] ([pinyin])
**English:** [definition]
**HSK Level:** [1-6]
**Example:** [Chinese sentence] ([pinyin]) — [English translation]

**Your turn:** Use [hanzi] in your own sentence. Any level of complexity is fine.
```

**Engagement rules:**
- Members reply with their own sentence using the word.
- Other members react with a check mark if the sentence is grammatically correct or natural.
- No "corrections" unless someone explicitly asks. Unsolicited correction discourages participation.
- the team or a moderator occasionally posts a "best of" roundup — not as a competition, but to highlight creative or interesting uses.

**Weekly summary:** Every Sunday, the team posts a recap of the 7 words from that week in a single message. Members who used all 7 in sentences get a shout-out (not a prize — just recognition).

**Word selection:** Drawn from the app's 10,000+ item library, starting with HSK 1-3 and cycling through in rough HSK order. As the community levels up, the daily words progress into higher HSK tiers.

---

#### Weekly Study Challenge

**Format:** Posted Monday at 8:00 AM ET in #daily-practice, pinned for the week.

**Structure:**
```
**Weekly Challenge — Week [N]**

**This week's challenge:** [specific, measurable task]

**How to participate:**
1. Reply to this message with "I'm in" to commit.
2. Post your progress in this thread throughout the week.
3. Check in on Friday with your status.
4. Sunday: final results.

No prizes. No penalties. Just accountability.
```

**Example challenges (rotating themes):**

| Week | Challenge | Theme |
|------|-----------|-------|
| 1 | Study every day this week (any duration counts) | Consistency |
| 2 | Learn 5 new measure words and use each in a sentence | Grammar |
| 3 | Listen to 60 minutes of Chinese audio this week (podcast, show, music) | Listening |
| 4 | Read one full graded passage and post 3 words you looked up | Reading |
| 5 | Record yourself saying 10 tone pairs and post in #tone-practice | Tones |
| 6 | Find and share one Chinese learning resource you have never seen recommended | Discovery |
| 7 | Write 5 sentences in Chinese without using a dictionary | Production |
| 8 | Complete a diagnostic check in the app (or do a self-assessment) and share your honest skill breakdown | Diagnostics |

**Friday check-in:** the team posts a thread: "How's the challenge going? Post your progress — honest, not inflated."

**Sunday results:** the team posts a summary: how many people committed, how many followed through, notable efforts. Tone: factual, not cheerleadery. "14 people committed, 9 posted progress, 6 completed. Here's what people found hardest: [summary]."

---

#### Monthly Events

**AMA with the Aelu Team (last Friday of each month, 7:00 PM ET, 45 min, voice channel)**
- the team answers questions about the app roadmap, his own learning progress, building-in-public decisions, and Chinese learning strategy.
- Questions collected in advance via a thread in #feedback (posted 3 days before the AMA).
- Voice channel, but the team types answers for key points so they are searchable later.
- Post-AMA: the team posts a text summary of key Q&A pairs in #changelog.

**Study Sprint (first Saturday of each month, 2:00 PM ET, 2 hours, voice channel)**
- Structure: 4 pomodoro cycles (25 min study, 5 min break).
- Everyone joins the Study Together voice channel, mutes themselves, and studies.
- During breaks, unmute for brief check-ins: "What are you working on?"
- the team participates as a fellow studier, not as a host.

**"Show Your Progress" Thread (mid-month, posted in #show-your-stats)**
- the team posts a thread: "It's the 15th. How are you doing? Share your stats, projections, wins, struggles — whatever is real."
- Members share screenshots, diagnostic results, or just a paragraph about where they are.
- No comparison pressure. The thread is about individual trajectories, not rankings.

**Guest Speaker (quarterly, starting in Phase 2)**
- Invite a Chinese teacher, content creator, or tool developer from the partner list for a 30-minute voice session.
- Format: 15 min presentation or Q&A, 15 min open discussion.
- Promote the event 2 weeks in advance in the server and cross-post to Reddit/social.
- Target guests: Chinese Zero to Hero (Phil), I'm Learning Mandarin (Mischa), a working iTalki tutor, a heritage speaker willing to share their perspective.

---

#### Accountability Pairs

**Opt-in system:**

1. Members post in #language-exchange with the tag "[Accountability Pair]" and include: HSK level, timezone, preferred check-in time, and what they want to be held accountable for (daily sessions, specific weekly goals, exam prep milestones).

2. the team (or later, a moderator) manually matches pairs based on: same or adjacent HSK level, overlapping timezone (within 3 hours), and compatible goals.

3. Pairs are introduced via a group DM from the team with a brief: "You two have been matched. You're both HSK 3, Americas timezone, aiming for daily practice. DM each other a quick check-in each day — what you studied, how long, any struggles. Re-matching happens at the end of each month if either of you wants a change."

4. Monthly re-matching: At the end of each month, the team posts in #language-exchange asking who wants to continue with their current partner vs. re-match. Pairs that are working stay together. Pairs that fizzled get re-matched or opt out.

**Scale plan:** At 50+ members, this becomes a Google Form where members submit their details and the team matches them in batches. At 200+ members, a moderator takes over the matching process.

---

### Growth Strategy

#### Phase 1: Seed (0-50 members) — Months 1-2

**Invitation sources:**
- Existing app users: email notification and in-app banner linking to the Discord.
- Reddit: the team's existing presence in r/ChineseLanguage, r/MandarinChinese, r/LearnChinese. Not a "join my Discord" post — instead, mention the server naturally when relevant ("We discussed this in our Discord study group and someone pointed out...").
- Partner contacts: Personal messages to bloggers, podcasters, and content creators the team has already connected with (see partner-prospects.md). Not mass invitations — individual, personal asks.
- Twitter/X: Pin a tweet about the server. Include the invite link in the team's bio.
- The marketing newsletter (if launched): mention the Discord in the first issue.

**the team's role:**
- Active daily. Responds to every introduction, answers every question, participates in every daily vocabulary challenge.
- Posts the daily vocabulary word manually (webhook not yet automated).
- Hosts Office Hours weekly even if only 1-2 people show up.
- Starts conversations: posts study observations, asks questions, shares his own struggles. The server should never feel like a ghost town in Phase 1.

**Tone:**
- "Alpha community" feel. Early members are getting in on something small and personal.
- The team participates as fellow learners, not product evangelists. They share their own study sessions, gaps, and diagnostic scores.
- The app comes up organically because the team uses it, but the server is about studying Chinese, not about the app.

**Milestone:** 50 members by end of month 2.

---

#### Phase 2: Cultivate (50-200 members) — Months 3-5

**New activities:**
- Weekly challenges begin (if not already started in Phase 1).
- First monthly AMA.
- First study sprint.
- Accountability pair matching begins.

**Community leadership:**
- Identify 2-3 members who are consistently active, helpful, and have good judgment. Approach them privately: "You've been incredibly helpful in the server. Would you be willing to take on a moderator role? It's light — mainly making sure questions get answered and the rules are followed."
- Give moderators a private #mod-chat channel for coordination.
- Brief moderator guidelines: respond to rule violations within 24 hours, always DM first before public action, escalate anything ambiguous to the team.

**Cross-promotion:**
- Start engaging in partner Discord servers (see Part 2).
- Cross-post interesting discussions from the server to Reddit (with permission from the original poster, paraphrased).
- Mention the Discord in blog posts, social media, and the app's about page.

**Milestone:** 200 members by end of month 5.

---

#### Phase 3: Sustain (200-500 members) — Months 6-9

**Transition:**
- Community generates its own conversations without the team initiating.
- Members answer each other's questions before the team gets to them.
- Weekly challenges can be suggested by members (the team curates and posts).
- Study sprints can be hosted by community members in different timezones.

**the team's role shifts:**
- Daily presence is still important but reduced. 2-3 check-ins per day instead of constant monitoring.
- Focus shifts to: posting changelog updates, hosting monthly AMAs, reviewing feedback, and big-picture engagement.
- Moderators handle day-to-day channel management.

**New content:**
- Community-generated study guides (pinned in #resources).
- Member-led voice sessions (e.g., an HSK 5 member hosts a reading discussion).
- Guest speaker events (quarterly).

**Milestone:** 500 members by end of month 9. Self-sustaining daily activity without the team initiating.

---

#### Phase 4: Scale (500+ members) — Month 10+

**At this scale:**
- Consider adding language-specific sub-channels if demand warrants (e.g., #cantonese, #classical-chinese).
- Partner server integrations: mutual announcements, shared events, cross-server voice sessions.
- Voice events become regular (3-4 per week across timezones).
- Community-driven resource curation: members maintain a pinned list of recommended tools, books, and courses in #resources.
- Members who have gone from beginner to intermediate (or intermediate to advanced) become the most valuable community members — their journey stories are more persuasive than any marketing.

**App ambassador program:**
- Identify members who use the app daily and talk about it naturally (not promotional).
- Offer them Beta Tester roles, early access to features, and a direct line to the team for feedback.
- They are not affiliates or salespeople. They are power users whose genuine experience is visible to the community.

**Milestone:** Organic growth through word-of-mouth and Discord Discovery. Server is listed in relevant Discord directories (DISBOARD, top.gg).

---

### Moderation Plan

**Phase 1 (0-50 members):**
- the team moderates alone.
- Low volume makes this manageable.
- All moderation actions logged in #mod-log (Carl-bot does this automatically).

**Phase 2 (50-200 members):**
- Recruit 2-3 moderators.
- **Selection criteria:** Active for 30+ days. Posts regularly and helpfully. Demonstrates good judgment in how they interact with others. Has not had any warnings or rule violations. Willing to commit to checking the server at least once daily.
- **Moderator responsibilities:**
  - Monitor channels for rule violations.
  - Welcome new members who do not receive an automatic welcome (edge cases).
  - Answer questions or tag someone who can.
  - Escalate ambiguous situations to the team.
  - Attend monthly moderator sync (15-minute voice call, once per month).
- **Moderator guidelines document:** Shared in #mod-chat.
  - Always DM first before taking public action.
  - Use the escalation ladder: warning, mute (24h), kick, ban.
  - Never delete a message without logging the reason in #mod-log.
  - When in doubt, do not act — ask the team or another moderator.
  - Moderators are community members first. They should participate in discussions, post in daily challenges, and be seen as peers, not authority figures.

**Phase 3+ (200+ members):**
- Expand moderator team to 4-5 people with timezone coverage (at least one mod in each major timezone).
- Monthly moderator sync becomes structured: review any incidents, discuss community health metrics, plan upcoming events.
- the team reviews #mod-log weekly and provides feedback.

---

## Part 2: Existing Servers to Join

The following servers are listed in priority order. For each, the team should join as a genuine community member first. No immediate self-promotion. Participate for at least 2 weeks before mentioning the app, and only when it is naturally relevant.

---

### 1. r/ChineseLanguage Discord

- **Server name:** /r/ChineseLanguage
- **Approximate members:** 42,500+
- **Focus:** General Chinese language learning — all levels, all dialects, all aspects. Grammar questions, pronunciation challenges, tool discussions, cultural context.
- **Activity level:** High. Multiple conversations daily across channels. Regular pronunciation challenge events.
- **Self-promotion rules:** Self-promotion is generally restricted. Resources can be shared if relevant to an ongoing discussion. Blatant advertising will be removed.
- **Engagement strategy:** This is the single most important community for the team to be active in. Answer grammar questions. Share observations from his own study. Participate in pronunciation challenges. When someone asks "how do I know if I'm ready for HSK X?" or "how do I track my skill gaps?", that is a natural opening to mention the app — but only after providing a substantive answer first. the team should be known here as "that guy who gives good advice and also happens to be building an app," not "that guy who keeps promoting his app."
- **Priority:** 1

**Team introduction:**

"Hey everyone. We're the team behind Aelu — we've been studying Mandarin for [X months/years], currently around HSK 3. We're also building a Mandarin learning app, which is both our project and our daily study tool. Mostly here to learn from people who are further along, answer questions when we can, and talk about the mechanics of how we actually get better at this language. Happy to be here."

---

### 2. 中英交流 Chinese-English Language Exchange

- **Server name:** 中英交流 Chinese-English Language Exchange
- **Approximate members:** 69,600+
- **Focus:** The original Chinese-English exchange server. Active voice chats for language practice. Strong presence of native Chinese speakers learning English.
- **Activity level:** Very high. Voice channels are frequently populated. Text channels are active around the clock.
- **Self-promotion rules:** No self-promotion or advertising. Resources shared must be genuinely helpful, not promotional.
- **Engagement strategy:** Join voice practice sessions. This server is more about practice than tools, so the team should focus on being learners here, not builders. Participate in Chinese conversations at the appropriate level. Help English learners with their English. Build relationships. The app may come up in "what tools do you use?" conversations, which happen organically in exchange communities.
- **Priority:** 2

**Team introduction:**

"Hi, we're the Aelu team. Learning Mandarin, currently around HSK 3 level. My listening and speaking are behind my reading, so I'm here mainly for voice practice. Based in [timezone]. Native English speaker — happy to help with English questions too. Looking forward to practicing with everyone."

---

### 3. Migaku Discord

- **Server name:** Migaku: Really Learn Languages
- **Approximate members:** 19,200+
- **Focus:** Immersion-based language learning using the Migaku browser extension and tools. Chinese is one of several supported languages with dedicated channels.
- **Activity level:** Moderate to high. Chinese channels are less active than Japanese channels but still have regular discussion.
- **Self-promotion rules:** Self-promotion of competing tools is likely unwelcome. Resource sharing is acceptable if framed as helpful.
- **Engagement strategy:** The Migaku community values immersion and input-based learning. the team should engage on the topic of reading comprehension and the gap between passive input and active recall — a topic where the Aelu app's approach (the cleanup loop) is highly relevant without being promotional. Discuss how reading feeds into drilling. Share observations about retention from reading vs. from flashcards. This audience respects data and methodology.
- **Priority:** 3

**Team introduction:**

"Hi, we're the Aelu team. Studying Mandarin, currently HSK 3-ish. I'm interested in the intersection of immersion and structured review — specifically how reading Chinese content can feed back into active recall practice. Also building a Chinese learning tool on the side. Here to learn from the community and share what I'm finding in my own study."

---

### 4. Refold Chinese (汉语)

- **Server name:** Refold -- 汉语 (ZH)
- **Approximate members:** 6,800+
- **Focus:** Chinese-specific branch of the Refold immersion community. Comprehensible input methodology, tracking immersion hours, sharing resources.
- **Activity level:** Moderate. Discussions happen in bursts around immersion logs and resource sharing.
- **Self-promotion rules:** Generally tolerant of tool discussion if framed as a fellow learner sharing what works. Direct advertising would be removed.
- **Engagement strategy:** The Refold community tracks immersion hours meticulously and values quantified progress. the team should contribute to discussions about measuring progress beyond "hours of input" — the idea that you can listen for 500 hours but still have specific gaps in tone discrimination or grammar that immersion alone does not fix. This is where structured drilling complements immersion, and where the app's diagnostic approach is naturally relevant.
- **Priority:** 3

**Team introduction:**

"Hey, we're the Aelu team. Working through Mandarin at around HSK 3. I do a mix of immersion and structured drilling — interested in how they complement each other. Specifically trying to figure out how to measure whether my input is actually converting to usable skill, beyond just counting hours. Looking forward to the discussions here."

---

### 5. Language Learning Community (LLC)

- **Server name:** Language Learning Community
- **Approximate members:** 30,800+
- **Focus:** Multi-language learning community. Channels for many languages including Chinese. General methodology discussion, motivation, and language exchange.
- **Activity level:** High overall. Chinese-specific channels are moderately active.
- **Self-promotion rules:** Self-promotion is restricted to designated channels or contexts. Being an active community member comes first.
- **Engagement strategy:** Participate in general language learning methodology discussions. Share insights from building a learning system (the FSRS algorithm, interleaving research, desirable difficulty). This audience is interested in the science behind learning, not just Chinese specifically. the team can build credibility here as someone who understands learning science and applies it to a specific language.
- **Priority:** 4

**Team introduction:**

"Hi, we're the Aelu team. Primary language right now is Mandarin Chinese, currently HSK 3. I'm interested in the methodology side of language learning — spaced repetition scheduling, interleaving, how to measure actual skill gaps vs. perceived progress. Also building a Chinese study tool, which gives me a weird dual perspective of being both the student and the system designer. Happy to discuss methods with anyone."

---

### 6. 中文吧 Chinese Club

- **Server name:** 中文吧 Chinese Club China
- **Approximate members:** 43,100+
- **Focus:** Large Chinese community server — not exclusively for learners. Includes gaming, music, investment discussion, and general Chinese-language social channels. Has a dedicated Chinese learning area.
- **Activity level:** Very high, but much of the activity is in non-learning channels (gaming, entertainment).
- **Self-promotion rules:** No ads or affiliate links. The learning-focused channels are more tolerant of resource sharing.
- **Engagement strategy:** Focus exclusively on the Chinese learning channels. Answer beginner questions. Share study tips. The broader server is a social community, not a study community, so the team's presence should be focused and specific. This is a place to help individuals, not promote to a crowd.
- **Priority:** 4

**Team introduction:**

"Hi, we're the Aelu team. Learning Mandarin, around HSK 3. Here for the Chinese learning channels — happy to share study tips and learn from more advanced speakers. Based in [timezone], studying most evenings."

---

### 7. Chinese Zero to Hero Discord

- **Server name:** Chinese Zero to Hero
- **Approximate members:** 350+
- **Focus:** Community around the Chinese Zero to Hero video course platform. Students at various levels discussing course content, grammar questions, and study progress.
- **Activity level:** Low to moderate. Small but engaged community.
- **Self-promotion rules:** Likely tolerant of tool discussion since the community is small and collegial. Direct advertising of a competing product would be inappropriate; framing as a complementary tool is acceptable.
- **Engagement strategy:** Chinese Zero to Hero is explicitly listed as a complementary tool in the positioning document ("we are the gym; they are the coach"). the team should engage as a fellow learner who uses CZ2H courses and supplements with his own drilling tool. This is a natural partnership opportunity — students who watch the course videos but struggle to retain what they learned are exactly the Aelu app's target user. Mention the app only when someone describes the exact problem it solves.
- **Priority:** 3

**Team introduction:**

"Hey, we're the Aelu team. Using CZ2H for structured grammar and instruction, supplementing with my own drilling practice. Currently around HSK 3. I've found the combination of video instruction plus targeted drilling works well for me — the courses explain the patterns, and then I drill them until they stick. Happy to discuss what's working and what isn't."

---

### 8. I'm Learning Mandarin / Peak Mandarin Discord

- **Server name:** I'm Learning Mandarin
- **Approximate members:** ~400
- **Focus:** Community around the I'm Learning Mandarin podcast. Learners at various stages sharing tips, experiences, and resources.
- **Activity level:** Low to moderate. Newer server, still building.
- **Self-promotion rules:** Likely tolerant given the small, friendly community. Being genuine and helpful matters more than strict rules.
- **Engagement strategy:** This is a podcast-centered community, which means members value narrative and personal experience over raw data. the team should share the learning journey — the specific struggles, the methods tried and abandoned, the metrics that surprised. The podcast format of "stories from the journey" aligns with building-in-public storytelling. Potential for a podcast guest appearance (see partner-outreach.md).
- **Priority:** 4

**Team introduction:**

"Hi, we're the Aelu team. Been listening to the podcast and decided to join the community. We're learning Mandarin — around HSK 3 — and also building a study tool as a small team, which means we spend a lot of time thinking about why certain practice methods work and others don't. Looking forward to being part of the conversations here."

---

### 9. Practice Your Language

- **Server name:** Practice Your Language
- **Approximate members:** 1,000+
- **Focus:** Multi-language practice server with voice and text channels for 70+ languages, including Chinese.
- **Activity level:** Moderate. Chinese channels are less populated than Spanish or Japanese.
- **Self-promotion rules:** Resource sharing acceptable in appropriate channels. Active participation expected before sharing.
- **Engagement strategy:** Join Chinese voice practice sessions. Be a regular presence in the Chinese text channel. Because this server is multi-language, the team's participation helps build connections with polyglots who may also be studying Chinese — a different demographic from dedicated Chinese-only servers.
- **Priority:** 5

**Team introduction:**

"Hi, we're the Aelu team. Studying Mandarin Chinese, around HSK 3. Looking for speaking practice — my reading is ahead of my speaking and I need to close that gap. Happy to help with English in return."

---

### 10. GoEast Mandarin Discord

- **Server name:** GoEast Mandarin
- **Approximate members:** Small (estimated 200-500 based on school community size)
- **Focus:** Community around the GoEast Mandarin language school (Shanghai-based). Voice chat events, learning discussions, school community.
- **Activity level:** Low to moderate. Event-driven — activity spikes around scheduled voice events.
- **Self-promotion rules:** As a school-affiliated server, promotion of external tools should be handled carefully. Being a helpful community member is the approach.
- **Engagement strategy:** Participate in voice events. GoEast is a school, which means their community includes people who are already paying for structured instruction and may need a drilling supplement. This aligns with the positioning: "we are the gym; they are the coach."
- **Priority:** 5

**Team introduction:**

"Hi, we're the Aelu team. Self-studying Mandarin, around HSK 3. Joined for the voice practice events — trying to get more speaking reps in. Based in [timezone]."

---

### 11. Polyglot Coffee

- **Server name:** Polyglot Coffee
- **Approximate members:** Estimated 1,000-3,000
- **Focus:** Multi-language learning with weekly lessons, private tutoring connections, and support for 35+ languages.
- **Activity level:** Moderate. Structured around weekly lessons and events.
- **Self-promotion rules:** Community-oriented. Resource sharing in context is fine; advertising is not.
- **Engagement strategy:** Participate in Chinese-related discussions and events. Share methodology insights (FSRS, interleaving research) that apply to any language — this positions the team as someone who thinks seriously about how learning works, which builds credibility across the polyglot community.
- **Priority:** 5

**Team introduction:**

"Hi, we're the Aelu team. Primarily studying Mandarin Chinese right now — HSK 3 level. Interested in the science of language learning, especially spaced repetition and how to measure actual progress vs. perceived progress. Happy to join Chinese practice sessions and general methodology discussions."

---

### 12. Language Exchange (Discord.com)

- **Server name:** Language Exchange
- **Approximate members:** 4,700+
- **Focus:** Mass language exchange with 50+ language channels. Connect learners with native speakers.
- **Activity level:** Moderate. Chinese channels exist but are not the busiest.
- **Self-promotion rules:** Standard no-spam rules. Participation before promotion.
- **Engagement strategy:** Low-effort, low-priority. Join Chinese channels, offer English help, participate when time allows. Not a primary community.
- **Priority:** 5

**Team introduction:**

"Hi, we're the Aelu team. Learning Mandarin (HSK 3). Native English speaker. Looking for casual language exchange — happy to help with English."

---

### Engagement Priority Summary

| Priority | Server | Why |
|----------|--------|-----|
| 1 | r/ChineseLanguage | Largest serious Chinese learning community. The team's answers here reach the most relevant people. |
| 2 | 中英交流 Exchange | Largest overall. Voice practice opportunity. Native speaker access. |
| 3 | Migaku, Refold Chinese, CZ2H | Methodology-aligned audiences who value data and systems. Natural partnership potential. |
| 4 | LLC, 中文吧, I'm Learning Mandarin | Good communities with partial audience overlap. Worth consistent presence but not daily priority. |
| 5 | Practice Your Language, GoEast, Polyglot Coffee, Language Exchange | Niche or multi-language servers. Occasional presence sufficient. |

**Time allocation (Phase 1):**
- 15 min/day in r/ChineseLanguage Discord (answer 1-2 questions, participate in a thread).
- 10 min/day in 中英交流 (join a voice session once per week, check text channels daily).
- 5 min/day rotating through priority 3-4 servers.
- Priority 5 servers: check once per week.

**Total: ~30 min/day on external server engagement.**

---

## Part 3: Content Calendar (First 8 Weeks)

### Week 1: Launch Week

**Theme:** Getting started. Setting the tone.

**Daily vocabulary words:**

| Day | Hanzi | Pinyin | English | HSK | Example |
|-----|-------|--------|---------|-----|---------|
| Mon | 学习 | xué xí | to study, to learn | 1 | 我每天学习中文。(Wǒ měi tiān xuéxí zhōngwén.) — I study Chinese every day. |
| Tue | 开始 | kāi shǐ | to begin, to start | 2 | 我们开始吧。(Wǒmen kāishǐ ba.) — Let's begin. |
| Wed | 练习 | liàn xí | to practice | 2 | 你需要多练习。(Nǐ xūyào duō liànxí.) — You need to practice more. |
| Thu | 进步 | jìn bù | progress, to improve | 3 | 你的中文有很大的进步。(Nǐ de zhōngwén yǒu hěn dà de jìnbù.) — Your Chinese has improved a lot. |
| Fri | 坚持 | jiān chí | to persist, to insist | 3 | 他每天坚持跑步。(Tā měi tiān jiānchí pǎobù.) — He persists in running every day. |
| Sat | 努力 | nǔ lì | to work hard, effort | 2 | 她很努力学中文。(Tā hěn nǔlì xué zhōngwén.) — She works very hard to learn Chinese. |
| Sun | 习惯 | xí guàn | habit, to be used to | 3 | 我习惯早起。(Wǒ xíguàn zǎo qǐ.) — I'm used to getting up early. |

**Weekly challenge:** "Study every day this week — any duration counts. Post what you did in #daily-practice each day. The goal is just to show up."

**Events:**
- Monday: Server opens. the team posts welcome message, introduction, and the first daily word.
- Wednesday: the team posts his own introduction in #introductions (model the format and depth he expects).
- Friday: the team posts a "state of the server" message in #off-topic: "We're at [N] members after 5 days. Here's what I've noticed so far."
- Sunday: Weekly vocabulary recap + challenge results.

**the team's planned posts:**
- Monday: "I started learning Mandarin [X months/years] ago. Here's where I actually stand right now." [shares his own diagnostic screenshot, honestly]
- Tuesday: In #questions, asks a genuine question he has about Chinese. Models the kind of question-asking he wants to see.
- Thursday: In #tips-and-tricks, posts the first tip: "The focus command." Explains how to use it.
- Saturday: In #media-recommendations, recommends one Chinese show or podcast he actually watches/listens to. Brief review, why it is useful for practice.

**Cross-promotion:**
- Reddit: Post in r/ChineseLanguage weekly thread about starting the Discord. Frame as "started a study group for adults learning Mandarin, here's the invite if you want to join."
- Twitter/X: Tweet about the server launch. Brief, non-hype. "Started a Discord for Mandarin learners. Daily vocabulary, weekly challenges, honest progress sharing. Invite link in bio."

---

### Week 2: Building Rhythm

**Theme:** Getting comfortable with the daily cadence.

**Daily vocabulary words:**

| Day | Hanzi | Pinyin | English | HSK | Example |
|-----|-------|--------|---------|-----|---------|
| Mon | 复习 | fù xí | to review | 2 | 我要复习昨天的生词。(Wǒ yào fùxí zuótiān de shēngcí.) — I want to review yesterday's new words. |
| Tue | 发音 | fā yīn | pronunciation | 3 | 你的发音很好。(Nǐ de fāyīn hěn hǎo.) — Your pronunciation is good. |
| Wed | 声调 | shēng diào | tone (of Chinese) | 3 | 声调很重要。(Shēngdiào hěn zhòngyào.) — Tones are very important. |
| Thu | 记住 | jì zhù | to remember | 2 | 我记住了这个词。(Wǒ jìzhù le zhège cí.) — I remembered this word. |
| Fri | 忘 | wàng | to forget | 2 | 我忘了他的名字。(Wǒ wàng le tā de míngzi.) — I forgot his name. |
| Sat | 理解 | lǐ jiě | to understand, comprehension | 3 | 我不太理解这个句子。(Wǒ bú tài lǐjiě zhège jùzi.) — I don't really understand this sentence. |
| Sun | 区别 | qū bié | difference, to distinguish | 3 | 这两个词有什么区别？(Zhè liǎng gè cí yǒu shénme qūbié?) — What's the difference between these two words? |

**Weekly challenge:** "Learn 5 new measure words and use each in a sentence. Post them in #daily-practice. If you only know 个 and 本, this is your week."

**Events:**
- Thursday: First Office Hours (7:00 PM ET). the team hosts in voice channel, takes questions about Chinese learning and the app.
- Saturday: Informal reading discussion in #reading-corner. the team shares a short HSK 2-3 passage and asks: "What words tripped you up?"

**the team's planned posts:**
- Monday: In #resources, shares his top 3 resources outside of the app (Pleco, a podcast, a textbook). Brief description of how each fits into his workflow.
- Wednesday: In #tone-practice, records himself doing a set of tone pairs and posts the audio. Asks: "How do these sound? Be honest." Models vulnerability and the expectation that this channel is about getting better, not performing.
- Friday: In #daily-practice, shares a mid-week check-in on his own study: "Here's my week so far. [X] items reviewed, [Y] new, tone accuracy at [Z]%. The measure word challenge caught me — I only knew 7 measure words."
- Sunday: Weekly recap. Names members who showed up consistently (not "great job!" — just "Maria, Carlos, and Wei posted every day this week").

**Cross-promotion:**
- Blog: If the blog is launched, write a brief post about "Why I Started a Study Discord" — honest, building-in-public tone. Cross-post excerpt to Reddit.

---

### Week 3: Deepening Engagement

**Theme:** Moving beyond daily vocabulary into skill-specific practice.

**Daily vocabulary words:**

| Day | Hanzi | Pinyin | English | HSK | Example |
|-----|-------|--------|---------|-----|---------|
| Mon | 听力 | tīng lì | listening ability | 3 | 我的听力需要提高。(Wǒ de tīnglì xūyào tígāo.) — My listening ability needs to improve. |
| Tue | 阅读 | yuè dú | reading | 3 | 阅读是学中文的好方法。(Yuèdú shì xué zhōngwén de hǎo fāngfǎ.) — Reading is a good way to learn Chinese. |
| Wed | 口语 | kǒu yǔ | spoken language, speaking | 3 | 我的口语不太好。(Wǒ de kǒuyǔ bú tài hǎo.) — My spoken Chinese isn't very good. |
| Thu | 语法 | yǔ fǎ | grammar | 3 | 中文语法不太难。(Zhōngwén yǔfǎ bú tài nán.) — Chinese grammar isn't too difficult. |
| Fri | 生词 | shēng cí | new word, vocabulary item | 2 | 今天学了十个生词。(Jīntiān xué le shí gè shēngcí.) — Today I learned ten new words. |
| Sat | 句子 | jù zi | sentence | 2 | 请造一个句子。(Qǐng zào yī gè jùzi.) — Please make a sentence. |
| Sun | 意思 | yì si | meaning | 1 | 这个词是什么意思？(Zhège cí shì shénme yìsi?) — What does this word mean? |

**Weekly challenge:** "Listen to 60 minutes of Chinese audio this week (podcast, show, music, anything). Track your total. Post what you listened to and one thing you noticed about your comprehension."

**Events:**
- Thursday: Office Hours #2.
- Saturday: First Study Sprint attempt. 2-hour pomodoro session in Study Together voice channel. Even if only 2-3 people show up, run it.

**the team's planned posts:**
- Monday: In #questions, starts a discussion: "What's the one skill you know is lagging behind the others? For me, it's listening. My reading is about HSK 3 but my listening feels like HSK 2 on a good day."
- Wednesday: In #feedback, asks: "For those using the app — what's confusing? What's frustrating? I want to hear the negative stuff, not just the positive."
- Friday: In #show-your-stats, posts his own diagnostic breakdown. Names specific weaknesses.
- Sunday: Challenge recap. Summarizes what people listened to. Highlights any interesting observations.

**Cross-promotion:**
- Reddit: Share a learning observation from the week's discussions (anonymized) as a standalone post. Natural, not promotional.

---

### Week 4: Community Identity

**Theme:** The community starts to have its own character.

**Daily vocabulary words:**

| Day | Hanzi | Pinyin | English | HSK | Example |
|-----|-------|--------|---------|-----|---------|
| Mon | 方法 | fāng fǎ | method, way | 2 | 你有什么好方法？(Nǐ yǒu shénme hǎo fāngfǎ?) — Do you have any good methods? |
| Tue | 比较 | bǐ jiào | to compare, relatively | 2 | 这个比较难。(Zhège bǐjiào nán.) — This is relatively difficult. |
| Wed | 提高 | tí gāo | to raise, to improve | 3 | 我想提高我的听力。(Wǒ xiǎng tígāo wǒ de tīnglì.) — I want to improve my listening. |
| Thu | 经验 | jīng yàn | experience | 3 | 你有学中文的经验吗？(Nǐ yǒu xué zhōngwén de jīngyàn ma?) — Do you have experience learning Chinese? |
| Fri | 困难 | kùn nan | difficulty, difficult | 3 | 你遇到了什么困难？(Nǐ yùdào le shénme kùnnan?) — What difficulties have you encountered? |
| Sat | 容易 | róng yì | easy | 2 | 这个字很容易写。(Zhège zì hěn róngyì xiě.) — This character is easy to write. |
| Sun | 发现 | fā xiàn | to discover, to find | 3 | 我发现一个好办法。(Wǒ fāxiàn yī gè hǎo bànfǎ.) — I discovered a good method. |

**Weekly challenge:** "Read one full graded passage (in the app, Du Chinese, The Chairman's Bao, or any source) and post 3 words you looked up. Tell us: did you understand the overall meaning even without those 3 words?"

**Events:**
- Thursday: Office Hours #3.
- Friday: First Monthly AMA (if Week 4 falls at month-end). If not, schedule for the appropriate Friday.
- Saturday: Accountability pair matching — first round. Post in #language-exchange inviting sign-ups.

**the team's planned posts:**
- Monday: In #resources, shares a study method post: "Here's how I structure my daily sessions. [Detailed breakdown of time allocation, drill mix, and reasoning.]"
- Wednesday: In #wins, shares a genuine win of his own — no matter how small. Models the tone: honest, specific, not inflated.
- Friday: In #off-topic, asks a non-study question: "For those living in or who have visited Chinese-speaking countries — what surprised you most about daily life there?" Builds community beyond study mechanics.
- Sunday: End-of-month reflection (if applicable). "Here's what the first month looked like: [N] members, [X] daily vocabulary words, [Y] people participated in challenges, [Z] questions asked and answered."

**Cross-promotion:**
- Twitter/X: Share the end-of-month stats. Building-in-public framing.
- Newsletter: Mention the Discord community and highlight one interesting discussion.

---

### Week 5: Expanding Scope

**Theme:** Branching into culture and real-world usage.

**Daily vocabulary words:**

| Day | Hanzi | Pinyin | English | HSK | Example |
|-----|-------|--------|---------|-----|---------|
| Mon | 文化 | wén huà | culture | 3 | 中国文化很有意思。(Zhōngguó wénhuà hěn yǒu yìsi.) — Chinese culture is very interesting. |
| Tue | 传统 | chuán tǒng | tradition, traditional | 3 | 这是中国的传统节日。(Zhè shì Zhōngguó de chuántǒng jiérì.) — This is a traditional Chinese festival. |
| Wed | 交流 | jiāo liú | to exchange, communication | 3 | 语言交流很有帮助。(Yǔyán jiāoliú hěn yǒu bāngzhù.) — Language exchange is very helpful. |
| Thu | 环境 | huán jìng | environment, surroundings | 3 | 学习环境很重要。(Xuéxí huánjìng hěn zhòngyào.) — The study environment is very important. |
| Fri | 适合 | shì hé | suitable, appropriate | 3 | 这个方法很适合你。(Zhège fāngfǎ hěn shìhé nǐ.) — This method is very suitable for you. |
| Sat | 机会 | jī huì | opportunity, chance | 3 | 我有一个很好的机会。(Wǒ yǒu yī gè hěn hǎo de jīhuì.) — I have a very good opportunity. |
| Sun | 了解 | liǎo jiě | to understand, to know about | 2 | 我想了解中国历史。(Wǒ xiǎng liǎojiě Zhōngguó lìshǐ.) — I want to learn about Chinese history. |

**Weekly challenge:** "Record yourself saying 10 tone pairs and post the audio in #tone-practice. Pairs to try: 1-2, 1-4, 2-3, 2-4, 3-1, 3-4, 4-1, 4-2, 1-1, 4-4. Pick 10 words that match these patterns."

**Events:**
- Thursday: Office Hours #4.
- Saturday: Study Sprint #2. Same format. Promote 2 days in advance.

**the team's planned posts:**
- Monday: In #media-recommendations, does a detailed review of one Chinese podcast or show. Not just "it's good" — specific notes on vocabulary level, speaking speed, accent, and what skill it trains.
- Wednesday: In #tone-practice, posts a "tone challenge" — 5 audio clips of tone pairs and asks members to identify them. (Can be generated from the app's audio system or from public pronunciation resources.)
- Friday: Building-in-public post in #changelog or #off-topic: "This week I worked on [feature]. Here's why. Here's what's next."
- Sunday: Challenge recap. Tone practice is harder to summarize — the team picks 2-3 audio clips from members and gives brief, honest, constructive feedback.

**Cross-promotion:**
- Blog post: "What 35 Days of Daily Vocabulary Practice Taught Me" — references the Discord challenge without being promotional.

---

### Week 6: Knowledge Sharing

**Theme:** Community members start teaching each other.

**Daily vocabulary words:**

| Day | Hanzi | Pinyin | English | HSK | Example |
|-----|-------|--------|---------|-----|---------|
| Mon | 教 | jiāo | to teach | 2 | 她教我中文。(Tā jiāo wǒ zhōngwén.) — She teaches me Chinese. |
| Tue | 帮助 | bāng zhù | to help, help | 2 | 谢谢你的帮助。(Xièxie nǐ de bāngzhù.) — Thank you for your help. |
| Wed | 解释 | jiě shì | to explain, explanation | 3 | 你能解释一下吗？(Nǐ néng jiěshì yíxià ma?) — Can you explain? |
| Thu | 建议 | jiàn yì | suggestion, to suggest | 3 | 我有一个建议。(Wǒ yǒu yī gè jiànyì.) — I have a suggestion. |
| Fri | 分享 | fēn xiǎng | to share | 3 | 我想分享一个好资源。(Wǒ xiǎng fēnxiǎng yī gè hǎo zīyuán.) — I want to share a good resource. |
| Sat | 讨论 | tǎo lùn | to discuss, discussion | 3 | 我们讨论一下这个问题。(Wǒmen tǎolùn yíxià zhège wèntí.) — Let's discuss this problem. |
| Sun | 总结 | zǒng jié | to summarize, summary | 3 | 我来总结一下这周的学习。(Wǒ lái zǒngjié yíxià zhè zhōu de xuéxí.) — Let me summarize this week's study. |

**Weekly challenge:** "Find and share one Chinese learning resource you have never seen recommended. It could be a YouTube channel, an app, a website, a textbook, a podcast — anything. Post it in #resources with a one-paragraph review. No duplicates."

**Events:**
- Thursday: Office Hours #5.
- Friday: Monthly AMA #2 (if timing aligns).

**the team's planned posts:**
- Monday: In #questions, asks a challenging grammar question and invites more advanced members to help answer. Models the behavior of deferring to others' expertise.
- Wednesday: In #tips-and-tricks, posts a second app tip. Something specific and useful.
- Friday: In #feedback, posts a specific design question: "I'm deciding between [option A] and [option B] for [feature]. What would you prefer and why?" Genuine decision-making input, not a fake consultation.
- Sunday: Resource roundup from the challenge. Pins the best ones. Thanks specific members by name.

**Cross-promotion:**
- Share the best resource finds from the challenge in a Reddit post (credited to the members who found them).

---

### Week 7: Going Deeper

**Theme:** Moving into production-focused practice.

**Daily vocabulary words:**

| Day | Hanzi | Pinyin | English | HSK | Example |
|-----|-------|--------|---------|-----|---------|
| Mon | 表达 | biǎo dá | to express | 3 | 我不知道怎么表达。(Wǒ bù zhīdào zěnme biǎodá.) — I don't know how to express it. |
| Tue | 翻译 | fān yì | to translate, translation | 3 | 你能帮我翻译吗？(Nǐ néng bāng wǒ fānyì ma?) — Can you help me translate? |
| Wed | 正确 | zhèng què | correct, right | 3 | 这个答案是正确的。(Zhège dá'àn shì zhèngquè de.) — This answer is correct. |
| Thu | 错误 | cuò wù | mistake, error | 3 | 犯错误是正常的。(Fàn cuòwù shì zhèngcháng de.) — Making mistakes is normal. |
| Fri | 改 | gǎi | to change, to correct | 2 | 我要改一下我的句子。(Wǒ yào gǎi yíxià wǒ de jùzi.) — I need to correct my sentence. |
| Sat | 流利 | liú lì | fluent | 3 | 他说中文说得很流利。(Tā shuō zhōngwén shuō de hěn liúlì.) — He speaks Chinese very fluently. |
| Sun | 效果 | xiào guǒ | effect, result | 3 | 这个方法的效果很好。(Zhège fāngfǎ de xiàoguǒ hěn hǎo.) — This method's effect is very good. |

**Weekly challenge:** "Write 5 sentences in Chinese without using a dictionary. Any topic, any level of complexity. Post them in #daily-practice. Then look up any words you were unsure about and post corrections."

**Events:**
- Thursday: Office Hours #6.
- Saturday: Study Sprint #3. Try to get a member to co-host one in a different timezone.

**the team's planned posts:**
- Monday: In #daily-practice, does the challenge himself first. Posts 5 sentences with honest commentary: "Sentence 3 was rough — I wasn't sure about the word order with 虽然...但是."
- Wednesday: In #reading-corner, posts a passage discussion. Shares a paragraph from the graded reader and asks: "What's the hardest part of this passage? The vocabulary, the grammar structure, or following the logic?"
- Friday: In #show-your-stats, posts a two-month retrospective of his own progress. What changed, what did not, what surprised him. Data-grounded, honest.
- Sunday: Challenge recap. Highlights sentences that were creative or brave (writing in Chinese without a dictionary is hard at any level).

**Cross-promotion:**
- Twitter/X: Share an interesting sentence a member wrote (with permission). "Someone in our Discord study group wrote this sentence without a dictionary: [sentence]. HSK 2 level, three weeks into daily practice."

---

### Week 8: Assessment and Reflection

**Theme:** Measuring progress honestly.

**Daily vocabulary words:**

| Day | Hanzi | Pinyin | English | HSK | Example |
|-----|-------|--------|---------|-----|---------|
| Mon | 水平 | shuǐ píng | level, standard | 3 | 我的中文水平还不够。(Wǒ de zhōngwén shuǐpíng hái bú gòu.) — My Chinese level isn't good enough yet. |
| Tue | 目标 | mù biāo | goal, target | 3 | 我的目标是通过HSK四级。(Wǒ de mùbiāo shì tōngguò HSK sì jí.) — My goal is to pass HSK 4. |
| Wed | 计划 | jì huà | plan, to plan | 2 | 你有什么学习计划？(Nǐ yǒu shénme xuéxí jìhuà?) — What's your study plan? |
| Thu | 结果 | jié guǒ | result, outcome | 3 | 你对这个结果满意吗？(Nǐ duì zhège jiéguǒ mǎnyì ma?) — Are you satisfied with this result? |
| Fri | 继续 | jì xù | to continue | 3 | 我会继续努力。(Wǒ huì jìxù nǔlì.) — I will continue to work hard. |
| Sat | 成功 | chéng gōng | success, to succeed | 3 | 他终于成功了。(Tā zhōngyú chénggōng le.) — He finally succeeded. |
| Sun | 过程 | guò chéng | process, course | 3 | 学中文是一个长过程。(Xué zhōngwén shì yī gè cháng guòchéng.) — Learning Chinese is a long process. |

**Weekly challenge:** "Complete a diagnostic check — in the app, with a practice test, or by honest self-assessment — and share your skill breakdown in #show-your-stats. Where are your strongest and weakest skills? Has anything changed since you joined?"

**Events:**
- Thursday: Office Hours #7.
- Friday: Monthly AMA #3 (end of month 2). Focus on the community's first two months: what worked, what to change, what's next.
- Saturday: "Show Your Progress" thread in #show-your-stats. Two-month milestone.

**the team's planned posts:**
- Monday: "Two months of this server. Here's what I've learned about building a study community." Building-in-public reflection in #off-topic.
- Wednesday: In #feedback, posts a "next 3 months" roadmap discussion: "Here's what I'm planning for the app and the server. What am I missing?"
- Friday: AMA — prepared with data on community activity, app updates, and learning reflections.
- Sunday: Two-month community retrospective. Stats, highlights, acknowledgments. Asks: "What should we do differently in months 3-4?"

**Cross-promotion:**
- Blog post: "8 Weeks of Daily Mandarin Vocabulary: What Stuck and What Didn't" — references the Discord challenge data.
- Reddit: Share the community retrospective as a "building-in-public" post. Genuine data, genuine learnings.
- Newsletter: Two-month update highlighting community milestones and interesting discussions.

---

### Content Calendar Summary

| Week | Vocab Theme | Challenge | Key Event | Cross-Promo |
|------|-------------|-----------|-----------|-------------|
| 1 | Learning foundations | Daily consistency | Server launch, first Office Hours prep | Reddit launch post, Twitter |
| 2 | Memory & pronunciation | Measure words | First Office Hours | Blog post |
| 3 | Language skills | Listening hours | First Study Sprint | Reddit observation |
| 4 | Methods & difficulty | Graded reading | Monthly AMA, accountability pairs | Twitter stats, newsletter |
| 5 | Culture & context | Tone pairs | Study Sprint #2 | Blog post |
| 6 | Teaching & sharing | Resource discovery | Monthly AMA #2 | Reddit resource roundup |
| 7 | Production & accuracy | Writing without dictionary | Study Sprint #3 | Twitter member spotlight |
| 8 | Assessment & goals | Diagnostic check | Monthly AMA #3, 2-month milestone | Blog retrospective, Reddit, newsletter |

---

## Part 4: Metrics

### Weekly Metrics

Track every Sunday evening. Keep a simple spreadsheet.

| Metric | How to measure | Week 1 target | Week 4 target | Week 8 target |
|--------|---------------|---------------|---------------|---------------|
| New members | Discord server insights | 10-15 | 5-10/week | 8-12/week |
| Total members | Discord server insights | 10-15 | 35-60 | 60-100 |
| Messages per day (avg) | Discord server insights | 5-10 | 15-30 | 30-50 |
| Active members (posted at least once that week) | Manual count or bot analytics | 5-8 | 15-25 | 25-40 |
| Daily vocabulary challenge participation | Count of members who posted a sentence | 3-5 | 8-15 | 15-25 |
| Weekly challenge participation (committed) | Count of "I'm in" replies | 5-8 | 10-20 | 15-30 |
| Weekly challenge completion | Count of members who posted results | 3-5 | 6-12 | 10-20 |
| Questions asked | Count in #questions | 2-5 | 5-10 | 10-20 |
| Questions answered | Count of replies to questions | 2-5 | 5-10 | 10-20 |
| Q-to-A ratio | Answered / asked | >0.8 | >0.8 | >0.9 |

### Monthly Metrics

Track on the first of each month.

| Metric | How to measure | Month 1 target | Month 2 target |
|--------|---------------|----------------|----------------|
| Member retention (30-day return rate) | Members who were active in both current and previous month / members active in previous month | N/A (first month) | >60% |
| Top contributors | Rank members by message count + helpfulness (qualitative) | Identify top 5 | Identify potential moderators |
| App signups from Discord | Create a unique invite link (aelu.app/?ref=discord) or UTM parameter. Track in analytics. | 3-5 | 5-10 |
| Sentiment | Qualitative: read through the week's conversations. Are they positive? Constructive? Are people helping each other? | Positive | Positive + self-sustaining |
| Voice channel usage | Number of unique members who joined a voice channel that month | 3-5 | 8-15 |
| Office Hours attendance | Count of attendees per session | 2-4 | 5-10 |
| Event attendance (sprints, AMAs) | Count of attendees per event | 3-6 | 8-15 |

### Health Signals

**Green (healthy):**
- 3+ conversations happening daily without the team initiating.
- New member introductions at least 3x per week.
- Questions are being answered by community members, not just the team.
- Daily vocabulary challenge gets at least 5 responses.
- Voice channels are used at least twice per week.
- Members are referring other members ("my friend wants to join").

**Yellow (needs attention):**
- the team has to start most conversations.
- Daily vocabulary challenge gets fewer than 3 responses.
- Questions go unanswered for more than 24 hours.
- New members join but never introduce themselves or post.
- Voice channels are empty except during scheduled events.
- The same 3-4 people do all the talking.

**Red (intervention required):**
- Multiple days with zero messages (excluding #changelog).
- Members leaving without explanation (check for toxicity, drama, or stale content).
- Questions go unanswered for 48+ hours.
- No participation in weekly challenges.
- the team is the only person posting.

**Interventions by signal level:**

| Signal | Action |
|--------|--------|
| Yellow | the team increases posting frequency. Start more conversations. DM quiet members: "Hey, noticed you joined last week — how's your study going?" Post more personal content (learning struggles, progress updates). Lower the barrier for participation. |
| Red | Assess root cause: is the server too quiet (not enough members)? Too unfocused (too many channels for the size)? Too promotional (feels like a sales funnel)? Consolidate channels if needed. Post a frank message: "The server has been quiet. What would make this a place you want to spend time?" Consider temporarily archiving low-activity channels to concentrate conversation. |

### Tracking Tools

- **Discord Server Insights:** Built into Discord for servers with Community features enabled. Provides member count, message volume, and retention data. Enable Community in Server Settings.
- **Spreadsheet:** Simple Google Sheet or CSV tracking weekly and monthly numbers. the team fills it in every Sunday.
- **UTM link:** Create `aelu.app/?ref=discord` for any app links shared in the server. Track conversions in the app's analytics.
- **Manual observation:** No substitute for actually reading the conversations. 5 minutes every evening scanning channels gives qualitative signal that no dashboard captures.

---

## Appendix: Quick Reference

### Bot Checklist (setup order)

1. Enable Community features in Discord server settings.
2. Invite Carl-bot. Configure reaction roles in #roles. Configure auto-mod rules. Set up welcome DM.
3. Invite Sapphire. Configure welcome message in #welcome. Configure join/leave logging.
4. Invite Pomomo. Configure timer for Study Together voice channel.
5. Invite Apollo. Create recurring events (Office Hours, Study Sprint, AMA).
6. Set up Daily Word webhook. Test formatting. Schedule first 7 days of posts.

### Channel Creation Checklist

1. Create categories: Welcome, Study, The App, Community, Voice.
2. Create text channels with descriptions and slow mode where appropriate (5s for #daily-practice, 30s for #off-topic).
3. Set #welcome and #changelog to read-only (everyone can read, only admins can post).
4. Create voice channels with appropriate user limits (Study Together: 25, Speaking Practice: 10, Office Hours: 25).
5. Set up #mod-log as a private channel (moderators + the team only).

### the team's Weekly Time Commitment

| Task | Time | When |
|------|------|------|
| Post daily vocabulary word | 5 min/day | 8:00 AM ET |
| Check and respond in all channels | 15 min/day | Evening |
| External server engagement | 30 min/day | Varies |
| Office Hours (host) | 30 min/week | Thursday 7 PM ET |
| Weekly challenge posting + recap | 20 min/week | Monday + Sunday |
| Monthly AMA (prep + host + summary) | 90 min/month | Last Friday |
| Monthly Study Sprint | 2 hr/month | First Saturday |
| Metrics tracking | 15 min/week | Sunday evening |
| **Weekly total** | ~6-7 hours/week | |

This is a significant commitment in Phase 1-2. It reduces to ~3-4 hours/week in Phase 3 as moderators and community members take over daily engagement.
