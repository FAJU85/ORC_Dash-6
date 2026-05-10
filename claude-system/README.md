# Claude Code — نظام الوكلاء المتكامل

نظام **45 وكيل** + **12 مهارة** + **11 أمر** يعمل في claude.ai/code ومن terminal.

## المحتويات

```
.claude/
├── agents/    ← 45 وكيل (SDLC + Dev + Advanced + Upgrades)
├── skills/    ← 12 مهارة متخصصة
├── commands/  ← 11 أمر (/new-bot, /deploy, ...)
├── hooks/     ← 6 hooks تلقائية
├── CLAUDE.md  ← قواعد التوجيه
└── settings.json
```

## التثبيت

### على GitHub (claude.ai/code)
```bash
cp -r .claude/ your-repo/
git add .claude/
git commit -m "feat: Claude Code agent system"
git push
```

### على الجهاز (CLI)
```bash
cp -r .claude/ ~/.claude/
```

## الاستخدام

اكتب طلبك مباشرة:
```
"أنشئ بوت تيليجرام يجيب بـ AI"     → /new-bot
"ابنِ API لإدارة المهام"            → /new-api
"أريد صفحة هبوط"                  → /new-page
"راجع الكود قبل النشر"            → /review
"انشر المشروع"                    → /deploy
```

## الوكلاء الرئيسيون

| الوكيل | الدور |
|--------|-------|
| `project-manager` | ينسّق جميع مشاريع جديدة |
| `sdlc-orchestrator` | يُشغّل 8 طبقات SDLC |
| `board-of-directors` | يصوّت على القرارات الحرجة |
| `self-improver` | يحسّن النظام بعد كل مشروع |
| `troubleshooter` | يُصلح الأخطاء تلقائياً |
| `security-auditor` | OWASP scan قبل كل deployment |
