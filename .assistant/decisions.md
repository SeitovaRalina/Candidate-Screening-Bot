# Decisions

## D-1 — Architecture: managed workflow with LLM steps, not a freely-exploring agent
The process path is known in advance (parse vacancy -> parse resume -> compare -> flag -> card). Called "agent" to the client colloquially; built and evaluated as a workflow. See `tech-details/stack.md`.
**Date:** 2026-09-04.

## D-2 — Channel: Telegram via Hermes Messaging Gateway
Per playbook default; avoids hand-rolling bot infrastructure. Confirmed by client interest in "рассматривается возможность использования бота в Telegram."
**Date:** 2026-09-04.

## D-3 — Human keeps the final hiring decision
Transcript Тема 4 confirms explicitly: "окончательное решение о приглашении на собеседование остаётся за человеком" and the human "будет проверять и подтверждать решения нейросети." The bot runs its analysis autonomously (no human needed to steer the analysis step itself), but its verdict is advisory. This resolves the apparent tension with Тема 3's "оценка резюме без первичного участия человека" — that line describes the analysis step, not the final decision.
**Date:** 2026-09-04.

## D-4 — Every verdict/red-flag must cite resume evidence
Client requirement, stated twice in the transcript (Тема 3 and Тема 4): must be able to explain decisions by quoting the resume/vacancy. Non-negotiable design constraint, not a nice-to-have.
**Date:** 2026-09-04.

## D-5 — hh.ru personal-account login excluded from MVP
Regardless of technical feasibility findings from OQ-5, personal-account login is out of MVP scope pending explicit client approval and guardrail review. See `open-questions.md` OQ-5 and `product-overview/anti-stories.md`.
**Date:** 2026-09-04.
