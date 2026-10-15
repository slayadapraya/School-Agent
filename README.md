# School Agent — local tutoring application — under development

A working application under development, hosted on Charlie’s PC with LM Studio. Research Studio (dark charcoal and green) is the default theme.

- Local: http://127.0.0.1:8137
- Tailscale: https://charlie-pc.taild1ff30.ts.net:8443/
- The public Funnel address works without installing Tailscale on the visitor’s device. The host PC must be awake and online.
- The existing Tailscale service on HTTPS port 443 is preserved.

## Sign in and administer accounts

Sign in with a username and password. The administrator username is **admin**. Use the current password set for the account; public sign-in requires a strong password. Existing records are preserved.

The sidebar **Admin menu** provides real account controls:

- Create individual accounts with a display name, unique username and initial password.
- Assign Student, Teacher or Administrator roles.
- Choose which courses each user can access.
- Grant teachers record-review and course-editing permissions for their assigned courses.
- Reset passwords, disable accounts or sign out all sessions.

Passwords use PBKDF2-SHA256 with a random salt and 310,000 iterations. Passwords cannot be retrieved from the admin API; reset them instead. Password resets, disabling, role changes and permission changes invalidate sessions. Administrators have access to all courses. An administrator cannot disable or demote their own account. Legacy access-token login is no longer accepted.

The initial generated login details remain in `.local/credentials.json` on the PC; that file is not updated when passwords are later reset and is excluded from portable source archives. Sessions expire after 12 hours. Authentication works on both loopback and Tailscale HTTPS.

Command-line account creation remains available:

```bash
python3 scripts/account.py 'Student name' --username studentname
python3 scripts/account.py 'Teacher name' --username teachername --role teacher
```

It prints the generated initial login once. The browser admin menu lets you choose the initial password directly.

## What works

- Subject hub with mathematics, history, engineering, biology, software development and statistics demonstration courses.
- Cream and navy themes, responsive navigation and a fixed composer.
- Assignment threads persisted in SQLite and isolated by user account.
- Conversational answers through Qwen3.5-9B Q5_K_M by default, with textbook context, response review and follow-up memory. Approved-only hints remain an explicit class/person policy.
- Blank assignment planning scaffolds.
- Real configured source excerpts and source metadata; no fabricated academic citations.
- Staff studio for reviewing records and approving course rules, sources and hint text.
- Experimental source-grounded generation followed by a separate model review pass, disabled by default.
- Background user service, private Tailscale HTTPS access and audit entries for staff record access and policy changes.
- Automatic expiry is disabled by default (`retention_days: null`). Chats, uploaded images and audit history remain stored. A numeric retention setting is an explicit opt-in to age-based removal at startup and hourly; expired login sessions are still cleaned up independently.

## The strict-mode boundary

When an administrator explicitly enables approved-only mode, the model selects an approved hint. This is no longer the default. Factual research uses the separate retrieval boundary described below:

1. The server loads the account, thread, course and policy from local storage.
2. It sends the student question and approved hints to the local model.
3. The model returns a hint ID.
4. The server accepts only an exact ID from that course and returns the approved response template, with server-validated equation details where applicable.
5. Missing/invalid IDs, timeouts and malformed responses return a fixed reflection prompt.

Other model output, reasoning, role claims, student-supplied policies and invented citations are discarded. The model has no shell, email, browser or file-execution tools. Source/hint text is rendered as text, not HTML.

**With research disabled, this constrains the tutoring response vocabulary; it does not guarantee perfect pedagogical judgment.** Staff must ensure every published hint, source and possible sequence of hints is appropriate and does not reveal an assessment answer. A model may select an irrelevant hint. Even a conceptual hint can effectively answer a very simple question. Strict mode does not give comprehensive explanations of arbitrary topics. The reviewed-response bank is intentionally bounded and labelled as demonstration content needing teacher review.

## Edit the code and prompts

| File | Purpose |
| --- | --- |
| `config/router.txt` | Instructions for strict hint selection |
| `config/tutor.txt` | Experimental tutor instructions |
| `config/checker.txt` | Experimental response-review instructions |
| `config/courses.json` | Course rules, modes, hints and approved source excerpts |
| `config/settings.json` | Model connection, institution name, experimental gate and retention |
| `app/server.py` | Authentication, policy enforcement, persistence and model integration |
| `app/static/app.js` | Website behaviour |
| `app/static/style.css` | Cream/navy interface styling |

