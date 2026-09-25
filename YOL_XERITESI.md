# Atalar Sözü Botu — sıfırdan yol xəritəsi

Bu sənəd botu heç vaxt yazmamış adam üçündür. Kompüteri bilirsinizsə, bu addımları ardıcıllıqla getmək kifayətdir.

Hazır qovluqda var:

- `bot.py` — işlək bot
- `proverbs.json` — 35 atalar sözü
- `requirements.txt` — kitabxanalar
- `.env.example` — token şablonu
- `tools/add_proverb.py` — bazaya yeni sətir əlavə etmək

---

## 0. Nə qurursan (1 səhifəlik şəkil)

İstifadəçi Telegram-da bota yazır.

Bot iki iş görür:

1. **Açar söz.** «dost» yazırsan → bazada «dost» keçən atalar sözləri gəlir.
2. **Hekayə.** Vəziyyəti danışırsan → eyni axtarış, amma bütün cümlənin sözləri ilə.

Texniki zəncir belədir:

```
Telegram → BotFather tokeni → sənin kompüterində Python bot.py
         → proverbs.json oxunur → cavab Telegram-a qayıdır
```

Bot işləyəndə sənin kompüter (və ya server) açıq qalmalıdır. Əks halda bot cavab verməz.

---

## 1. Lazım olanlar

- Telegram hesabı (telefon nömrəsi ilə)
- Python 3.10 və ya daha yuxarı
- İnternet
- Mətn redaktoru (VS Code, Cursor, hətta Notepad)

Yoxlama (terminal):

```bash
python3 --version
```

`Python 3.10` və ya `3.11` / `3.12` görməlisən. Yoxdursa:

- Windows: https://www.python.org/downloads/ — quraşdıranda **Add python.exe to PATH** işarələ
- macOS: `brew install python`
- Linux: `sudo apt install python3 python3-venv python3-pip`

---

## 2. BotFather: bot yaratmaq və token almaq

Token botun şifrəsidir. Kimdə token varsa, bot sənin adından mesaj göndərə bilər.

1. Telegram-da axtar: `@BotFather`
2. Mavi tikə bax. Saxta BotFather-lərə token vermə.
3. Yaz: `/newbot`
4. Ad soruşulanda, məsələn: `Atalar Sözü`
5. İstifadəçi adı soruşulanda `bot` ilə bitməlidir, məsələn:
   - `atalar_sozu_bot`
   - `atalarsozu_az_bot`
   Əgər ad doludursa, başqa variant yaz.
6. BotFather sənə belə bir sətir verəcək:

```
7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Bu **token**dir.

7. Tokeni təhlükəsiz yerə kopyala. Çata, Instagram-a, GitHub-a atma.

### Botu gözəl etmək (eyni BotFather söhbətində)

`/setdescription` seç, botunu seç, yaz:

```
Azərbaycan atalar sözlərini açar söz və hekayə ilə tapır. Yalnız Azərbaycan dilində.
```

`/setabouttext`:

```
Atalar sözü maarifləndirmə botu
```

`/setcommands` — aşağıdakını eyni formatda, sətir-sətir göndər:

```
start - Başla
acar - Açar sözlə axtar
hekaye - Hekayəyə uyğun atalar sözü
tesaduf - Təsadüfi atalar sözü
komek - Kömək
legv - Axtarışı dayandır
```

`/setuserpic` — istəsən şəkil yüklə.

Tokeni unutsan: BotFather-də `/token` və ya `/mybots`.

Token sızarsa: `/revoke` — köhnəsi ölür, yenisi yaranır. Sonra `.env`-i yenilə.

---

## 3. Layihə qovluğunu yerləşdir

Bu paket `atalar-sozu-bot` adlanır. Onu kompüterində istədiyin yerə qoy, məsələn:

```
sənədlər/atalar-sozu-bot/
  bot.py
  proverbs.json
  requirements.txt
  .env.example
  tools/add_proverb.py
