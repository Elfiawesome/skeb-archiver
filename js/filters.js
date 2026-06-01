/* ================================================================
   Skeb Tracker — filters.js
   Filter logic, URL params, sort state, filter button UI sync
   ================================================================ */

App._applyFilters = function() {
	var filtered = App.allUsers.slice();
	var now = Date.now() / 1000;

	if (App.filterAlbumTags.length) {
		filtered = filtered.filter(function(u) {
			return App.filterAlbumTags.some(function(t) { return (u._tags || []).includes(t); });
		});
	}

	if (App.searchTerm) {
		var predicates = App._parseSearchTokens(App.searchTerm);
		filtered = filtered.filter(function(u) { return predicates.every(function(p) { return p(u); }); });
	}
	if (App.filterAcceptable !== null) filtered = filtered.filter(function(u) { return u.acceptable === App.filterAcceptable; });
	if (App.filterNsfw !== null) filtered = filtered.filter(function(u) { return u.nsfw === App.filterNsfw; });
	if (App.filterGenre) filtered = filtered.filter(function(u) { return u.current_prices && u.current_prices.hasOwnProperty(App.filterGenre); });

	if (App.filterPriceMin !== null || App.filterPriceMax !== null) {
		filtered = filtered.filter(function(u) {
			var prices = App._getUserPrices(u, App.filterGenre);
			if (!prices) return false;
			var min = Math.min.apply(null, prices);
			var max = Math.max.apply(null, prices);
			if (App.filterPriceMin !== null && max < App.filterPriceMin) return false;
			if (App.filterPriceMax !== null && min > App.filterPriceMax) return false;
			return true;
		});
	}
	if (App.filterWorksMin !== null) filtered = filtered.filter(function(u) { return (u.total_works || 0) >= App.filterWorksMin; });
	if (App.filterWorksMax !== null) filtered = filtered.filter(function(u) { return (u.total_works || 0) <= App.filterWorksMax; });
	if (App.filterSeenOlderDays !== null) {
		(function(t) {
			filtered = filtered.filter(function(u) { return u.first_seen && u.first_seen < t; });
		})(now - App.filterSeenOlderDays * 86400);
	}
	if (App.filterUpdatedWithinDays !== null) {
		(function(t) {
			filtered = filtered.filter(function(u) { return u.last_updated && u.last_updated > t; });
		})(now - App.filterUpdatedWithinDays * 86400);
	}

	if (App.sortChain.length) {
		filtered.sort(function(a, b) {
			for (var i = 0; i < App.sortChain.length; i++) {
				var cmp = App._compare(a, b, App.sortChain[i]);
				if (cmp !== 0) return cmp;
			}
			return 0;
		});
	}

	App.filteredUsers = filtered;
	App._updateFilterButtonsUI();
	App._updateURL();
	App._renderUsers();
	App._renderPagination();
	App._renderAlbumButton();
};

App._getUserPrices = function(u, genre) {
	if (!u.current_prices || !Object.keys(u.current_prices).length) return null;
	return genre ? (
		genre in u.current_prices ? [u.current_prices[genre]] : null
	) : Object.values(u.current_prices);
};

App._compare = function(a, b, sort) {
	var price = function(u) {
		var p = App._getUserPrices(u, App.filterGenre);
		return p ? Math.min.apply(null, p) : Infinity;
	};
	var va, vb;
	switch (sort.key) {
		case 'price':      va = price(a);            vb = price(b);            break;
		case 'works':      va = a.total_works || 0;  vb = b.total_works || 0;  break;
		case 'updated':    va = a.last_updated || 0; vb = b.last_updated || 0; break;
		case 'first_seen': va = a.first_seen || 0;   vb = b.first_seen || 0;   break;
		default: return 0;
	}
	return sort.dir === 'asc' ? va - vb : vb - va;
};