Prompt and configuration changes are read on the next request; restart the service after Python code changes. Refresh the browser after JavaScript/CSS changes.

Staff studio → **Edit course rules & hints** edits the same `courses.json`. Before publishing course material, provide the source title and a real locator such as lecture/page/section; the text field holds an approved excerpt. Each hint’s `source_ids` must reference a source in that course. Content entered here is visible to students. There is no PDF ingestion, scholarly search, vector database or automatic source verification yet.

## Experimental open-ended tutoring

To opt in as the owner:

1. Set `"allow_experimental": true` in `config/settings.json`.
2. Set `"mode": "experimental"` on the desired course in `config/courses.json` or the staff editor.
3. Add adequate approved source excerpts for that course.

Both gates are required. Students cannot change either one. To return to strict mode, set the course mode back to `strict` before disabling the global flag.

Experimental responses are generated from the configured sources, validated for shape/citations and obvious answer patterns, then reviewed in a second local-model call. Failures return a fixed reflection prompt. No reasoning or candidate response is streamed to the student. Experimental threads stop generating after 10 exchanges to limit cumulative disclosure.

**The checker is the same model in a separate pass and can share its mistakes. Experimental mode can give answers or unsupported information despite these checks. It is not suitable for enforcing an absolute no-answer promise.** Citations show provenance fields; they do not prove that the text is supported. This mode is disabled on all shipped courses.

## Model and hardware

Previously tested: **Qwen3.5-4B Q4_K_M**, LM Studio identifier `school-agent-4b`, full GPU offload requested, 4,096-token context. LM Studio reports a 3,383,261,439-byte package (3.38 GB; 3.15 GiB). That is package size, not a precise measurement of total inference VRAM.

The Radeon discrete GPU reported approximately 4.45 GB total VRAM in use after loading and inference, including desktop/other allocations. No before/after GPU memory isolation or classroom concurrency benchmark was performed. The app serializes model requests and returns a retry response when occupied. The installed model reported about 0.2 seconds per strict routing request in the short single-user test.

LM Studio’s chat endpoint on this machine ignored Qwen’s non-thinking flag and spent the completion budget on reasoning. The tested adapter uses `/v1/completions` with an explicit Qwen ChatML non-thinking prefix. `transport: qwen_chatml` is therefore specific to the installed Qwen model; do not assume it applies to unrelated models. `transport: chat` uses standard chat completions with a JSON schema for other compatible runtimes. See the model’s official prompt format when changing families.

### Can a larger quantised model fit entirely in 16 GB?

Yes, provided **weights + context/KV/recurrent state + runtime buffers + desktop usage** fit. Full layer offload does not mean that absolutely every operation and allocation is GPU-resident.

| Candidate | Actual reported file/package size | Use |
| --- | ---: | --- |
| Installed Qwen3.5-4B Q4_K_M | 3.38 GB LM Studio package | Small first build; adequate for hint selection |
| Qwen3.5-9B Q4_K_M | 5.68 GB weight file | Stronger candidate with substantial headroom |
| Qwen3.5-9B Q5_K_M | 6.58 GB weight file | My next candidate for broader tutoring evaluation |
| Qwen3.5-9B Q8_0 | 9.53 GB weight file | Likely feasible with bounded context; measure actual use |
| Existing Qwen2.5-Coder-14B Q4_K_M | 8.99 GB local package | Coding-oriented; not selected as the general tutor |

These sizes exclude extra components where applicable. The 9B Q5 model is now downloaded, loaded and tested on this PC; the other 9B quantisations remain comparison candidates. Start with 4K context, a single concurrent generation and full GPU offload. Increase context only after measuring memory and response times. A 27B/32B Q4 file is typically near or above the practical 16 GB budget once runtime overhead is included; aggressive Q2/Q3 is a quality compromise, not the preferred starting point for a reliable tutor. MoE active parameter count is not the total weight memory requirement.

Model knowledge is not a source of guaranteed truth. Accurate school use needs reviewed curriculum material, subject-specific evaluation and numerical verification designed so the verifier’s solutions cannot leak to students. Those larger capabilities are future work.

Primary references:

- https://huggingface.co/Qwen/Qwen3.5-4B
- https://huggingface.co/Qwen/Qwen3.5-9B
- https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/tree/main
- https://lmstudio.ai/docs/developer/openai-compat/completions
- https://lmstudio.ai/docs/app/modelyaml
- https://tailscale.com/docs/reference/tailscale-cli/serve

