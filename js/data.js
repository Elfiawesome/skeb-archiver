/* ================================================================
   Skeb Tracker — data.js
   Album fetching, parsing, decompression, merging
   ================================================================ */

App._fetch = async function(url) {
	var res = await fetch(url);
	if (!res.ok) {
		res = await fetch(
			"https://raw.githubusercontent.com/Elfiawesome/skeb-archiver/refs/heads/archive/" + url
		);
	}
	return res;
};

App._parseAlbumHeader = function(buffer) {
	var view = new DataView(buffer);
	var metaSize = view.getUint32(0, false);
	var metaBytes = new Uint8Array(buffer.slice(4, 4 + metaSize));
	var meta = JSON.parse(new TextDecoder('utf-8').decode(metaBytes));
	var dataSize = new DataView(
		buffer.slice(4 + metaSize, 8 + metaSize)
	).getUint32(0, false);
	return { meta: meta, metaSize: metaSize, dataSize: dataSize, headerSize: 8 + metaSize };
};

App._decompressAndParse = async function(compressed) {
	var stream = new Response(compressed).body.pipeThrough(
		new DecompressionStream('gzip')
	);
	var buf = await new Response(stream).arrayBuffer();
	return JSON.parse(new TextDecoder('utf-8').decode(buf));
};

App._getAlbum = async function(relativePath) {
	var i = relativePath.lastIndexOf('/');
	var dir = i >= 0 ? relativePath.substring(0, i) : '';
	var name = i >= 0 ? relativePath.substring(i + 1) : relativePath;
	var prefix = dir ? dir + '/' : '';
	var base = prefix + name + '.album/' + name + '.';
	var idx = 1;
	var downloaded = 0;
	var meta = null;
	var dataSize = null;
	var headerSize = 0;
	var chunks = [];

	while (meta === null || downloaded < headerSize + dataSize) {
		var jobs = [];
		for (var j = 0; j < 10; j++) jobs.push(App._fetch(base + (idx + j)));
		var responses = await Promise.all(jobs);
		for (var rk = 0; rk < responses.length; rk++) {
			var r = responses[rk];
			if (!r.ok) continue;
			var buf = await r.arrayBuffer();
			if (meta === null) {
				var h = App._parseAlbumHeader(buf);
				meta = h.meta;
				dataSize = h.dataSize;
				headerSize = h.headerSize;
			}
			chunks.push(buf);
			downloaded += buf.byteLength;
		}
		if (meta !== null && dataSize !== null) {
			App._updateProgress(downloaded / (headerSize + dataSize) * 100);
		} else {
			App._updateProgress(-1);
		}
		idx += 10;
	}

	var total = headerSize + dataSize;
	var merged = new Uint8Array(total);
	var off = 0;
	for (var ck = 0; ck < chunks.length; ck++) {
		merged.set(new Uint8Array(chunks[ck]), off);
		off += chunks[ck].byteLength;
	}

	var data = await App._decompressAndParse(merged.slice(headerSize));
	return Object.assign({}, meta, { data: Array.isArray(data) ? data : [] });
};

App._getAlbumFromUrl = async function(url) {
	var r;
	if (url.indexOf('://') >= 0) {
		r = await fetch(url);
	} else {
		r = await App._fetch(url);
	}
	if (!r.ok) throw new Error('HTTP ' + r.status);
	var buf = await r.arrayBuffer();
	var h = App._parseAlbumHeader(buf);
	var data = await App._decompressAndParse(buf.slice(h.headerSize));
	return Object.assign({}, h.meta, { data: Array.isArray(data) ? data : [] });
};

App._getAlbumFromFile = async function(relativePath) {
	var r = await App._fetch(relativePath);
	if (!r.ok) throw new Error('HTTP ' + r.status);
	var buf = await r.arrayBuffer();
	var h = App._parseAlbumHeader(buf);
	var data = await App._decompressAndParse(buf.slice(h.headerSize));
	return Object.assign({}, h.meta, { data: Array.isArray(data) ? data : [] });
};

App._loadAlbumIndex = async function() {
	try {
		var r = await App._fetch('albums/index.json');
		if (r.ok) App.albumIndex = await r.json();
	} catch (e) {
		console.warn('Could not load album index:', e);
		App.albumIndex = { 'albums/main_index': { label: 'All Artists', type: 'full' } };
	}
};