App._readURLParams = function() {
	var p = new URLSearchParams(window.location.search);
	App.searchTerm = p.get('search') || '';
	document.getElementById('searchInput').value = App.searchTerm;

	var a = p.get('acceptable');
	App.filterAcceptable = a === 'true' ? true : (a === 'false' ? false : null);
	var n = p.get('nsfw');
	App.filterNsfw = n === 'true' ? true : (n === 'false' ? false : null);
	App.filterGenre = p.get('genre') || '';
	App.filterPriceMin = p.get('minPrice') ? +p.get('minPrice') : null;
	App.filterPriceMax = p.get('maxPrice') ? +p.get('maxPrice') : null;
	App.filterWorksMin = p.get('worksMin') ? +p.get('worksMin') : null;
	App.filterWorksMax = p.get('worksMax') ? +p.get('worksMax') : null;
	App.filterSeenOlderDays = p.get('seenOlderDays') ? +p.get('seenOlderDays') : null;
	App.filterUpdatedWithinDays = p.get('updatedWithin') ? +p.get('updatedWithin') : null;
	App.currentPage = parseInt(p.get('page')) || 1;

	var sort = p.get('sort') || '';
	App.sortChain = sort ? sort.split(',').map(function(s) {
		var dir = s.split('_').pop();
		return { key: s.replace('_' + dir, ''), dir: dir === 'desc' ? 'desc' : 'asc' };
	}).filter(function(s) { return s.key; }) : [];

	App.filterAlbumTags = p.get('album_tag') ? p.get('album_tag').split(',').filter(Boolean) : [];

	var album = p.get('album') || '';
	var albumUrl = p.get('album_url') || '';
	if (albumUrl) {
		App.currentAlbum = { name: '_external', label: 'External', type: 'curated', _externalUrl: albumUrl };
	} else if (album && album.replace(/\/$/, '') !== 'albums/main_index' && album !== '_file') {
		App.currentAlbum = { name: album, label: album, type: 'curated' };
	} else {
		App.currentAlbum = { name: 'albums/main_index', label: 'All Artists', type: 'full' };
	}

	App._updateFilterButtonsUI();
};

App._updateURL = function() {
	var p = new URLSearchParams();
	if (App.searchTerm) p.set('search', App.searchTerm);
	if (App.filterAcceptable !== null) p.set('acceptable', App.filterAcceptable);
	if (App.filterNsfw !== null) p.set('nsfw', App.filterNsfw);
	if (App.filterGenre) p.set('genre', App.filterGenre);
	if (App.filterPriceMin !== null) p.set('minPrice', App.filterPriceMin);
	if (App.filterPriceMax !== null) p.set('maxPrice', App.filterPriceMax);
	if (App.filterWorksMin !== null) p.set('worksMin', App.filterWorksMin);
	if (App.filterWorksMax !== null) p.set('worksMax', App.filterWorksMax);
	if (App.filterSeenOlderDays !== null) p.set('seenOlderDays', App.filterSeenOlderDays);
	if (App.filterUpdatedWithinDays !== null) p.set('updatedWithin', App.filterUpdatedWithinDays);
	if (App.sortChain.length) p.set('sort', App.sortChain.map(function(s) { return s.key + '_' + s.dir; }).join(','));
	if (App.currentPage > 1) p.set('page', App.currentPage);
	if (App.filterAlbumTags.length) p.set('album_tag', App.filterAlbumTags.join(','));
	if (App.currentAlbum) {
		if (App.currentAlbum._fromFile) {
			// file-loaded albums don't have a URL
		} else if (App.currentAlbum._externalUrl) {
			p.set('album_url', App.currentAlbum._externalUrl);
		} else if ((App.currentAlbum.name || '').replace(/\/$/, '') !== 'albums/main_index') {
			p.set('album', App.currentAlbum.name);
		}
	}
	history.replaceState(null, '', window.location.pathname + (p.toString() ? '?' + p.toString() : ''));
};