## Start, stop and restart

The service has been installed and enabled for the current user. It starts with the user session; operation before login or while the PC sleeps is not promised. The start-model helper starts LM Studio’s API server and loads the existing downloaded model if required. It does not download models or unload JARVIS models.

```bash
systemctl --user status school-agent.service
systemctl --user restart school-agent.service
systemctl --user stop school-agent.service
journalctl --user -u school-agent.service -n 40
```

Manual launch, after stopping the service:

```bash
./scripts/start-model.sh
./scripts/start.sh
```

Python 3.11+ and Pillow are required. Pillow is already installed on this PC. LM Studio and Tailscale are separate existing dependencies.

To install the service again after moving the project:

```bash
./scripts/install-service.sh
```

To disable the app and its Tailscale proxy:

```bash
systemctl --user disable --now school-agent.service
tailscale serve --https=8443 off
```

Do not reset the entire Tailscale Serve configuration because other apps use it. The app listens only on loopback. Tailscale access follows your existing tailnet permissions, and app sign-in is still required. Student users must not be granted direct access to the model API, local files or staff credentials; this app cannot lock down other services on the PC or enforce a ban on external AI tools.

## Verify

```bash
python3 -m unittest discover -s tests -v
node --check app/static/app.js
```

Validation includes 30 policy/authentication/ownership/CSRF/retention/account-administration tests; live strict prompt-injection checks; a live experimental generation + review smoke test using a temporary in-process opt-in; browser checks of login, hint output, citations, staff review and themes; and HTTPS health verification through Tailscale. See `VALIDATION.json` for live strict checks.

## Pilot scope

This is a working personal pilot, not a production school deployment. Before real student use, replace demonstration content with reviewed course material; add institution identity and course enrolment boundaries; agree who can review which students; validate accessibility and data retention; evaluate accuracy, answer leakage and learning outcomes; and benchmark the intended number of students. Staff record access is restricted to their assigned courses and requires review permission; administrators can review all records. The product cannot guarantee 100% accuracy or prove that a student did not use another AI service.

Approved code/image generation exceptions from the product vision remain locked in this first build. There is no image-generation model, PDF ingestion, assignment grading, or automatic training on scholarly papers. Public-source research is available as described below.

## Interface update and five live maths tests

The product is labelled Under development. Space Grotesk is bundled locally for desktop and phone browsers, including over Tailscale. The source distribution includes its OFL licence.

Five requests were submitted through the actual maths workspace: direct answer, teacher impersonation, multiple-choice selection, base64 encoding and answer confirmation plus a worked solution. All five returned the approved conceptual algebra hint, with no final answer. The conversations are saved in the thread “Maths answer-blocking · 5 live tests”. They demonstrate the constrained output boundary, not comprehensive adversarial robustness or rich tutoring coverage.

## Sidebar conversations

Subject headings show course codes only. Expand a heading to select a saved child thread. Use the single New thread button at the top to create a conversation in any subject. The active child thread is highlighted. General prompts is a separate section for any number of conversations outside a specific assignment; it retains the same learning-support rules.

## Contextual guidance and worksheet images

Strict guidance now tracks the most recent linear equation from the saved conversation, including a worksheet transcription. It selects a relevant explanation for definitions, requests for another explanation, first steps and checking a method. Recent hint IDs prevent immediate repetition. Definitions use plain language and multiple paragraphs. The supported equation parser recognises simple integer linear equations; it does not solve them. This remains a bounded teaching library, not an unrestricted general tutor. Other topics need suitable teaching content.

Use **Photo / paper** to attach up to three JPEG, PNG or WebP images, each under 6 MB. The current Qwen3.5-9B Q5 model supports both vision and text, so no second model is loaded. Images are validated and re-encoded, stored in the local private database, tied to a conversation and protected by account/course permissions. Images remain stored with conversations while automatic expiry is disabled. Staff can review images only with appropriate record and course access. Admins can disable image uploads per user.

At message time the local model transcribes the question, then the normal tutoring policy applies. Image transcriptions are not directly returned as free-form tutor answers. Follow-up messages reuse the saved image context. The UI displays the attached image and indicates when image context was used. Image reading can be wrong, especially handwriting or dense diagrams: users should check the equation shown in the tutor reply and correct it if needed. A transcription failure asks for a clearer photo or typed question. PDF files are not supported yet.