```

Terminalda o qovluğa keç:

```bash
cd yol/atalar-sozu-bot
```

---

## 4. Python mühiti (virtual env)

Sistem Python-unu zibilləməmək üçün ayrıca mühit açırıq.

```bash
python3 -m venv .venv
```

Aktivləşdir:

- Linux / macOS:

```bash
source .venv/bin/activate
```

- Windows (cmd):

```bat
.venv\Scripts\activate
```

- Windows (PowerShell):

```powershell
.venv\Scripts\Activate.ps1
```

Prompt-un əvvəlində `(.venv)` görünməlidir.

Kitabxanaları quraşdır:

```bash
pip install -r requirements.txt
```

Bu iki paket gəlir:

- `python-telegram-bot` — Telegram API
- `python-dotenv` — `.env` faylından token oxumaq

---

## 5. Tokeni koddan kənarda saxla

```bash
cp .env.example .env
```

Windows-da Explorer-də `.env.example`-i kopyalayıb adını `.env` qoy.

`.env` faylını aç və belə et:

```
BOT_TOKEN=7123456789:AAH_senin_real_tokenin
```

Boşluq qoyma. Dırnaq qoyma.

`.gitignore`-da `.env` var. Git-ə düşməsin.

---

## 6. İlk dəfə işə sal

Mühit aktivdirsə:

```bash
python bot.py
```

Görməlisən:

```
Bot başladı. Atalar sözü sayı: 35
```

Telegram-da öz botunu aç (`t.me/senin_botun`), `/start` yaz.

Gözlənilən menyu:

- 🔑 Açar söz
- 📖 Hekayə
- 🎲 Təsadüfi
- ℹ️ Kömək

Yoxlama:

1. **Açar söz** → `dost` yaz. «Dost dar gündə tanınar» gəlməlidir.
2. **Hekayə** → `İşimi sabaha qoydum, sonra tələsdim` yaz. «Axşamın işini sabaha qoyma» gəlməlidir.
3. **Təsadüfi** — hər basışda başqa söz.

Dayandırmaq: terminalda `Ctrl+C`.

---

## 7. Kod necə işləyir (qısa)

`bot.py` üç hissədir.

### 7.1. Baza

Açılışda `proverbs.json` yaddaşa yüklənir. Hər atalar sözünün sahələri:

| sahə   | nədir                                      |
|--------|---------------------------------------------|
| `id`   | unikal nömrə                               |
| `text` | atalar sözünün özü                         |
| `mena` | qısa izah                                  |
| `acar` | axtarış üçün açar sözlər                   |
| `movzu`| mövzu etiketləri (zəhmət, dostluq...)      |

### 7.2. Axtarış

`normalize()` hərfləri sadələşdirir: `ə→e`, `ş→s` və s. Ona görə «söz» və «soz» yaxın düşür.

Xal belə yığılır:

- bütün sorğu mətndə varsa +8
- eyni sözlər kəsişirsə hər sözə +3
- qismən oxşarlıq +1

Ən yüksək xallılar qaytarılır.

Hekayə axtarışı eyni funksiyadır: fərq odur ki, istifadəçi bütöv cümlə yazır.

### 7.3. Söhbət vəziyyəti

`ConversationHandler` iki vəziyyət saxlayır:

- `ACAR` — növbəti mesaj açar söz sayılır
- `HEKAYE` — növbəti mesaj hekayə sayılır

`/legv` və ya `/start` vəziyyəti sıfırlayır.

---

## 8. Bazanı necə böyütmək

35 söz dərs üçündür, kifayət deyil. Məqsəd: 200–500.

### 8.1. Əl ilə JSON

`proverbs.json` aç. `proverbs` siyahısının sonuna əlavə et:

```json
{
  "id": 36,
  "text": "İşin özünə bax, sahibinə yox.",
  "mena": "İşi keyfiyyətinə görə qiymətləndir.",
  "acar": ["iş", "keyfiyyət", "sahib"],
  "movzu": ["iş", "ədalət"]
}
```

Qaydalar:

- `id` təkrarsız olsun
- vergül: son elementdən əvvəlki obyektin sonunda vergül var, sonuncuda yox
- JSON-u yoxla: https://jsonlint.com və ya

```bash
python -m json.tool proverbs.json > /dev/null
```

Xəta yoxdursa heç nə çap olunmur.

`meta.say` sahəsini də yenilə, ya da `tools/add_proverb.py` işlət — o özü sayır.

### 8.2. Hazır skript

```bash
python tools/add_proverb.py \
  "İşin özünə bax, sahibinə yox." \
  "İşi keyfiyyətinə görə qiymətləndir." \
  "iş,keyfiyyət,sahib" \
  "iş,ədalət"
