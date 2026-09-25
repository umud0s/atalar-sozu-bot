# Atalar Sözü Bot

Yalnız Azərbaycan dilində maarifləndirmə Telegram botu.

Əsas sənəd: `YOL_XERITESI.md`

Qısa işə salma:

```bash
cd atalar-sozu-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env içində BOT_TOKEN-i yaz
python bot.py
```