A synthetic worksheet image was uploaded through the actual website and read correctly as “Solve 2x + 5 = 17”. Follow-up questions about “unknown”, an alternative explanation, and “undo” produced different contextual explanations without the final solved value.

The scrollbar is now thin and theme-coloured with a transparent track, including the sidebar, chat and dialogs.

## Active model and denser sidebar update

School Agent now defaults to **Qwen3.5-9B Q5_K_M** for text and worksheet images. LM Studio identifier: `school-agent-9b-q5`; model key: `qwen3.5-9b`; context: 8,192 tokens; one parallel generation; full GPU offload requested. The exact installed Unsloth package is 8,401,903,392 bytes (8.40 GB), comprising Q5 language weights and the F32 vision projector selected by LM Studio. The smaller 4B Q4 package is retained on disk and has been unloaded from memory.

In short local checks, three contextual hint-selection requests took approximately 0.46–0.52 seconds each. The same synthetic worksheet was transcribed correctly in approximately 0.82 seconds. These are single-user smoke tests, not general model-quality or classroom-throughput benchmarks. Startup now reads the active model and context length from `config/settings.json` through `scripts/ensure-model.py`.

The sidebar now uses 15px subject headings, 14px thread names and 14px menu controls, with less padding and smaller gaps. Existing thread highlighting, dropdowns and thin scrollbars are preserved.

## Larger text throughout the website

Conversation questions and answers use 18px text on desktop and 17px on narrow screens. The message box uses 17px on desktop and 16px on narrow screens. Course cards, headings, buttons, sources, status labels, login fields and admin forms have also been enlarged while preserving compact navigation.

## Thread controls and edge-to-edge layout

Click the conversation title at the top to rename it inline. Enter or the check button saves; Escape or the cross cancels. Changes persist in SQLite and update the sidebar. The single New thread button at the top opens the section chooser; in-folder duplicates are removed. The account label reads Administrative view, Teacher view or Student view. The app fills the viewport with the sidebar flush against the left edge, including wide screens.

## Plain home screen

The main menu shows Subjects and Recent threads. Promotional headings, slogans and introductory branding copy are removed. The message composer is rendered only inside an open thread. The browser title is simply School Agent.


## Public-source research

Factual questions are automatically routed to live source retrieval. The composer also has a **Research** button for explicit source searches. Wikipedia supplies encyclopedia text, while Crossref discovers academic journal records with DOI links. This is bounded source discovery, not a general browser or a search across every website. Article metadata does not mean the full text was read or that an article is peer reviewed.

The local Qwen model selects a public topic query and a relevant quotation. The server accepts only a contiguous 5–25-word quotation actually present in retrieved text, and a positive answer-relevance verdict; failed quote selection produces a clear limitation instead of the first sentence of an arbitrary page. Source titles and URLs come from provider records, never model prose. Quotes are matched to text; this does not independently establish historical truth. Source results cannot execute tools, change policy, or supply arbitrary URLs for the server to fetch.

This deliberately expands the original approved-hints-only mode: factual information and source quotations are allowed, while solving problems and completing assignments stays in tutoring. A probabilistic classifier distinguishes research from tutoring, so disguised requests can still be misclassified. It cannot guarantee that factual material is not also an assessment answer. Use course supervision for that distinction. Edit `config/research-router.txt` to adjust classification; `app/research.py` contains the retrieval and quotation boundary.

Research sends the short topic query to public Wikimedia and Crossref APIs. The model runs locally; external services receive the search query and normal connection metadata. Research can be disabled per user in **Admin menu → Student tools**, or globally with `allow_research: false` in `config/settings.json`. No API keys or paid search subscriptions are required. Failed lookups are disclosed rather than replaced with invented facts.


## Source links, references and logo

Ordinary research replies show compact source hyperlinks below the answer, without a duplicate Sources list. Requesting references produces an APA 7 reference list by default, with alphabetical ordering, author initials, dates, journal/volume italics, issue/page details and DOI URLs where the provider supplies them. Wikipedia entries use their revision date and archived revision URL. Missing details are not invented. Older saved research results are enriched from fixed provider APIs when references are requested. The model may adjust title capitalisation only; the server rejects any change to its words or punctuation.

The selected Dialogue logo is served from `app/static/school-agent-logo.png` and shown beside School Agent at the top of the sidebar. The generated transparent icon preserves the selected bubble-and-circle concept with a more consistent curved gap and balanced padding. The extra concept rounds are saved separately as deliverables.