```

Bot açıqdırsa, yeni sözün görünməsi üçün `Ctrl+C` və yenidən `python bot.py`.

### 8.3. Haradan söz yığmaq

Etibarlı mənbələr:

- Azərbaycan Vikisitat: «Azərbaycan atalar sözləri»
- çap kitabları: «Atalar sözü», Bakı
- müəllim / filoloq yoxlaması

Hər sözə **özün** `mena`, `acar`, `movzu` yaz. Kopyala-yapışdır kifayət deyil — axtarış bu sahələrdən asılıdır.

Yaxşı `acar` nümunəsi:

- mətn: «Dost dar gündə tanınar»
- acar: `dost, çətinlik, sınaq, etibar, dar gün`
- pis acar: yalnız `dost`

### 8.4. Keyfiyyət qaydası

Hər yeni sətir üçün 4 sual:

1. Bu doğrudan atalar sözüdür, yoxsa sadəcə aforizm?
2. Məna 1 cümlədirmi?
3. Açar sözlər real axtarışları əhatə edirmi?
4. Təkrar `text` yoxdurmu?

Təkrar yoxlama:

```bash
python -c "
import json
from collections import Counter
p=json.load(open('proverbs.json',encoding='utf-8'))['proverbs']
c=Counter(x['text'] for x in p)
print('say',len(p))
print('tekrar',[k for k,v in c.items() if v>1])
"
```

### 8.5. Sonrakı mərhələ: axtarışı gücləndirmək

200+ söz olanda sadə kəsişmə zəif qala bilər. Onda növbə:

1. eyni JSON qalır
2. `movzu` üzrə filtr düyməsi əlavə et
3. istəsən sonradan kiçik semantik model (məs. cümlə vektoru) qoy — amma **əvvəl bazanı doldur**

---

## 9. Tez-tez çıxan xətalar

| əlamət | səbəb | həll |
|--------|--------|------|
| `BOT_TOKEN tapılmadı` | `.env` yoxdur və ya ad səhvdir | `.env` eyni qovluqda olsun |
| bot cavab vermir | `bot.py` işləmir | terminalı açıq saxla |
| `Conflict: terminated by other getUpdates` | eyni token iki yerdə işləyir | o biri prosesi öldür |
| JSON xətası, bot açılmır | `proverbs.json` pozulub | `python -m json.tool proverbs.json` |
| menyu görünmür | BotFather əmrləri qoyulmayıb | `/setcommands` |
| «Unauthorized» | token səhv / revoke olunub | `/token` götür, `.env`-i yenilə |

Eyni tokeni iki kompüterdə eyni anda işə salma.

---

## 10. Botu 24 saat işlək saxlamaq (sonra)

İndi polling kifayətdir: sənin kompüterində `python bot.py`.

Gündəlik istifadə üçün sonra:

1. ucuz VPS (Ubuntu)
2. qovluğu yüklə
3. eyni `venv` + `.env`
4. `systemd` xidməti və ya `tmux` içində `python bot.py`

Webhook (nginx + HTTPS) sonra gəlir. İlk ay polling ilə get.

Heç vaxt tokeni GitHub public repo-ya qoyma.

---

## 11. Təklif olunan həftə planı

**Gün 1.** BotFather + venv + `.env` + `python bot.py` + `/start` işləyir.

**Gün 2.** Kodu oxu. Bir düymənin mətnini dəyiş, botu yenidən aç, fərqi gör.

**Gün 3–4.** `proverbs.json`-u 35-dən 80-ə çıxar. Hər sözə məna + 4–8 açar söz.

**Gün 5.** 10 tanışa ver. Hansı sorğular boş cavab gətirdi, onları yaz.

**Həftə 2.** Bazanı 150+ et. Boş cavab verən sorğular üçün yeni `acar` əlavə et.

**Həftə 3.** İstəsən əlavə funksiya: mövzu siyahısı, günün atalar sözü (`JobQueue`).

Əlavə funksiyanı baza 100-ü keçmədən yazma. Maarifləndirmə botunda dəyər sözlərin keyfiyyətindədir.

---

## 12. Növbəti kiçik təkmilləşdirmələr (istəyə bağlı)

Bunları indi yazmağa ehtiyac yoxdur. Sıra belədir:

1. `/movzu` — mövzuya görə siyahı
2. səhifələmə: 5-dən çox nəticə olsa «növbəti» düyməsi
3. istifadəçi boş nəticə alanda «bu sözü bazaya əlavə edək?» qeydi (yalnız sənə, admin id ilə)
4. günün sözü — səhər bir atalar sözü

Admin id almaq: `@userinfobot`-a yaz, rəqəmi götür, `bot.py`-də yalnız o id-yə `/elave` əmri aç.

---

## 13. Təhlükəsizlik, 3 qayda

1. Token sirdir.
2. Bot yalnız ictimai atalar sözü və izah göndərir — şəxsi məlumat saxlamır.
3. Qrupa salacaqsanса BotFather-də `/setprivacy` və `/setjoingroups`-u başa düş, sonra sal.

---

Hazırsansa sıra belədir: BotFather → `.env` → `pip install` → `python bot.py` → `dost` yaz → işləyirsə bazanı böyüt.