App._tryLoadAlbum = async function(name) {
	try {
		var info = App.albumIndex[name] || {};
		App._showProgress();
		if (info._file) {
			var d = await App._getAlbumFromFile(name + '.album');
		} else {
			var d = await App._getAlbum(name);
		}
		App._hideProgress();
		App.albumEntries = d.data || [];
		App.currentAlbum = {
			name: name,
			label: info.label || d.label || name,
			type: info.type || d.type || 'curated'
		};
	} catch (e) {
		console.error('Failed to load album:', e);
		App._hideProgress();
		App.albumEntries = [];
		App.currentAlbum = { name: 'albums/main_index', label: 'All Artists', type: 'full' };
	}
};

App._tryLoadExternal = async function(url) {
	try {
		App._showProgress();
		var d = await App._getAlbumFromUrl(url);
		App._hideProgress();
		App.albumEntries = d.data || [];
		App.currentAlbum = {
			name: d.name || '_external',
			label: d.label || d.name || 'External',
			type: d.type || 'curated',
			_externalUrl: url
		};
	} catch (e) {
		console.error('Failed to load external album:', e);
		App._hideProgress();
		App.albumEntries = [];
		App.currentAlbum = { name: 'albums/main_index', label: 'All Artists', type: 'full' };
	}
};

App._switchAlbum = async function(name) {
	App.currentPage = 1;
	App.filterAlbumTags = [];

	if (name === 'albums/main_index') {
		App.currentAlbum = { name: 'albums/main_index', label: 'All Artists', type: 'full' };
		App.albumEntries = [];
	} else {
		await App._tryLoadAlbum(name);
	}

	App._onAlbumChanged();
};

App._loadExternalAlbum = async function(url) {
	App.currentPage = 1;
	App.filterAlbumTags = [];
	await App._tryLoadExternal(url);
	App._onAlbumChanged();
};

App._onAlbumChanged = function() {
	App._mergeWithMain();
	App._collectAlbumTags();
	App._buildCustomKeyIndex();
	App._buildScreenNameIndex();
	App._renderSortStates();
	App._updateURL();
	App._applyFilters();
	App._renderAlbumButton();
};

App._mergeWithMain = function() {
	if (!App.currentAlbum || App.currentAlbum.type === 'full' || !App.albumEntries.length) {
		App.allUsers = App.mainData.slice();
		return;
	}

	var map = {};
	for (var i = 0; i < App.mainData.length; i++) {
		map[App.mainData[i].screen_name] = App.mainData[i];
	}

	var merged = [];
	for (var j = 0; j < App.albumEntries.length; j++) {
		var e = App.albumEntries[j];
		var sn = e.screen_name;
		if (!sn) continue;
		var full = map[sn];
		if (full) {
			var copy = Object.assign({}, full);
			if (e.tags) copy._tags = e.tags;
			if (e.notes !== undefined) copy._notes = e.notes;
			if (e.latest_thumbnails && e.latest_thumbnails.length) copy.latest_thumbnails = e.latest_thumbnails;
			if (e.avatar_url) copy.avatar_url = e.avatar_url;
			if (e.current_prices && Object.keys(e.current_prices).length) copy.current_prices = e.current_prices;
			if (e.total_works != null) copy.total_works = e.total_works;
			if (e.acceptable != null) copy.acceptable = e.acceptable;
			merged.push(copy);
		} else {
			merged.push({
				screen_name: sn,
				_tags: e.tags || [],
				_notes: e.notes || '',
				latest_thumbnails: e.latest_thumbnails || [],
				avatar_url: e.avatar_url || '',
				current_prices: e.current_prices || {},
				total_works: e.total_works || 0,
				acceptable: e.acceptable,
				file: App._computeFileKey(sn)
			});
		}
	}
	App.allUsers = merged;
};

App._collectAlbumTags = function() {
	var set = {};
	for (var i = 0; i < App.allUsers.length; i++) {
		var tags = App.allUsers[i]._tags;
		if (tags) tags.forEach(function(t) { set[t] = true; });
	}
	App.albumTags = Object.keys(set).sort();
};
