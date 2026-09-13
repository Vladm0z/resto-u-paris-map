/* Resto'U Paris - live open/closed map. Pan & zoom only, ASCII UI.
	 Venues sharing the same spot (coords rounded to ~1 m) are grouped into ONE
	 marker; the popup lists every venue at that spot with its own status. */
const CONFIG = {
	darkGreenMin: 120, greenMin: 60, opensSoonMin: 60,
	refreshSec: 60, center: [48.8566, 2.3522], zoom: 12,
	groupDecimals: 5,	 // ~1 m: venues closer than this merge into one marker
};
const COLORS = { dark_green:'#006400', green:'#00a650', yellow:'#ffd400',
								 red:'#e53935', blue:'#1e88e5', unknown:'#8d8d8d', confirmed:'#424242' };
const COLOR_KEY = Object.fromEntries(Object.entries(COLORS).map(([k, v]) => [v, k]));
const WD = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
const WD_SHORT = { Mon:0, Tue:1, Wed:2, Thu:3, Fri:4, Sat:5, Sun:6 };
const RANK = { open: 4, opens_soon: 3, closed: 2, confirmed: 1, unknown: 0 };

const map = L.map('map', {
	center: CONFIG.center, zoom: CONFIG.zoom, minZoom: 10, maxZoom: 19,
	dragging: true, scrollWheelZoom: true, doubleClickZoom: true,
	touchZoom: true, keyboard: true, boxZoom: true,
});
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
	maxZoom: 19,
	attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors | data: MESR open data (Licence Ouverte)',
}).addTo(map);