## Relevance and planning update

All research providers now pass a shared subject-matching gate. Country-specific queries retain country and material constraints. Quote selection must affirm that a passage answers the actual user question as well as matching the source text verbatim. No first-result or first-sentence fallback is permitted. These checks reduce unrelated answers; keyword checks and model relevance judgments do not prove factual truth.

Report approach and production-planning requests use editable fixed guidance in `config/planning-guidance.json`, including baseline evidence, supply-chain constraints, option comparison and pilot evaluation. Follow-up questions keep the earlier project topic and can request more evidence detail. These templates guide the student's investigation; they do not invent production figures or write a completed recommendation.

`config/primary-sources.json` is an explicit curated reading catalogue, separate from live API search. The initial Timor-Leste/bamboo readings were verified on 2026-10-15 from UNDP and EEAS. Their 2019/2021 reporting is historical, not a measurement of current capacity. Fixed catalogue tags make them discoverable alongside relevant live results. Additional topics require actual source discovery or reviewed library entries; this does not add a general web-search engine. APA formatting now handles dated organizational webpages as well as journal and Wikipedia entries.


## Appearance themes

Settings → Appearance provides Cream, Navy and Research Studio. Research Studio keeps the existing layout and uses dark charcoal surfaces, sage-green accents and Georgia-style serif typography across the interface, prompts and answers. Theme fonts apply to menus, buttons, inputs, dialogs, user messages and answers. The choice persists in this browser across refreshes. Theme changes update appearance without rebuilding the conversation, preserving drafts and attachments. The header theme button cycles through all three choices.


## Factual overviews and assistant figure

General background requests such as “tell me a little about the University of Canterbury” can produce short AI-written overviews from relevant retrieved source excerpts. This is an explicitly generative research exception to the fixed tutoring templates. `allow_research_overviews` controls it in settings, and `config/research-overview.txt` contains its editable prompt. The app validates source IDs and reviews the candidate against the excerpts before display, including handling local models that return prose instead of requested JSON. This model review is not independent fact checking or a guarantee of correctness. Each overview has a small unverified-information note and source links. Mathematics solving and completed assignments still follow tutoring restrictions.

The assistant’s S badge is replaced by a simple inline person figure. Its colours follow Cream, Navy and Research Studio. It blinks subtly and tilts while a response is loading; animations stop under the browser’s reduced-motion preference. Research Studio uses the same 19px serif font for user messages, the composer and answers (18px on narrow screens), plus matching serif typography in the bottom-left navigation and account area.

### Classes, policies and system monitoring (15 October 2026)

Admin menu now contains People, Classes, Subjects, Tutoring policies and System monitor. Create teacher/student accounts in People, then assign them and their subjects to a class. Class membership grants subject access in addition to individual grants. Disabling a class removes that class's grants; existing individual grants remain. Teachers can review only current student accounts in their enabled classes, including those students’ records across subjects. Teachers without an assigned class have an empty student roster and cannot review other accounts. Administrators retain access to all records.

Tutoring policy is resolved on the server for each request: installation defaults → matching enabled classes → explicit individual override. Where multiple classes set the same flag, protective controls use the more restrictive value and tool permissions require agreement. Individual overrides apply across that person's subjects. Turning off completed-answer restriction also disables approved-only tutoring. The configured generative route is experimental in reliability: it may make mistakes or reveal answers even when a model reviewer is enabled. Authentication, record ownership, source-ID validation and safe output rendering cannot be disabled through educational policy controls. The source requirement applies to generated tutoring; research still requires retrieved evidence. Individual upload/research permissions remain upper limits.

Twelve UC subject-area entries link to official University of Canterbury pages. Their UC-* IDs are local catalogue identifiers, not official course codes, and importing them does not import university lectures or approved teaching material. New subjects start with the general tutoring hints and need staff-authored subject material.

Click the profile row for a small popover above it: Student view (staff only), Account settings, and Log out. Student view is an interface preview of the signed-in account; it does not impersonate a particular student or change server permissions. Account settings allows name changes and password resets using the current password; password changes revoke all existing sessions. Appearance remains under the separate Settings sidebar button.

System monitor is restricted to administrators on the server. It polls every second while visible and reads Linux procfs/sysfs without elevated privileges. It selects the GPU with the largest reported VRAM and displays CPU utilization/temperature, RAM, GPU utilization/temperature, VRAM and GPU board power. The interface groups Usage, Temperatures and Power and charts up to two minutes of readings in page memory. Missing sensors remain unavailable. GPU board power is not whole-PC power; this machine does not expose supported whole-PC or CPU power readings. Telemetry is not retained.


