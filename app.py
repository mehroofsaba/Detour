import os, json, sqlite3, random, urllib.request
from flask import Flask, request, jsonify, g

app = Flask(__name__, static_folder='static', static_url_path='')
DB = os.environ.get('DETOUR_DB', 'detour.db')
OLLAMA = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
MODEL = os.environ.get('DETOUR_MODEL', 'gemma3')
STATS = ['exploration', 'curiosity', 'observation', 'courage', 'chaos']
TITLES = ['Indoor Creature', 'Sidewalk Explorer', 'Park Gremlin', 'Neighborhood Witch', 'Horizon Chaser', 'Local Legend']
ACH = {'first_detour': 'First DETOUR', 'first_note': 'First Field Note', 'first_museum': 'First museum item',
       'rainy': 'First rainy adventure', 'night': 'First night adventure', 'weekly': 'Three DETOURs in a week',
       'nearby': 'Noticed something near home'}

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close(_):
    d = g.pop('db', None)
    if d: d.close()

def init():
    c = sqlite3.connect(DB)
    c.executescript('''create table if not exists quests(id integer primary key autoincrement,title text,data text,status text default 'active',created text default current_timestamp);
create table if not exists notes(id integer primary key autoincrement,quest_id int,title text,body text,reflection text,photo text,category text,weather text,place text,xp int,created text default current_timestamp);
create table if not exists stats(k text primary key,v int default 0);
create table if not exists ach(k text primary key,created text default current_timestamp);
create table if not exists kv(k text primary key,v text);''')
    for col in ('lat real', 'lon real'):
        try: c.execute('alter table notes add column ' + col)
        except Exception: pass
    for k in STATS: c.execute('insert or ignore into stats(k) values(?)', (k,))
    c.commit(); c.close()

def llm(prompt, images=None):
    try:
        m = {'model': MODEL, 'prompt': prompt, 'stream': False, 'format': 'json'}
        if images: m['images'] = images
        body = json.dumps(m).encode()
        r = urllib.request.Request(OLLAMA + '/api/generate', body, {'Content-Type': 'application/json'})
        return json.loads(urllib.request.urlopen(r, timeout=60).read())['response']
    except Exception:
        return None

# (title, difficulty, steps, clue, rewards, tags)
POOL = [
 ("The Yellow Thing", "gentle", ["Leave your current location.", "Find something yellow.", "Walk another 200 steps.", "Stop and observe."], "Look up, look down. It might be small.", {"exploration": 8, "curiosity": 8}, "any"),
 ("The Thing That Isn't Supposed To Be There", "gentle", ["Leave wherever you are.", "Walk until something looks completely out of place.", "Don't photograph it. Look at it for ten seconds.", "Walk another 200 steps. Something else is waiting."], "Look for what doesn't belong.", {"curiosity": 12, "observation": 6}, "any"),
 ("Take The Wrong Turn", "bold", ["Walk to the next junction.", "Turn the way you never turn.", "Do it twice more.", "Find a place you've never noticed."], "If it feels familiar, turn again.", {"exploration": 14, "courage": 6}, "dry"),
 ("The Quiet Street", "gentle", ["Find a sheltered spot, a doorway or a porch.", "Stay for three minutes.", "Count five different sounds.", "Notice one thing that is moving."], "Listen for the quietest sound.", {"observation": 14, "curiosity": 4}, "rain"),
 ("Find Something Older Than You", "gentle", ["Head toward the oldest looking thing nearby.", "Touch its surface if you can.", "Guess its age. Don't look it up yet.", "Describe three things you notice."], "Walls, trees and signs count.", {"observation": 10, "curiosity": 10}, "any"),
 ("Grey Looks Good On You", "gentle", ["Go outside.", "Find something that looks better in grey.", "Stand with it for a minute.", "Find a second one."], "Wet stone, old paint, sky.", {"observation": 10, "exploration": 6}, "cloud"),
 ("Follow The Light", "bold", ["Find where the last light is falling.", "Walk toward it.", "Stop when it leaves the ground.", "Notice what it touched last."], "Look for long shadows.", {"exploration": 12, "observation": 8}, "night"),
 ("Say Hello To A Stranger", "bold", ["Walk somewhere with people.", "Say hello to someone.", "Ask them their favourite thing nearby.", "Remember the answer."], "A smile counts as hello.", {"courage": 16, "exploration": 4}, "dry"),
 ("The Silly Walk Tax", "chaotic", ["Pick a lamp post as your goal.", "Walk there like nobody is watching.", "Pay the toll: touch the post and bow.", "Choose a new goal and repeat."], "Commit to the bit.", {"chaos": 16, "courage": 6}, "dry"),
 ("Everyone Picks A Direction", "social", ["Everyone chooses a direction. Nobody explains why.", "Walk 100 steps together.", "Find the weirdest object within 500 metres.", "Vote on the winner."], "Disagree out loud.", {"courage": 8, "chaos": 8, "curiosity": 6}, "group"),
 ("Same Colour Stranger", "social", ["Pick one colour among you.", "Find a stranger wearing it.", "Wave without speaking.", "Report back who spotted them first."], "Hats and shoes count.", {"courage": 12, "chaos": 6}, "group"),
]

