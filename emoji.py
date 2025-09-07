# emoji.py
import re,random
LEX=[(r"\b(идея|инсайт|концепт)\b",["💡","✨"]),(r"\b(контент|пост(ы)?|карточк)\b",["🧩","📝"]),(r"\b(текст|заголовок|описани)\b",["✍️"]),(r"\b(дизайн|визуал|баннер)\b",["🎨","🖼️"]),(r"\b(фото|изображени)\b",["📸"]),(r"\b(видео|ролик)\b",["🎬"]),(r"\b(план|недел|календар)\b",["🗓️"]),(r"\b(дедлайн|срок|сегодня|завтра)\b",["⏰"]),(r"\b(публикаци|постинг|опубликуем|выложим)\b",["🚀","📣"]),(r"\b(провер|верифиц|модерац|готово)\b",["✅","🔎"]),(r"\b(ошибк|проблем|таймаут|сбой)\b",["⚠️","🛑"]),(r"\b(ИИ|AI|нейросет|автоматизац|бот)\b",["🤖","⚙️"]),(r"\b(аналитик|метрик|отчёт|статистик)\b",["📊","📈"]),(r"\b(клиент|проект|подписк|платёж)\b",["💼"]),(r"\b(канал|чаты?|телеграм)\b",["📢"])]
HEAD=["📣","🛠️","🚀","🎯"]
CTA=["👉","✅","🚀","🔔","📌"]
URL=re.compile(r"(https?://\S+)")
HANDLE=re.compile(r"(@[A-Za-z0-9_]+)")
HASH=re.compile(r"(#[\wА-Яа-я_]+)")
CODEB=re.compile(r"```.*?```",re.S)
CODEI=re.compile(r"`[^`]+`")
QUOTE=re.compile(r"^\s*>\s*",re.M)
def _protect(t):
    r={}
    i=[("CODEB",CODEB),("CODEI",CODEI),("URL",URL),("TAG",HANDLE),("HASH",HASH)]
    for p,n in i:
        idx=0
        def sub(m):
            nonlocal idx
            k=f"__{p}{idx}__";r[k]=m.group(0);idx+=1;return k
        t=n.sub(sub,t)
    return t,r
def _restore(t,r):
    for k,v in r.items(): t=t.replace(k,v)
    return t
def stylize(text,style="balanced",seed=None):
    if seed is not None: random.seed(seed)
    s,stash=_protect(text)
    lim={"minimal":2,"balanced":6,"rich":10}.get(style,6);cnt=0;used=set()
    def ch(arr):
        random.shuffle(arr)
        for a in arr:
            if a not in used: return a
        return arr[0] if arr else ""
    def is_header(ln):
        if ln.strip().startswith("#"): return True
        if len(ln)<=80 and re.search(r"^[A-ZА-Я0-9\s\-–!?:]+$",ln.strip()): return True
        return False
    out=[]
    for i,ln in enumerate(s.splitlines()):
        if cnt>=lim or not ln.strip() or QUOTE.search(ln): out.append(ln);continue
        if is_header(ln) or i==0:
            e=ch(HEAD)
            if e and not ln.strip().startswith(e):
                ln=f"{e} {ln}";used.add(e);cnt+=1
        if cnt<lim and re.match(r"^\s*[-*•]\s+",ln):
            added=False
            for pat,choices in LEX:
                if re.search(pat,ln,flags=re.I):
                    e=ch(choices);ln=re.sub(r"^(\s*[-*•]\s+)",r"\1"+e+" ",ln);used.add(e);cnt+=1;added=True;break
            if not added and style!="minimal": ln=re.sub(r"^(\s*[-*•]\s+)",r"\1• ",ln)
            out.append(ln);continue
        if cnt<lim and style!="minimal":
            for pat,choices in LEX:
                if re.search(pat,ln,flags=re.I):
                    e=ch(choices);ln=re.sub(r"^(\s*)(\S+)",r"\1"+e+r" \2",ln,1);used.add(e);cnt+=1;break
        if cnt<lim and re.search(r"\b(нажми(те)?|выбери(те)?|одобри(ть|те)|запусти(ть|те)|подтверди(ть|те)|перегенерируй)\b",ln,flags=re.I):
            e=ch(CTA);ln=ln.rstrip()+" "+e;used.add(e);cnt+=1
        out.append(ln)
    res=_restore("\n".join(out),stash)
    res=re.sub(r"(([^\w\s]|[\U0001F300-\U0001FAFF]))\s*\1\s*\1",r"\1\1",res)
    return res