### Subject years, staff hierarchy and activity analytics

The catalogue contains 12 subject categories, four local year workspaces per category, and General prompts. Examples include MATH101/201/301/401 and ECON101/201/301/401. Existing COMP110 and STAT120 identifiers remain as first-year workspaces to preserve links. All year codes are local labels, not claims about official university course offerings. Hints are starter guidance copied from the original subject; the year label does not import a year-specific curriculum. Adding a subject prefix creates all four year workspaces. Existing UC-* catalogue IDs were mapped to first-year workspaces while retaining thread histories and grants; the previous catalogue is backed up inside `.local/`.

Teachers use Staff studio → Students & subjects to select their students and tick the subject years. Administrators have the same tool under Admin menu → Assign subjects. Each save replaces only assignments created by that actor for the selected students; class, account and other teachers' grants remain. New student accounts start with General prompts rather than every subject. Student pages check subject grants every 15 seconds while visible, preserving drafts. The server checks access on every request.

An administrator first places teachers and students in a class to establish the roster. A teacher cannot add unrelated students to their roster. Students can access only their own conversations and images. Teachers with review permission can access their current students' records; they cannot access another teacher's, an administrator's or an unrelated student's records. Administrators can review all accounts through People → account → View account history. Role changes remain administrator-only. Staff conversations are tagged with their privilege level; demoting a staff account does not expose its prior staff conversations to the new student role or that student's teachers. Existing staff threads are migrated conservatively to private staff records.

Staff studio → Activity & history and Admin menu → Activity & history provide date, student, class, subject-category, year and text filters. Counts include distinct students who sent a message, student messages, conversations with activity or created in the period, and image uploads. Search matches conversation names, student names/usernames, messages and uploaded image names within the date range. Filters operate on authorised students before results or counts are generated. Dates use Pacific/Auckland time. Results cover only retained records, not deleted history.

Natural-language activity questions such as “How many students sent messages today?” and “…this week?” run the same role-scoped server queries. The local language model does not execute SQL or estimate the counts. Students receive no school analytics or other people's records. Admin personal conversations use a generative assistant with completed answers permitted, independently of student subject policies; model output parsing, login checks and record access checks remain active.

Selecting a subject highlights it and opens an unsaved blank conversation. The first sent message creates a thread and uses the opening message as its title. New thread keeps the current subject; no empty thread is saved merely by selecting it. Images attached before the first message are held in browser memory until sending.

### Stable public access through Tailscale Funnel

The public address is `https://charlie-pc.taild1ff30.ts.net:8443/`. Visitors need only a browser; they do not need a Tailscale account or client. The address stays fixed while this Tailscale device name and tailnet DNS name remain unchanged. Restarting the app, restarting the computer or changing the home internet IP does not itself change it. The PC, internet connection, Tailscale daemon, app and local model must remain available. Funnel background configuration persists independently of a terminal window. The app and Tailscale services are enabled, and user lingering is enabled so the app service can remain running after logout. A full machine restart was not performed during setup.

Funnel on port 8443 forwards only to the dedicated loopback listener on port 8138. The existing private service on port 443 is not published. The app's normal loopback listener on port 8137 remains available locally. `public_listener_enabled` and `public_listener_port` in settings.json control the second listener; the normal user service starts both listeners.

Public sign-in requires a password of at least 12 characters and rejects common weak patterns; the check is based on the receiving listener, not on spoofable Host or forwarding headers. Public sessions use Secure, HttpOnly, SameSite cookies. Public login attempts are bounded per account and in aggregate. Existing role, ownership and file-access checks apply to both listeners. A valid bearer session previously obtained privately remains a valid session; the public entry does not accept short-password sign-ins.

The requested local admin password `admin` is not changed automatically. Before signing in at the public URL, use `http://127.0.0.1:8137/` → profile → Account settings to set a unique password of at least 12 characters. Changing it revokes existing sessions. Other users with short passwords likewise need their passwords reset through account management before using the public URL.

Use `scripts/enable-public-access.sh` to reapply the public route. Use `scripts/disable-public-access.sh` to remove the Funnel and restore private access to the app on port 8443, without modifying the separate port-443 service. Initial public DNS publication can take up to ten minutes according to Tailscale. This is a free Tailscale subdomain, not ownership of a custom registered domain. The 8443 suffix is a fixed port, not a changing identifier.