const fmtMin = m => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
const fmtDur = m => m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')}` : `${m} min`;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
	({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
const trunc = (s, n) => (s && s.length > n) ? s.slice(0, n - 1) + '...' : s;

function parisNow() {
	const parts = new Intl.DateTimeFormat('en-GB', {
		timeZone: 'Europe/Paris', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
	}).formatToParts(new Date());
	const g = t => parts.find(p => p.type === t).value;
	let h = parseInt(g('hour'), 10); if (h === 24) h = 0;
	return { day: WD_SHORT[g('weekday')], minute: h * 60 + parseInt(g('minute'), 10) };
}

function statusOf(p, now) {
	if (p.closure_status === 'confirmed')
		return { state: 'confirmed', label: 'Long-term closure (works/renovation) - see notice' };
	const sched = p.schedule || {};
	for (const [o, c] of (sched[String(now.day)] || [])) {
		if (now.minute >= o && now.minute < c) {
			const left = c - now.minute;
			return { state: 'open', left, label: `Open now - closes at ${fmtMin(c)} (in ${fmtDur(left)})` };
		}
	}
	for (let d = 0; d < 7; d++) {
		const day = (now.day + d) % 7;
		for (const [o] of (sched[String(day)] || []).slice().sort((a, b) => a[0] - b[0])) {
			if (d === 0 && o <= now.minute) continue;
			const delta = d * 1440 + o - now.minute;
			const when = d === 0 ? 'today' : d === 1 ? 'tomorrow' : WD[day];
			if (delta <= CONFIG.opensSoonMin)
				return { state: 'opens_soon', label: `Closed - opens ${when} at ${fmtMin(o)} (in ${fmtDur(delta)})` };
			return { state: 'closed', label: `Closed - opens ${when} at ${fmtMin(o)}` };
		}
	}
	return { state: 'unknown', label: 'Opening hours unknown - see details' };
}

function colorFor(s) {
	if (s.state === 'open') {
		if (s.left >= CONFIG.darkGreenMin) return COLORS.dark_green;
		if (s.left >= CONFIG.greenMin)		 return COLORS.green;
		return COLORS.yellow;
	}
	if (s.state === 'opens_soon') return COLORS.blue;
	if (s.state === 'closed')		 return COLORS.red;
	if (s.state === 'confirmed')	return COLORS.confirmed;
	return COLORS.unknown;
}

/* best status of a spot: open > opens_soon > closed > confirmed > unknown.
	 among several open venues, keep the one with the most time left. */
function groupStatus(statuses) {
	let best = statuses[0];
	for (const s of statuses) if (RANK[s.state] > RANK[best.state]) best = s;
	if (best.state === 'open')
		for (const s of statuses) if (s.state === 'open' && s.left > best.left) best = s;
	return best;
}

function accessBadge(a) {
	if (!a) return '';
	if (a.level === 'all')				return `<span class="badge ok">open to ALL students</span>`;
	if (a.level === 'staff')			return `<span class="badge staff">staff only${a.note ? ': ' + esc(trunc(a.note, 70)) : ''}</span>`;
	if (a.level === 'restricted') return `<span class="badge warn">restricted${a.note ? ': ' + esc(trunc(a.note, 70)) : ''}</span>`;
	return `<span class="badge muted">${a.note ? esc(trunc(a.note, 70)) : 'no access info (CROUS default: all students)'}</span>`;
}

function venueHtml(p, s) {
	let notices = '';
	if (p.closure_status === 'confirmed')
		notices += `<div class="warn">[!] ${esc(p.description || p.closure_notice || 'Closed for renovation - verify locally')}</div>`;
	else if (p.closure_status === 'notice_only' && p.closure_notice)
		notices += `<div class="notice">[i] ${esc(p.closure_notice)}</div>`;
	else if (p.description)
		notices += `<div class="desc">${esc(p.description)}</div>`;
	return `
		<h3>${esc(p.name)}</h3>
		<div class="badges"><span class="badge type">${esc(p.type || '?')}</span>${accessBadge(p.access)}</div>
		<div class="status" style="color:${colorFor(s)}">* ${esc(s.label)}</div>
		${notices}
		<div class="addr">${esc(p.address || '')}${p.zone ? ' - ' + esc(p.zone) : ''}</div>
		<div class="hours"><b>Hours (as published):</b> ${esc(p.hours_raw || 'n/a')}
			${p.schedule_confidence === 'unparsed' ? '<i> (could not parse - check raw text)</i>' : ''}</div>`;
}

function popupHtml(places, statuses) {
	let html = '<div class="pop">';
	places.forEach((p, i) => {
		if (i > 0) html += '<hr class="sep">';
		html += venueHtml(p, statuses[i]);
	});
	html += `<div class="src"><a href="https://www.etudiant.gouv.fr/fr/carte-pour-trouver-les-resto-u-235" target="_blank" rel="noopener">Official CROUS map</a></div></div>`;
	return html;
}

const title = L.control({ position: 'topright' });
title.onAdd = () => {
	const d = L.DomUtil.create('div', 'leaflet-control box title');
	d.innerHTML = `<b>Resto'U Paris</b><br><span id="clock"></span><br><span id="total" class="fine"></span>`;
	return d;
};
title.addTo(map);

const LEGEND = [
	['dark_green', 'Open - closes in 2 h+'],
	['green',			'Open - closes in 1-2 h'],
	['yellow',		 'Open - closes in < 1 h'],
	['blue',			 'Closed - opens within 1 h'],
	['red',				'Closed'],
	['confirmed',	'Long-term closure'],
	['unknown',		'Hours unknown'],
];
const legend = L.control({ position: 'bottomright' });
legend.onAdd = () => {
	const d = L.DomUtil.create('div', 'leaflet-control box legend');
	d.innerHTML = LEGEND.map(([k, l]) =>
		`<div><span class="dot" style="background:${COLORS[k]}"></span>${l} <span class="cnt" id="cnt-${k}"></span></div>`).join('');
	return d;
};
legend.addTo(map);

let items = [];
fetch('data/paris.json')
	.then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
	.then(data => {
		/* group venues that sit on the same spot (rounded to ~1 m) into ONE marker */
		const groups = new Map();
		for (const p of data.places) {
			const k = p.lat.toFixed(CONFIG.groupDecimals) + ',' + p.lon.toFixed(CONFIG.groupDecimals);
			if (!groups.has(k)) groups.set(k, { lat: 0, lon: 0, places: [] });
			const g = groups.get(k);
			g.places.push(p);
			g.lat += p.lat; g.lon += p.lon;
		}
		for (const g of groups.values()) { g.lat /= g.places.length; g.lon /= g.places.length; }

		for (const g of groups.values()) {
			const marker = L.circleMarker([g.lat, g.lon], {
				radius: g.places.length > 1 ? 11 : 9,	 // slightly bigger when several venues share the spot
				weight: 2, color: '#ffffff', opacity: .9,
				fillColor: COLORS.unknown, fillOpacity: .95,
			}).addTo(map);
			items.push({ places: g.places, marker });
		}
		const el = document.getElementById('total');
		if (el) el.textContent = `${data.places.length} venues - ${items.length} map spots`;
		tick();
		setInterval(tick, CONFIG.refreshSec * 1000);
	})
	.catch(e => alert('Could not load data/paris.json - run scripts/scrape.py first. (' + e + ')'));

function tick() {
	const now = parisNow();
	const counts = Object.fromEntries(Object.keys(COLORS).map(k => [k, 0]));
	for (const it of items) {
		const statuses = it.places.map(p => statusOf(p, now));
		const best = groupStatus(statuses);
		const col = colorFor(best);
		const names = it.places.map(p => p.name).join(' / ');
		it.marker.setStyle({ fillColor: col });
		it.marker.setTooltipContent(`${names} - ${best.label}`);
		it.marker.bindPopup(popupHtml(it.places, statuses), { 
		autoPan: true, 
		className: 'mobile-popup',
		maxWidth: 360 // Leaflet needs a default, but our CSS will override it for small screens
	});
		counts[COLOR_KEY[col]]++;
	}
	for (const [k] of LEGEND) {
		const el = document.getElementById('cnt-' + k);
		if (el) el.textContent = counts[k] ? `(${counts[k]})` : '';
	}
	const el = document.getElementById('clock');
	if (el) el.textContent = `Paris time: ${fmtMin(now.minute)} - ${WD[now.day]}`;
}