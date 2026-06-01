/* ================================================================
   Skeb Tracker — query.js
   Custom data query parser, tokeniser, autocomplete index
   ================================================================ */

App._checkCompare = function(actual, op, expected) {
	if (actual === undefined || actual === null) return false;
	if (Array.isArray(actual)) {
		if (op === ':' || op === '=') return actual.some(function(a) { return App._eq(a, expected); });
		if (op === '!=') return !actual.some(function(a) { return App._eq(a, expected); });
		return false;
	}
	switch (op) {
		case ':': case '=': return App._eq(actual, expected);
		case '!=': return !App._eq(actual, expected);
		case '>': return actual > expected;
		case '>=': return actual >= expected;
		case '<': return actual < expected;
		case '<=': return actual <= expected;
	}
	return false;
};

App._parseQueryToken = function(token) {
	var m = token.match(/^(-?)([a-zA-Z0-9_.]+)(>=|<=|!=|=|>|<|:)(.+)$/);
	if (!m) return null;
	var negate = m[1] === '-';
	var path = m[2];
	var op = m[3];
	var value = App._coerceValue(m[4]);
	return function(u) {
		var actual = App._resolvePath(u.custom, path);
		var result = App._checkCompare(actual, op, value);
		return negate ? !result : result;
	};
};

App._parseSearchTokens = function(searchTerm) {
	var tokens = searchTerm.trim().split(/\s+/);
	var predicates = [];
	var textTerms = [];
	for (var i = 0; i < tokens.length; i++) {
		var token = tokens[i];
		if (!token) continue;
		var pred = App._parseQueryToken(token);
		if (pred) {
			predicates.push(pred);
		} else {
			textTerms.push(token);
		}
	}
	if (textTerms.length) {
		(function(t) {
			predicates.push(function(u) { return u.screen_name && u.screen_name.toLowerCase().includes(t); });
		})(textTerms.join(' ').toLowerCase());
	}
	return predicates;
};

// --- autocomplete index ---

App._buildCustomKeyIndex = function() {
	var set = {};
	function walk(obj, prefix) {
		if (obj == null || typeof obj !== 'object') return;
		Object.keys(obj).forEach(function(k) {
			var full = prefix ? prefix + '.' + k : k;
			set[full] = true;
			if (typeof obj[k] === 'object' && obj[k] !== null && !Array.isArray(obj[k])) {
				walk(obj[k], full);
			}
		});
	}
	for (var i = 0; i < App.allUsers.length; i++) {
		var c = App.allUsers[i].custom;
		if (c) walk(c, '');
	}
	App._customKeyIndex = Object.keys(set).sort();
};

// --- screen name index for autocomplete ---

App._buildScreenNameIndex = function() {
	App._screenNameIndex = App.allUsers.map(function(u) { return u.screen_name; }).sort();
};

// --- autocomplete dropdown ---

App._acResults = [];

App._showAutocomplete = function(partial) {
	var dd = document.getElementById('acDropdown');
	if (!dd) return;
	var results = [];
	var lower = partial.toLowerCase();

	if (partial) {
		// matching screen names
		var snIdx = App._screenNameIndex || [];
		for (var i = 0; i < snIdx.length; i++) {
			if (snIdx[i].toLowerCase().includes(lower)) {
				results.push({ type: 'user', text: snIdx[i] });
				if (results.length >= 5) break;
			}
		}
		// matching custom keys
		var keyIdx = App._customKeyIndex || [];
		for (var j = 0; j < keyIdx.length; j++) {
			if (keyIdx[j].toLowerCase().startsWith(lower)) {
				results.push({ type: 'key', text: keyIdx[j] });
				if (results.length >= 10) break;
			}
		}
	}

	App._acResults = results;
	if (!results.length) {
		dd.classList.remove('visible');
		App._acSelected = -1;
		return;
	}

	App._acSelected = -1;
	dd.innerHTML = results.map(function(r, i) {
		var icon = r.type === 'key' ? '<span class="ac-icon ac-icon-key">K</span>' : '<span class="ac-icon ac-icon-user">@</span>';
		var suffix = r.type === 'key' ? ':' : '';
		return '<div class="ac-item" data-idx="' + i + '">' + icon + '<span class="ac-text">' + r.text + suffix + '</span></div>';
	}).join('');
	dd.classList.add('visible');

	dd.querySelectorAll('.ac-item').forEach(function(el) {
		el.addEventListener('mousedown', function(e) {
			e.preventDefault();
			var idx = parseInt(el.dataset.idx);
			if (idx >= 0 && idx < App._acResults.length) App._acceptAutocomplete(idx);
		});
	});
};

App._hideAutocomplete = function() {
	var dd = document.getElementById('acDropdown');
	if (dd) dd.classList.remove('visible');
	App._acSelected = -1;
};

App._acceptAutocomplete = function(idx) {
	var r = App._acResults[idx];
	if (!r) return;
	var input = document.getElementById('searchInput');
	var val = input.value;
	var selStart = input.selectionStart || val.length;

	// find the token being edited
	var before = val.substring(0, selStart);
	var after = val.substring(selStart);

	// find last token start before cursor
	var lastSpace = before.lastIndexOf(' ');
	var tokenStart = lastSpace >= 0 ? lastSpace + 1 : 0;
	var prefix = val.substring(0, tokenStart);

	var replacement;
	if (r.type === 'key') {
		replacement = r.text + ':';
	} else {
		replacement = r.text;
	}

	input.value = prefix + replacement + ' ' + after;
	// set cursor after the replacement
	var newPos = prefix.length + replacement.length;
	if (r.type === 'key') newPos = prefix.length + replacement.length;
	else newPos = prefix.length + replacement.length + 1;
	input.setSelectionRange(newPos, newPos);
	input.focus();

	App._hideAutocomplete();
	// trigger filter
	input.dispatchEvent(new Event('input'));
};

App._handleAutocompleteKey = function(e) {
	var dd = document.getElementById('acDropdown');
	if (!dd || !dd.classList.contains('visible')) return;

	if (e.key === 'ArrowDown') {
		e.preventDefault();
		App._acSelected = Math.min(App._acSelected + 1, App._acResults.length - 1);
		App._highlightACItem();
	} else if (e.key === 'ArrowUp') {
		e.preventDefault();
		App._acSelected = Math.max(App._acSelected - 1, -1);
		App._highlightACItem();
	} else if (e.key === 'Enter' || e.key === 'Tab') {
		if (App._acSelected >= 0) {
			e.preventDefault();
			App._acceptAutocomplete(App._acSelected);
		}
	} else if (e.key === 'Escape') {
		App._hideAutocomplete();
	}
};

App._highlightACItem = function() {
	var dd = document.getElementById('acDropdown');
	if (!dd) return;
	var items = dd.querySelectorAll('.ac-item');
	items.forEach(function(el, i) {
		el.classList.toggle('selected', i === App._acSelected);
	});
};