App._updateFilterButtonsUI = function() {
	var btnAcc = document.getElementById('filterAcceptable');
	btnAcc.classList.toggle('active', App.filterAcceptable !== null);
	btnAcc.innerHTML = '<iconify-icon icon="mdi:check-circle-outline"></iconify-icon> ' +
		(App.filterAcceptable === null ? 'Accepting' : (App.filterAcceptable ? 'Accepting \u2713' : 'Not accepting \u2717'));

	var btnNsfw = document.getElementById('filterNsfw');
	btnNsfw.classList.toggle('active', App.filterNsfw !== null);
	btnNsfw.innerHTML = '<iconify-icon icon="mdi:alert-octagon-outline"></iconify-icon> ' +
		(App.filterNsfw === null ? 'NSFW' : (App.filterNsfw ? 'NSFW \u2713' : 'No NSFW \u2717'));

	document.getElementById('genreFilter').value = App.filterGenre;
	document.getElementById('priceMin').value = App.filterPriceMin != null ? App.filterPriceMin : '';
	document.getElementById('priceMax').value = App.filterPriceMax != null ? App.filterPriceMax : '';
	document.getElementById('worksMin').value = App.filterWorksMin != null ? App.filterWorksMin : '';
	document.getElementById('worksMax').value = App.filterWorksMax != null ? App.filterWorksMax : '';
	document.getElementById('seenOlderDays').value = App.filterSeenOlderDays != null ? App.filterSeenOlderDays : '';
	document.getElementById('updatedWithinDays').value = App.filterUpdatedWithinDays != null ? App.filterUpdatedWithinDays : '';
};

App._toggleSortKey = function(key) {
	var ex = App.sortChain.find(function(s) { return s.key === key; });
	if (!ex) App.sortChain.push({ key: key, dir: 'asc' });
	else if (ex.dir === 'asc') ex.dir = 'desc';
	else App.sortChain = App.sortChain.filter(function(s) { return s.key !== key; });
	App._renderSortStates();
	App.currentPage = 1;
	App._applyFilters();
};

App._renderSortStates = function() {
	document.querySelectorAll('.sort-chip').forEach(function(chip) {
		var key = chip.dataset.key;
		var act = App.sortChain.find(function(s) { return s.key === key; });
		chip.classList.toggle('active', !!act);
		var dir = chip.querySelector('.toggle-dir');
		if (dir) dir.textContent = act ? (act.dir === 'asc' ? '\u2191' : '\u2193') : '';
	});

	var container = document.getElementById('activeSorts');
	container.innerHTML = App.sortChain.map(function(s) {
		var label = s.key === 'first_seen' ? 'First seen' : s.key.charAt(0).toUpperCase() + s.key.slice(1);
		return '<span class="active-sort-tag">' + label + ' ' + (s.dir === 'asc' ? '\u2191' : '\u2193') + ' <span class="remove-sort" data-key="' + s.key + '">\u2715</span></span>';
	}).join('');
	container.querySelectorAll('.remove-sort').forEach(function(btn) {
		btn.addEventListener('click', function(e) {
			e.stopPropagation();
			App.sortChain = App.sortChain.filter(function(s) { return s.key !== btn.dataset.key; });
			App._renderSortStates();
			App.currentPage = 1;
			App._applyFilters();
		});
	});
};

App._extractGenres = function() {
	var set = {};
	App.allUsers.forEach(function(u) {
		if (u.current_prices) Object.keys(u.current_prices).forEach(function(g) { set[g] = true; });
	});
	App.genreList = Object.keys(set).sort();
	var sel = document.getElementById('genreFilter');
	sel.innerHTML = '<option value="">All genres</option>';
	App.genreList.forEach(function(g) {
		var o = document.createElement('option');
		o.value = g; o.textContent = g;
		sel.appendChild(o);
	});
	sel.value = App.filterGenre;
};

App._toggleAlbumTag = function(tag) {
	var i = App.filterAlbumTags.indexOf(tag);
	i === -1 ? App.filterAlbumTags.push(tag) : App.filterAlbumTags.splice(i, 1);
	App.currentPage = 1;
	App._applyFilters();
};