def fallback(mood, mins, group, kind, is_day):
    tags = {'any'} | ({'group'} if group else set())
    tags |= {'rain'} if kind in ('rain', 'storm', 'snow') else {'dry'}
    if kind == 'cloud': tags.add('cloud')
    if not is_day: tags.add('night')
    pool = [p for p in POOL if p[5] in tags and (group or p[5] != 'group')]
    if group: pool = [p for p in pool if p[5] == 'group'] or pool
    if mood in ('chaotic', 'restless'): pool = [p for p in pool if p[1] != 'gentle'] or pool
    if mood in ('tired', 'quiet'): pool = [p for p in pool if p[1] == 'gentle'] or pool
    t, d, s, c, r, _ = random.choice(pool)
    return {'title': t, 'duration': mins, 'difficulty': d, 'steps': s, 'clue': c, 'rewards': r,
            'hold_answer': random.random() < .35, 'source': 'fallback'}

def valid(q):
    try:
        steps = [str(x) for x in q['steps']][:7]
        rw = {k: max(1, min(20, int(v))) for k, v in q['rewards'].items() if k in STATS}
        if not steps or not rw: return None
        return {'title': str(q['title'])[:60], 'duration': 0, 'difficulty': str(q.get('difficulty', 'gentle')),
                'steps': steps, 'clue': str(q.get('clue', '')), 'rewards': rw,
                'hold_answer': bool(q.get('hold_answer')), 'source': 'ai'}
    except Exception:
        return None

@app.post('/api/generate')
def generate():
    j = request.json or {}
    mins = int(j.get('minutes', 30)); mood = j.get('mood', 'curious'); group = bool(j.get('group'))
    wx = j.get('weather') or {}; kind = wx.get('kind', 'unknown'); is_day = wx.get('is_day', 1)
    ctx = f"time {mins} min, mood {mood}, {'with friends' if group else 'alone'}, weather {kind} {wx.get('temp', '?')}C, {'day' if is_day else 'night'}, place type {j.get('place', 'unknown')}"
    prompt = ("You design tiny real-world adventures that make people put their phone away. Context: " + ctx +
              ". Return ONLY JSON: {\"title\":str,\"difficulty\":\"gentle|bold|chaotic\",\"steps\":[3-5 short imperative strings],\"clue\":str,"
              "\"rewards\":{keys from exploration,curiosity,observation,courage,chaos with ints 4-16},\"hold_answer\":bool}. "
              "Be specific, strange and safe. No shopping, no driving, no trespassing. Weather matters: rain means sheltered missions.")
    raw = llm(prompt); q = None
    if raw:
        try: q = valid(json.loads(raw))
        except Exception: q = None
    q = q or fallback(mood, mins, group, kind, is_day)
    q['duration'] = mins
    q['context'] = {'weather': wx, 'mood': mood, 'group': group}
    c = db().execute('insert into quests(title,data) values(?,?)', (q['title'], json.dumps(q)))
    db().commit(); q['id'] = c.lastrowid
    return jsonify(q)

def reflect(body, title, wx):
    raw = llm(f"Rewrite this field note as a 2 sentence journal entry. Only enhance, never invent facts. Note: '{body}'. Quest: {title}. Weather: {wx}. Return JSON {{\"reflection\":str}}")
    try: return json.loads(raw)['reflection'][:400]
    except Exception: pass
    return random.choice(["You looked closer than most people do today. That matters.",
                          "Almost walked past it. Glad you didn't.",
                          "Small things are still real things. This one is yours now."])

def state():
    d = db()
    st = {r['k']: r['v'] for r in d.execute('select * from stats')}
    xp = sum(st.values()); lvl = xp // 100 + 1
    ach = [r['k'] for r in d.execute('select k from ach')]
    hist = [dict(r) for r in d.execute("select id,title,status,created from quests order by id desc limit 50")]
    nm = d.execute("select v from kv where k='name'").fetchone()
    return {'name': nm['v'] if nm else '', 'stats': st, 'xp': xp, 'level': lvl, 'into': xp % 100, 'title': TITLES[min(lvl - 1, len(TITLES) - 1)],
            'achievements': [{'k': k, 'label': v, 'got': k in ach} for k, v in ACH.items()], 'history': hist}

@app.get('/api/state')
def get_state(): return jsonify(state())

