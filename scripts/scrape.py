#!/usr/bin/env python3
"""Scrape CROUS Paris restaurants/cafeterias from the official open API
and write data/paris.json for the static map. Stdlib only."""
import json, re, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = ("https://mesr.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
	   "fr_crous_restauration_france_entiere/records")
WHERE = 'zone like "Paris*"'		  # Paris arrondissements. Use '' for all France (~750)
OUT = Path(__file__).resolve().parents[1] / "data" / "paris.json"

DAYS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
		"vendredi": 4, "samedi": 5, "dimanche": 6}
DA = "|".join(DAYS)
RANGE_RE   = re.compile(rf"\b(?:du\s+|des\s+)?(?P<a>{DA})s?\s+au(?:x)?\s+(?P<b>{DA})s?\b", re.I)
SINGLE_RE  = re.compile(rf"\b(?:le\s+|les\s+)?(?P<d>{DA})s?\b", re.I)		  # "les samedis" too
ALLDAYS_RE = re.compile(r"\b(?:tous\s+les\s+jours|chaque\s+jour|7\s*j/7|7\s+jours\s+sur\s+7)\b", re.I)
TIME_RE = re.compile(r"\b(\d{1,2})\s*(?:[hH:](\d{2})|h)?\s*(?:à|-|–|—)\s*(\d{1,2})\s*(?:[hH:](\d{2})|h)?\b")
SEP_RE  = re.compile(r"\s*(?:,\s*)?(?:et|&)\s*")								# "Samedi et dimanche"

def fetch_records():
	recs, offset = [], 0
	while True:
		q = urllib.parse.urlencode({"where": WHERE, "limit": 100, "offset": offset})
		req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "resto-u-map/1.0"})
		with urllib.request.urlopen(req, timeout=60) as r:
			payload = json.load(r)
		batch = payload.get("results", [])
		recs.extend(batch)
		total = payload.get("total_count", 0)
		offset += len(batch)
		if not batch or offset >= total:
			if not recs:
				raise SystemExit(f"ERROR: 0 records for where={WHERE!r} — dataset renamed?")
			return recs

def hours_section(infos: str) -> str:
	if not infos:
		return ""
	m = re.search(r"Horaires?\s*(.*?)(?=Moyen\s+d'acc[eè]s|\bPratique\b|\bPaiements\b|\bContact\b|\bTarifs\b|$)",
				  infos, re.I | re.S)
	txt = m.group(1) if m else infos
	txt = re.sub(r"Attention[,.][^.\n]*évoluer\.?", "", txt, flags=re.I)
	return re.sub(r"\s+", " ", txt).strip()

def day_clauses(text):
	"""Split hours text into (weekdays, text-chunk) clauses."""
	spans = []
	for m in ALLDAYS_RE.finditer(text):
		spans.append((m.start(), m.end(), list(range(7))))
	for m in RANGE_RE.finditer(text):
		a, b = DAYS[m.group("a").lower()], DAYS[m.group("b").lower()]
		days, d = [], a
		while True:
			days.append(d)
			if d == b:
				break
			d = (d + 1) % 7
		spans.append((m.start(), m.end(), days))
	taken = [(s, e) for s, e, _ in spans]
	for m in SINGLE_RE.finditer(text):
		if any(s <= m.start() < e for s, e in taken):
			continue
		spans.append((m.start(), m.end(), [DAYS[m.group("d").lower()]]))
	spans.sort(key=lambda t: t[0])
	# merge day tokens joined by "et" / "&" / "," (e.g. "Samedi et dimanche")
	merged = []
	for s, e, days in spans:
		if merged and (SEP_RE.fullmatch(text[merged[-1][1]:s]) or text[merged[-1][1]:s].strip() == ","):
			ps, _, pdays = merged[-1]
			merged[-1] = (ps, e, pdays + days)
		else:
			merged.append((s, e, days))
	return [(days, text[e:(merged[i + 1][0] if i + 1 < len(merged) else len(text))])
			for i, (s, e, days) in enumerate(merged)]

def _merge(iv):
	out = []
	for o, c in iv:
		if out and o <= out[-1][1]:
			out[-1][1] = max(out[-1][1], c)
		else:
			out.append([o, c])
	return out

def parse_schedule(text):
	schedule = {d: [] for d in range(7)}
	found, had_days = False, False

	def add(chunk, days):
		nonlocal found
		for h1, m1, h2, m2 in TIME_RE.findall(chunk):
			o = int(h1) * 60 + int(m1 or 0)
			c = int(h2) * 60 + int(m2 or 0)
			if 0 <= o < 1440 and 0 < c <= 1440 and c > o:
				found = True
				for d in days:
					schedule[d].append([o, c])

	clauses = day_clauses(text)
	if clauses:
		had_days = True
		for days, chunk in clauses:
			add(chunk, days)
	else: # times but no day names -> assume Mon-Fri
		add(text, list(range(5)))
	for d in schedule:
		schedule[d] = _merge(sorted(schedule[d]))
	conf = "parsed" if (had_days and found) else ("defaulted_days" if found else "unparsed")
	return {str(d): v for d, v in schedule.items() if v}, conf