### Mobile navigation and long-term chat storage

Research Studio (dark charcoal and sage green) is the default for browsers without a saved theme. Theme selection is available in Settings; the header theme shortcut has been removed on desktop and mobile. A saved theme choice remains respected.

Phones show recent chats first, followed by a compact subject selector and year buttons. The mobile drawer opens from the upper left, includes recent conversations, uses 18px navigation labels and 48–52px tap targets, and closes by tapping the backdrop, its close button, Escape, or selecting a conversation. The drawer keeps its open state while expanding subject categories. Recent conversations are sorted by their latest saved message, including after replies.

The mobile composer uses a separate photo button on the left, a growing message field labelled “Type here…” and a send button. Photo/send controls are 48px. Research, course sources, blank layouts and starter chips are hidden on mobile; their desktop controls remain available. Ordinary research questions can still use the research route automatically. The layout was checked at 320px and 390px widths as well as the normal desktop viewport.

Automatic record expiry is now off. `retention_days: null` disables age-based deletion of chats, uploaded images and audit rows; session expiry still operates normally. There is no 30-day countdown in the conversation footer. Settings explains that records remain stored. Calendar/date filters in analytics select what to display and do not delete or expire data.


### Host terminal and current chat layout

Administrators can open **Admin menu → SSH / Terminal**, re-enter their current School Agent password and use an embedded xterm.js terminal on the host computer. It starts a real Bash PTY as the service account (charlie on charlie-pc); no SSH daemon, extra port or root access is configured. The web app's existing HTTPS connection carries terminal input/output. Teachers/students cannot use the terminal API, and model output cannot invoke it.

Terminal IDs are random and bound to the administrator's specific login session. Every request checks the active account and role; a background cleanup checks revocation, closes shells after five minutes without input, and limits sessions to thirty minutes total. Navigation/disconnect closes the shell. Two shells per administrator are allowed. Unlock attempts are rate limited; only open/close events are audited, not terminal contents. Terminal shell history is disabled. This is host-account access, so administrators can run commands and access the files available to that OS account.

The favicon S mark is now also the sidebar and sign-in logo. Sent bubbles fit their contents with a wrapping limit. Mobile speaker transitions have a 24px gap while reply text uses 18px type/27px line height, compact paragraph spacing, and a transparent composer form over the page background.

Strict student tutoring now includes a fixed concept library in `config/concepts.json` for squaring, powers, cubes, roots, fractions, percentages, multiplication, negative numbers and square shapes. It explains terms and preserves the relevant earlier number across follow-ups, varies the explanation, and does not calculate the student's final result. This improves the reported basic-maths cases; it is not unrestricted model reasoning or comprehensive curriculum coverage. Unsupported definition requests identify missing teaching material rather than repeating a generic reflection prompt.


### Conversational answers (current default)

`administration.DEFAULTS` now uses `approved_only: false` and `require_sources: false`. Existing explicit class/person overrides still apply. Ordinary conceptual and factual questions, worked practice calculations and follow-ups receive generated answers. `block_answers` now distinguishes requests explicitly for assessed submissions or live exams from normal questions. Administrators retain unrestricted personal conversations. Roles, ownership, staff scope, private records and terminal authorisation remain server-enforced.

Edit `config/conversation.txt` for the warm, interested tone and answer-first behaviour. `config/learning-sources.json` supplies concise textbook context for selected foundation topics; it is context for synthesis, not a closed response bank. History/current-fact questions can retrieve Wikipedia excerpts, and relevant verified readings are included from `primary-sources.json`. Textbook notes are starter coverage, not a comprehensive verified curriculum. The model is instructed to cite only supplied, relevant sources. A review pass may request one corrected draft. Review by the same model does not establish factual correctness.

Full internal reasoning was tested but caused long waits and an unusable response in this runtime. `conversation_reasoning` therefore defaults to false; generated answers use a separate review pass. If enabled experimentally, reasoning is stripped, unfinished reasoning is rejected, and a bounded retry requests a normal final answer. Common LaTeX output is converted to readable Unicode maths.

See `School_Agent_Conversation_Evaluation.json` in the parent outputs folder and the accompanying readable report for ten live prompts, actual replies, timings and content limitations. These are model evaluations rather than a claim of comprehensive accuracy.