@app.post('/api/complete/<int:qid>')
def complete(qid):
    d = db(); j = request.json or {}
    row = d.execute('select data from quests where id=?', (qid,)).fetchone()
    if not row: return jsonify(error='no such quest'), 404
    q = json.loads(row['data']); wx = j.get('weather') or {}
    body = (j.get('body') or '').strip()[:1000]; title = (j.get('title') or q['title'])[:80]
    refl = reflect(body, q['title'], wx.get('label', '')) if body and j.get('polish', True) else ''
    xp = 0
    for k, v in q['rewards'].items():
        d.execute('update stats set v=v+? where k=?', (v, k)); xp += v
    bonus = 5 if (body or j.get('photo')) else 0
    if bonus: d.execute("update stats set v=v+? where k='observation'", (bonus,)); xp += bonus
    d.execute("update quests set status='done' where id=?", (qid,))
    d.execute('insert into notes(quest_id,title,body,reflection,photo,category,weather,place,xp,lat,lon) values(?,?,?,?,?,?,?,?,?,?,?)',
              (qid, title, body, refl, j.get('photo', ''), j.get('category', 'Object'), wx.get('label', ''), j.get('place', ''), xp, j.get('lat'), j.get('lon')))
    got = ['first_detour']
    if body: got.append('first_note')
    if j.get('photo') or body: got.append('first_museum')
    if wx.get('kind') in ('rain', 'storm'): got.append('rainy')
    if wx.get('is_day', 1) == 0: got.append('night')
    if d.execute("select count(*) from quests where status='done' and created>=datetime('now','-7 day')").fetchone()[0] >= 3: got.append('weekly')
    if near(j.get('lat'), j.get('lon')): got.append('nearby')
    for k in got: d.execute('insert or ignore into ach(k) values(?)', (k,))
    d.commit()
    return jsonify(xp=xp, reflection=refl, state=state())

@app.get('/api/notes')
def notes():
    cat = request.args.get('category')
    sql = 'select * from notes' + (' where category=?' if cat else '') + ' order by id desc'
    return jsonify([dict(r) for r in db().execute(sql, (cat,) if cat else ())])

@app.delete('/api/notes/<int:nid>')
def del_note(nid):
    db().execute('delete from notes where id=?', (nid,)); db().commit(); return jsonify(ok=True)

import math
def km(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))

def near(lat, lon):
    r = db().execute("select v from kv where k='home'").fetchone()
    try:
        h = json.loads(r['v']); return km(float(lat), float(lon), h[0], h[1]) <= 1.0
    except Exception: return False

@app.post('/api/name')
def set_name():
    db().execute("insert or replace into kv values('name',?)", (((request.json or {}).get('name') or '')[:30],)); db().commit()
    return jsonify(ok=True)

@app.post('/api/home')
def set_home():
    j = request.json or {}
    db().execute("insert or replace into kv values('home',?)", (json.dumps([float(j['lat']), float(j['lon'])]),)); db().commit()
    return jsonify(ok=True)

@app.post('/api/bird')
def bird():
    j = request.json or {}; desc = (j.get('desc') or '')[:300]; img = (j.get('photo') or '').split(',')[-1]
    raw = llm("Look at the attached photo of a creature, plant or object found outdoors. Their note: '" + desc + "'. Do NOT name it. Give 3 clues about what to observe "
              "(size, shape, colour, movement, sound) and one question. Return JSON {\"clues\":[str],\"question\":str,\"reveal\":str}; "
              "reveal is the best identification from the image (common name plus one fact) ending with confidence low, medium or high; never claim certainty.", [img] if img else None)
    try:
        o = json.loads(raw); return jsonify(clues=[str(x) for x in o['clues']][:3], question=str(o['question']), reveal=str(o['reveal']), source='ai')
    except Exception:
        return jsonify(clues=["Note its size next to something you know.", "Where is it and what is it doing?", "Pick the one colour that stands out."],
                       question="What would you call it if you had to invent a name?",
                       reveal="No model is connected, so no guess is available. Try a field guide or iNaturalist.", source='fallback')

@app.post('/api/bird/save')
def bird_save():
    j = request.json or {}; d = db()
    d.execute("update stats set v=v+12 where k='observation'")
    d.execute('insert into notes(quest_id,title,body,photo,category,xp,lat,lon) values(0,?,?,?,?,12,?,?)',
              ((j.get('title') or 'Birdbrain find')[:80], (j.get('body') or '')[:1000], j.get('photo', ''), j.get('category', 'Animal'), j.get('lat'), j.get('lon')))
    d.execute("insert or ignore into ach(k) values('first_museum')"); d.commit()
    return jsonify(state=state())

@app.get('/')
def index(): return app.send_static_file('index.html')

os.makedirs(os.path.dirname(os.path.abspath(DB)), exist_ok=True)
init()
if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', '1') == '1', port=int(os.environ.get('PORT', 5000)))