ACCESS_RE = re.compile(r"(?:accessible|ouvert[e]?s?|r[ée]serv[ée]e?s?)\s+(?:[àa]\s+|au(?:x)?\s+)([^.\n]{3,150})", re.I)
ACCESS_SKIP_RE = re.compile(r"mobilit[ée]\s+r[ée]duite|handicap|pmr", re.I) # wheelchair access != student access
SPECIFIC_UNI_RE = re.compile(
	r"universit|campus|[ée]cole|institut|ensa|\bens\b|sorbonne|dauphine|assas|sciences\s*po|inalco|psl|condorcet", re.I)

def parse_access(infos, place_type="", place_name=""):
	"""all students vs restricted (one uni/campus) vs staff only."""
	phrases = []
	for m in ACCESS_RE.finditer(infos or ""):
		ph = m.group(1).strip()
		if ph and not ACCESS_SKIP_RE.search(ph):
			phrases.append(ph)
	# prefer phrases that actually talk about students/staff
	phrases.sort(key=lambda p: (bool(re.search(r"[ée]tudiant|personnel", p, re.I)), len(p)), reverse=True)
	phrase = phrases[0] if phrases else ""
	if not phrase:
		if re.search(r"administratif", f"{place_type} {place_name}", re.I):
			return {"level": "staff", "note": "Restaurant administratif (staff restaurant)"}
		return {"level": "unknown", "note": ""}
	pl = phrase.lower()
	has_students	  = bool(re.search(r"[ée]tudiant", pl))
	has_all_higher_ed = bool(re.search(r"tout[e]?s?\s+[ée]tudiant|enseignement\s+sup[ée]rieur", pl))
	has_specific_uni  = bool(SPECIFIC_UNI_RE.search(pl))
	has_only_staff	= bool(re.search(r"personnel", pl)) and not has_students
	if has_only_staff:
		return {"level": "staff", "note": phrase}
	if has_students and has_all_higher_ed and not has_specific_uni:
		return {"level": "all", "note": phrase}
	if has_students and has_specific_uni:
		return {"level": "restricted", "note": phrase}
	if has_students:
		return {"level": "restricted", "note": phrase + " (implied campus restriction)"}
	return {"level": "restricted", "note": phrase}

CLOSURE_OK_RE  = re.compile(r"\bferm[ée]e?\b|\bfermeture\b|travaux|r[ée]novation", re.I)
CLOSURE_SKIP_RE = re.compile(
	rf"ferm[ée]e?\s+(?:le\s+|les\s+)?(?:{DA}|jours?\s+f[ée]ri[ée]s)", re.I)

def closure_notice(*texts):
	"""Find a sentence announcing a closure/renovation in description or infos."""
	for t in texts:
		if not t:
			continue
		for sent in re.split(r"(?<=[.!?])\s+", t):
			if CLOSURE_OK_RE.search(sent) and not CLOSURE_SKIP_RE.search(sent):
				return re.sub(r"\s+", " ", sent).strip()
	return None

def clean_address(rec):
	c = rec.get("contact") or ""
	c = re.sub(r"(T[eé]l[eé]phone|T[eé]l\.?|E-?mail).*$", "", c, flags=re.I | re.S)
	name = rec.get("title") or ""
	if c.lower().startswith(name.lower()):
		c = c[len(name):]
	addr = re.sub(r"\s+", " ", c).strip(" ,")
	if len(addr) < 8:   # corrupted source data ("RU Châ", ...)
		addr = f"{rec.get('zone') or 'Paris'} — adresse non renseignée"
	return addr

def main():
	places, stale = [], []
	for r in fetch_records():
		geo = r.get("geolocalisation") or {}
		lat, lon = geo.get("lat") or r.get("lat"), geo.get("lon")
		if lat is None or lon is None:
			continue
		infos = r.get("infos") or ""
		desc  = r.get("short_desc") or ""
		hrs = hours_section(infos)
		sched, conf = parse_schedule(hrs)

		notice = closure_notice(desc, infos)
		flag = bool(r.get("closing"))
		if flag and notice:
			closure_status = "confirmed"	  # real closure (works, renovation, ...)
		elif notice:
			closure_status = "notice_only"	# text says closed but API flag not set -> info only
		else:
			if flag:
				stale.append(r.get("title"))  # flag with no textual evidence -> treat as stale
			closure_status = None

		places.append({
			"id": r.get("id"), "name": r.get("title"), "type": r.get("type"),
			"zone": r.get("zone"), "address": clean_address(r),
			"lat": lat, "lon": lon,
			"description": desc or None,
			"hours_raw": hrs,
			"schedule": sched, "schedule_confidence": conf,
			"access": parse_access(infos, r.get("type") or "", r.get("title") or ""),
			"closure_status": closure_status,
			"closure_notice": notice,
			"closing_flag_raw": flag,
			"photo": r.get("photo"),
		})
	OUT.parent.mkdir(parents=True, exist_ok=True)
	OUT.write_text(json.dumps({
		"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
		"source": API, "license": "Licence Ouverte / Etalab",
		"count": len(places), "places": places,
	}, ensure_ascii=False, indent=1), encoding="utf-8")
	unp = sum(1 for p in places if p["schedule_confidence"] == "unparsed")
	confirmed = sum(1 for p in places if p["closure_status"] == "confirmed")
	print(f"wrote {OUT}: {len(places)} places ({len(places) - unp} schedules parsed, {unp} unparsed)")
	print(f"closures: {confirmed} confirmed, {len(stale)} stale flags ignored: {stale}")

if __name__ == "__main__":
	main()