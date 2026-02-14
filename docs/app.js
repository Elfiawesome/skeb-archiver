"use strict";

/* ── tiny helpers ────────────────────────────────────────── */
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

function esc(s) {
if (!s) return "";
const d = document.createElement("div");
d.textContent = s;
return d.innerHTML;
}
function fmtDate(iso) {
return iso ? iso.substring(0, 10) : "\u2014";
}
function fmtYen(n) {
return n != null ? "\u00a5" + Number(n).toLocaleString() : "\u2014";
}
function fmtRange(r) {
if (!r) return "";
return r.min === r.max
	? fmtYen(r.min)
	: fmtYen(r.min) + " \u2013 " + fmtYen(r.max);
}

/* ── application ─────────────────────────────────────────── */
const App = {
users: [],
filtered: [],
cache: {},
loading: new Set(),
expanded: new Set(),
sortKey: "last_updated",
sortAsc: false,
search: "",
genre: "art",

/* ── bootstrap ───────────────────────────────────────── */
async init() {
	try {
	const r = await fetch("api/index.json");
	if (!r.ok) throw new Error("HTTP " + r.status);
	const data = await r.json();
	this.users = data.users || [];
	this.renderMeta(data);
	this.bind();
	this.update();
	} catch (e) {
	$("#tbody").innerHTML =
		'<tr><td colspan="5" class="msg">Failed to load data \u2014 ' +
		esc(e.message) +
		"</td></tr>";
	}
},

renderMeta(data) {
	$("#meta").textContent =
	this.users.length + " users \u00b7 " + fmtDate(data.generated_at);

	const total = this.users.reduce(
	(s, u) => s + (u.works_count || 0),
	0
	);
	$("#stats-bar").innerHTML =
	"<span>Users <strong>" + this.users.length + "</strong></span>" +
	"<span>Works <strong>" + total.toLocaleString() + "</strong></span>" +
	"<span>Generated <strong>" + fmtDate(data.generated_at) + "</strong></span>";
},

/* ── event binding ─────────────────────────────────── */
bind() {
	$("#search").addEventListener("input", (e) => {
	this.search = e.target.value.toLowerCase().trim();
	this.update();
	});
	$("#genre-filter").addEventListener("change", (e) => {
	this.genre = e.target.value;
	this.update();
	});
	$$("th[data-sort]").forEach((th) => {
	th.addEventListener("click", () => {
		const k = th.dataset.sort;
		if (this.sortKey === k) this.sortAsc = !this.sortAsc;
		else {
		this.sortKey = k;
		this.sortAsc = k === "screen_name";
		}
		this.update();
	});
	});
},

/* ── price access ──────────────────────────────────── */
getPrice(u) {
	const cp = u.current_prices || {};
	if (this.genre !== "all") return cp[this.genre] ?? null;
	for (const g of ["art", "voice", "novel", "comic"]) {
	if (cp[g] != null) return cp[g];
	}
	return null;
},

/* ── filter + sort ─────────────────────────────────── */
filter() {
	let list = this.users;

	if (this.search)
	list = list.filter((u) =>
		u.screen_name.toLowerCase().includes(this.search)
	);

	if (this.genre !== "all")
	list = list.filter((u) => {
		const cp = u.current_prices || {};
		return cp[this.genre] != null;
	});

	const key = this.sortKey;
	const dir = this.sortAsc ? 1 : -1;
	const self = this;

	list = list.slice().sort((a, b) => {
	let va, vb;
	switch (key) {
		case "screen_name":
		va = a.screen_name.toLowerCase();
		vb = b.screen_name.toLowerCase();
		return va < vb ? -dir : va > vb ? dir : 0;
		case "price":
		va = self.getPrice(a) ?? -1;
		vb = self.getPrice(b) ?? -1;
		return (va - vb) * dir;
		case "works_count":
		return ((a.works_count || 0) - (b.works_count || 0)) * dir;
		case "first_seen":
		case "last_updated":
		va = a[key] || "";
		vb = b[key] || "";
		return va < vb ? -dir : va > vb ? dir : 0;
		default:
		return 0;
	}
	});

	this.filtered = list;
},

/* ── render pipeline ───────────────────────────────── */
update() {
	this.filter();
	this.renderArrows();
	this.renderTable();
},

renderArrows() {
	$$("th[data-sort]").forEach((th) => {
	let a = th.querySelector(".arrow");
	if (!a) {
		a = document.createElement("span");
		a.className = "arrow";
		th.appendChild(a);
	}
	a.textContent =
		th.dataset.sort === this.sortKey
		? this.sortAsc
			? " \u25b2"
			: " \u25bc"
		: "";
	});
},

renderTable() {
	const tbody = $("#tbody");
	if (!this.filtered.length) {
	tbody.innerHTML =
		'<tr><td colspan="5" class="msg">No users match the filter</td></tr>';
	return;
	}

	const rows = [];
	for (const u of this.filtered) {
	const name = u.screen_name;
	const open = this.expanded.has(name);
	const busy = this.loading.has(name);
	const price = this.getPrice(u);

	rows.push(
		'<tr class="row-user' +
		(open ? " active" : "") +
		'" data-name="' + esc(name) +
		'" data-file="' + esc(u.file) + '">' +
		'<td class="cell-user">' +
			(u.avatar_url
			? '<img class="avatar" src="' + esc(u.avatar_url) +
				'" loading="lazy" onerror="this.style.display=\'none\'">'
			: '<div class="avatar-empty"></div>') +
			'<a class="user-link" href="https://skeb.jp/@' + esc(name) +
			'" target="_blank" rel="noopener">@' + esc(name) + "</a>" +
		"</td>" +
		'<td class="cell-price">' + fmtYen(price) + "</td>" +
		'<td class="cell-num">' + (u.works_count || 0) + "</td>" +
		'<td class="cell-date">' + fmtDate(u.first_seen) + "</td>" +
		'<td class="cell-date">' + fmtDate(u.last_updated) + "</td>" +
		"</tr>"
	);

	if (open) {
		if (busy) {
		rows.push(
			'<tr class="row-detail"><td colspan="5" class="msg">Loading \u2026</td></tr>'
		);
		} else if (this.cache[name]) {
		rows.push(this.renderDetail(this.cache[name]));
		}
	}
	}

	tbody.innerHTML = rows.join("");

	/* rebind row clicks */
	const self = this;
	tbody.querySelectorAll(".row-user").forEach((tr) => {
	tr.addEventListener("click", (ev) => {
		if (ev.target.tagName === "A") return;
		self.toggle(tr.dataset.name, tr.dataset.file);
	});
	});
},

/* ── expand / collapse ─────────────────────────────── */
async toggle(name, file) {
	if (this.expanded.has(name)) {
	this.expanded.delete(name);
	this.renderTable();
	return;
	}

	this.expanded.add(name);

	if (!this.cache[name]) {
	this.loading.add(name);
	this.renderTable();
	try {
		const resp = await fetch(
		"api/users/" + encodeURIComponent(file) + ".json"
		);
		if (!resp.ok) throw new Error("HTTP " + resp.status);
		this.cache[name] = await resp.json();
	} catch (e) {
		this.cache[name] = { screen_name: name, error: e.message };
	}
	this.loading.delete(name);
	}
	this.renderTable();
},

/* ── detail panel ──────────────────────────────────── */
renderDetail(d) {
	if (d.error) {
	return (
		'<tr class="row-detail"><td colspan="5" class="msg">Error: ' +
		esc(d.error) +
		"</td></tr>"
	);
	}

	return (
	'<tr class="row-detail"><td colspan="5">' +
	'<div class="detail-inner">' +
		this.renderDetailHead(d) +
		'<div class="detail-grid">' +
		'<div class="detail-section">' +
			"<h3>Price History</h3>" +
			this.renderPrices(d) +
		"</div>" +
		'<div class="detail-section">' +
			"<h3>Recent Works (" + (d.works || []).length + ")</h3>" +
			this.renderWorks(d) +
		"</div>" +
		"</div>" +
	"</div>" +
	"</td></tr>"
	);
},

renderDetailHead(d) {
	return (
	'<div class="detail-head">' +
		'<div class="detail-identity">' +
		(d.avatar_url
			? '<img class="detail-avatar" src="' + esc(d.avatar_url) +
			'" onerror="this.style.display=\'none\'">'
			: "") +
		"<div>" +
			'<div class="detail-display-name">' +
			esc(d.name || d.screen_name) +
			"</div>" +
			'<a class="detail-sn" href="https://skeb.jp/@' +
			esc(d.screen_name) +
			'" target="_blank" rel="noopener">@' +
			esc(d.screen_name) +
			"</a>" +
		"</div>" +
		"</div>" +
		'<div class="detail-meta">' +
		"<span>First seen " + fmtDate(d.first_seen) + "</span>" +
		"<span>Updated " + fmtDate(d.last_updated) + "</span>" +
		"</div>" +
	"</div>"
	);
},

/* ── price history section ─────────────────────────── */
renderPrices(d) {
	const ph = d.price_history || {};
	const genres = Object.keys(ph);
	if (!genres.length) return '<p class="msg-sm">No price data</p>';

	let html = "";
	for (const genre of genres) {
	const entries = ph[genre] || [];
	if (!entries.length) continue;

	const range = (d.price_range || {})[genre];

	html += '<div class="ph-genre">';
	html += '<div class="ph-genre-head">';
	html += '<span class="genre-tag">' + esc(genre) + "</span>";
	if (range && range.min !== range.max)
		html += '<span class="ph-range">' + fmtRange(range) + "</span>";
	html += "</div>";
	html += '<ul class="ph-list">';

	for (let i = entries.length - 1; i >= 0; i--) {
		const e = entries[i];
		let cls = "";
		if (i > 0) {
		const prev = entries[i - 1].amount || 0;
		const curr = e.amount || 0;
		if (curr > prev) cls = " ph-up";
		else if (curr < prev) cls = " ph-down";
		}
		html +=
		"<li>" +
		'<span class="ph-val' + cls + '">' + fmtYen(e.amount) + "</span>" +
		'<span class="ph-date">' + fmtDate(e.recorded_at) + "</span>" +
		"</li>";
	}

	html += "</ul></div>";
	}
	return html;
},

/* ── works grid section ────────────────────────────── */
renderWorks(d) {
	const works = d.works || [];
	if (!works.length) return '<p class="msg-sm">No works recorded</p>';

	const sorted = works.slice().sort((a, b) => {
	const da = a.created_at || a.scraped_at || "";
	const db = b.created_at || b.scraped_at || "";
	return db.localeCompare(da);
	});

	const MAX = 36;
	const show = sorted.slice(0, MAX);

	let html = '<div class="works-grid">';
	for (const w of show) {
	const path = w.path || "";
	const preview = w.preview || "";
	const genre = w.genre || "";
	const date = w.created_at || w.scraped_at || "";

	html += '<a class="work-card" href="https://skeb.jp' + esc(path) +
		'" target="_blank" rel="noopener">';

	if (preview) {
		html +=
		'<div class="work-thumb" style="background-image:url(\'' +
		esc(preview) +
		"')\"></div>";
	} else {
		html +=
		'<div class="work-thumb work-no-preview"><span>' +
		esc(path.split("/").pop() || "?") +
		"</span></div>";
	}

	html += '<div class="work-info">';
	if (genre) html += '<span class="work-genre">' + esc(genre) + "</span>";
	html += '<span class="work-date">' + fmtDate(date) + "</span>";
	html += "</div></a>";
	}
	html += "</div>";

	if (works.length > MAX)
	html +=
		'<p class="msg-sm" style="margin-top:8px">' +
		"Showing " + MAX + " of " + works.length + " works</p>";

	return html;
},
};

document.addEventListener("DOMContentLoaded", () => App.init());