// Settings editor for Rafisol (editor.html). Runs entirely client-side: the
// exported file never leaves the browser. Defaults, limits and the command
// list come from defaults.js, which generate_editor_defaults.py builds from
// config_schema.py - the bot re-validates everything on /config import, so
// the checks here are just there to catch mistakes early.
(function () {
	"use strict";

	const R = window.RAFISOL;
	const STORAGE_PREFIX = "rafisol-editor:";
	const SAMPLE_URL = "tests/fixtures/sample_export.json";
	const ID_SLUG = /^[a-z0-9_-]{1,32}$/;
	const DURATION = /^(\d+[wdhms])+$|^\d+$/;
	const HEX = /^#[0-9a-fA-F]{6}$/;

	const $ = (id) => document.getElementById(id);
	const els = {
		pane: $("pane"),
		nav: $("section-nav"),
		guildName: $("guild-name"),
		guildIcon: $("guild-icon"),
		importInput: $("import-input"),
		exportBtn: $("export-btn"),
		resetBtn: $("reset-btn"),
		dirtyNote: $("dirty-note"),
		dropZone: $("drop-zone"),
		status: $("status"),
		restoreBanner: $("restore-banner"),
		restoreText: $("restore-text"),
		restoreBtn: $("restore-btn"),
		restoreDismiss: $("restore-dismiss"),
	};

	const state = {
		data: null,     // the whole export: { schema, _meta, general, ... }
		section: "general",
		dirty: false,
		previews: [],   // refresh functions for previews in the current pane
		statusTimer: null,
	};

	// ---- small helpers

	const clone = (x) => JSON.parse(JSON.stringify(x));
	const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
	const arr = (x) => (Array.isArray(x) ? x : []);

	function el(tag, attrs, children) {
		const node = document.createElement(tag);
		for (const [key, value] of Object.entries(attrs || {})) {
			if (value === undefined || value === null || value === false) continue;
			if (key === "class") node.className = value;
			else if (key === "text") node.textContent = value;
			else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
			else if (key === "value") node.value = value;
			else if (key === "checked") node.checked = value;
			else node.setAttribute(key, value === true ? "" : value);
		}
		for (const child of [].concat(children === undefined ? [] : children)) {
			if (child === null || child === undefined || child === false) continue;
			node.append(child instanceof Node ? child : String(child));
		}
		return node;
	}

	function getPath(path) {
		let node = state.data;
		for (const key of path) {
			if (node === undefined || node === null) return undefined;
			node = node[key];
		}
		return node;
	}

	function setPath(path, value) {
		let node = state.data;
		for (const key of path.slice(0, -1)) node = node[key];
		node[path[path.length - 1]] = value;
		changed();
	}

	function setStatus(message, isError) {
		els.status.textContent = message;
		els.status.classList.toggle("error", !!isError);
		els.status.classList.add("show");
		clearTimeout(state.statusTimer);
		state.statusTimer = setTimeout(() => els.status.classList.remove("show"), 5000);
	}

	function escapeHtml(text) {
		return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
	}

	// ---- server snapshot (_meta) lookups

	const meta = () => (state.data && isObj(state.data._meta) && Array.isArray(state.data._meta.channels) ? state.data._meta : null);

	function channels(types) {
		const m = meta();
		if (!m) return null;
		return m.channels.filter((c) => !types || types.includes(c.type));
	}

	function roles(assignableOnly) {
		const m = meta();
		if (!m) return null;
		return m.roles.filter((r) => r.name !== "@everyone" && (!assignableOnly || r.assignable));
	}

	function channelById(id) {
		const m = meta();
		return m ? m.channels.find((c) => c.id === id) : null;
	}

	function roleById(id) {
		const m = meta();
		return m ? m.roles.find((r) => r.id === id) : null;
	}

	function channelLabel(id) {
		const c = channelById(id);
		if (!c) return meta() ? `unknown channel (${id})` : id;
		return c.type === "category" ? `${c.name} (category)` : `#${c.name}`;
	}

	function roleLabel(id) {
		const r = roleById(id);
		return r ? `@${r.name}` : meta() ? `unknown role (${id})` : id;
	}

	// ---- import normalising (mirrors config_schema.validateConfig, loosely)

	function mergeKnown(def, val) {
		if (Array.isArray(def)) {
			return Array.isArray(val) ? val.filter((x) => typeof x === "string" || typeof x === "number").map(String) : clone(def);
		}
		if (isObj(def)) {
			const out = clone(def);
			if (!isObj(val)) return out;
			for (const key of Object.keys(def)) {
				if (key in val) out[key] = mergeKnown(def[key], val[key]);
			}
			return out;
		}
		if (def === null) { // ids
			if (typeof val === "string") return val || null;
			if (typeof val === "number") return String(val);
			return null;
		}
		return typeof val === typeof def ? val : def;
	}

	const FIELD_DEFAULT = { name: "", value: "", inline: false };
	const THRESHOLD_DEFAULT = { count: 3, action: "timeout", duration: "1h" };

	function fixEmbed(e) {
		const out = mergeKnown(R.embedDefault, e);
		out.fields = arr(e && e.fields).map((f) => mergeKnown(FIELD_DEFAULT, f));
		return out;
	}

	function normalize(raw) {
		const out = mergeKnown(R.defaults, raw);
		out.schema = R.schema;
		const m = raw._meta;
		if (isObj(m) && Array.isArray(m.channels) && Array.isArray(m.roles)) out._meta = m;
		out.permissions.overrides = {};
		const overrides = isObj(raw.permissions) && isObj(raw.permissions.overrides) ? raw.permissions.overrides : {};
		for (const [name, value] of Object.entries(overrides)) out.permissions.overrides[name] = mergeKnown(R.overrideDefault, value);
		out.moderation.warn_thresholds = arr(raw.moderation && raw.moderation.warn_thresholds).map((t) => mergeKnown(THRESHOLD_DEFAULT, t));
		for (const key of ["join", "leave", "dm"]) {
			out.welcome[key].embed = fixEmbed(raw.welcome && raw.welcome[key] && raw.welcome[key].embed);
		}
		out.reaction_roles = arr(raw.reaction_roles).map((menu) => {
			const x = mergeKnown(R.rolemenuDefault, menu);
			x.embed = fixEmbed(menu && menu.embed);
			x.options = arr(menu && menu.options).map((o) => mergeKnown(R.rolemenuOptionDefault, o));
			return x;
		});
		out.posts = arr(raw.posts).map((post) => {
			const x = mergeKnown(R.postDefault, post);
			x.embeds = arr(post && post.embeds).map(fixEmbed);
			return x;
		});
		return out;
	}

	function buildExport() {
		const out = { schema: R.schema };
		if (state.data._meta) out._meta = state.data._meta;
		for (const key of Object.keys(R.defaults)) {
			if (key !== "schema") out[key] = state.data[key];
		}
		return out;
	}

	// ---- persistence

	function storageKey() {
		const m = meta();
		return STORAGE_PREFIX + (m ? m.guild_id : "blank");
	}

	function save() {
		try {
			localStorage.setItem(storageKey(), JSON.stringify({ savedAt: Date.now(), data: state.data }));
			localStorage.setItem(STORAGE_PREFIX + "last", storageKey());
		} catch (e) {
			// storage full or blocked, autosave is just a convenience
		}
	}

	function changed() {
		state.dirty = true;
		els.dirtyNote.classList.remove("d-none");
		save();
		for (const refresh of state.previews) refresh();
		renderNav();
	}

	function load(data, message) {
		state.data = data;
		state.dirty = false;
		els.dirtyNote.classList.add("d-none");
		els.exportBtn.disabled = false;
		els.resetBtn.disabled = false;
		els.restoreBanner.classList.add("d-none");
		renderHeader();
		renderNav();
		renderPane();
		if (message) setStatus(message);
	}

	function importText(text, name) {
		if (text.length > R.maxImportBytes) {
			setStatus("That file is too big to be a Rafisol config.", true);
			return;
		}
		let raw;
		try {
			raw = JSON.parse(text);
		} catch (e) {
			setStatus("That file isn't valid JSON.", true);
			return;
		}
		if (!isObj(raw) || !("general" in raw || "logging" in raw || "_meta" in raw)) {
			setStatus("That doesn't look like a Rafisol config. Get one with /config export.", true);
			return;
		}
		if (typeof raw.schema === "number" && raw.schema > R.schema) {
			setStatus("That config is from a newer version of Rafisol - refresh this page.", true);
			return;
		}
		if (/:\s*\d{17,}/.test(text)) {
			setStatus("Heads up: some IDs in that file are numbers, not strings, so they may have lost precision.", true);
		}
		load(normalize(raw), `Imported ${name}.`);
	}

	function importFile(file) {
		if (!file) return;
		const reader = new FileReader();
		reader.onload = () => importText(String(reader.result), file.name);
		reader.onerror = () => setStatus("Couldn't read that file.", true);
		reader.readAsText(file);
	}

	function exportFile() {
		const issues = findIssues();
		const out = buildExport();
		const blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
		const a = document.createElement("a");
		const m = meta();
		a.href = URL.createObjectURL(blob);
		a.download = `rafisol-${m ? m.guild_id : "settings"}.json`;
		document.body.appendChild(a); a.click(); a.remove();
		setTimeout(() => URL.revokeObjectURL(a.href), 1000);
		state.dirty = false;
		els.dirtyNote.classList.add("d-none");
		setStatus(`Exported ${a.download}. Upload it with /config import.` + (issues.length ? ` (${issues.length} thing${issues.length === 1 ? "" : "s"} to check - see Overview)` : ""));
	}

	// ---- checks shown on the overview (the bot does the real validation)

	function embedLength(e) {
		let total = ["title", "description", "author_name", "footer"].reduce((n, k) => n + (e[k] || "").length, 0);
		for (const f of e.fields) total += f.name.length + f.value.length;
		return total;
	}

	function findIssues() {
		const d = state.data;
		const issues = [];
		const checkIds = (list, label) => {
			const seen = new Set();
			list.forEach((item, i) => {
				if (!ID_SLUG.test(item.id)) issues.push(`${label} #${i + 1} needs an id (lowercase letters, numbers, - or _).`);
				else if (seen.has(item.id)) issues.push(`${label} id "${item.id}" is used twice.`);
				seen.add(item.id);
				if (!item.channel) issues.push(`${label} "${item.id || i + 1}" has no channel.`);
			});
		};
		checkIds(d.reaction_roles, "Role menu");
		checkIds(d.posts, "Post");
		d.reaction_roles.forEach((menu) => {
			if (!menu.options.length) issues.push(`Role menu "${menu.id}" has no roles.`);
			menu.options.forEach((o, i) => {
				if (!o.role) issues.push(`Role menu "${menu.id}" option ${i + 1} has no role.`);
				const r = roleById(o.role);
				if (r && !r.assignable) issues.push(`Role menu "${menu.id}": @${r.name} is above Rafisol's role or managed, so it can't be given out.`);
			});
		});
		d.posts.forEach((post) => {
			if (!post.content && !post.embeds.length) issues.push(`Post "${post.id}" is empty.`);
			if (/discord|clyde/i.test(post.username)) issues.push(`Post "${post.id}": webhook names can't contain "discord" or "clyde".`);
			if (post.embeds.reduce((n, e) => n + embedLength(e), 0) > 6000) issues.push(`Post "${post.id}" has more than 6000 characters of embeds.`);
		});
		const durations = [["Honeypot timeout", d.honeypot.duration]];
		for (const [name, rule] of Object.entries(d.automod.rules)) durations.push([`Automod ${name}`, rule.duration]);
		d.moderation.warn_thresholds.forEach((t) => durations.push([`Warn threshold ${t.count}`, t.duration]));
		for (const [label, value] of durations) {
			if (value && !DURATION.test(value)) issues.push(`${label}: "${value}" isn't a duration (try 10m, 1h, 1d12h).`);
		}
		for (const [key, label] of [["autoroles", "Autoroles"], ["bot_autoroles", "Bot autoroles"]]) {
			for (const id of d.welcome[key]) {
				const r = roleById(id);
				if (r && !r.assignable) issues.push(`${label}: @${r.name} can't be given out by Rafisol.`);
			}
		}
		if (d.honeypot.enabled && !d.honeypot.channel) issues.push("Honeypot is on but has no channel.");
		if (d.automod.enabled && !d.automod.log_channel && !d.logging.channels.moderation) issues.push("Automod is on but there's nowhere to log what it does (set a moderation log channel).");
		for (const key of ["join", "leave"]) {
			if (d.welcome[key].enabled && !d.welcome[key].channel) issues.push(`${key === "join" ? "Join" : "Leave"} messages are on but have no channel.`);
		}
		return issues;
	}

	// ---- controls. each takes a path into state.data and writes straight back to it

	function field(label, control, help, extra) {
		return el("div", { class: "field" }, [
			label ? el("label", {}, [label, extra || null]) : null,
			control,
			help ? el("small", { class: "form-text", text: help }) : null,
		]);
	}

	function textField(path, label, opts) {
		opts = opts || {};
		const counter = opts.max ? el("span", { class: "counter" }) : null;
		const update = () => {
			if (counter) {
				const n = input.value.length;
				counter.textContent = `${n}/${opts.max}`;
				counter.classList.toggle("over", n > opts.max);
			}
			if (opts.validate) input.classList.toggle("is-invalid", input.value !== "" && !opts.validate(input.value));
		};
		const input = el(opts.multiline ? "textarea" : "input", {
			class: "form-control form-control-sm",
			type: opts.multiline ? null : "text",
			rows: opts.multiline ? opts.rows || 3 : null,
			maxlength: opts.max || null,
			placeholder: opts.placeholder || null,
			spellcheck: opts.code ? "false" : null,
			value: getPath(path) || "",
			oninput: () => {
				let value = input.value;
				if (opts.transform) {
					value = opts.transform(value);
					if (value !== input.value) input.value = value;
				}
				setPath(path, value);
				update();
				if (opts.after) opts.after();
			},
		});
		update();
		return field(label, input, opts.help, counter);
	}

	function idField(path, label, opts) {
		return textField(path, label, Object.assign({
			max: 32,
			code: true,
			validate: (v) => ID_SLUG.test(v),
			transform: (v) => v.toLowerCase().replace(/\s+/g, "-"),
			help: "Lowercase letters, numbers, - and _. Used in commands.",
		}, opts));
	}

	function durationField(path, label, help) {
		return textField(path, label, { max: 20, code: true, placeholder: "e.g. 10m, 1h, 1d12h", validate: (v) => DURATION.test(v), help });
	}

	function numberField(path, label, min, max, help) {
		const input = el("input", {
			class: "form-control form-control-sm",
			type: "number",
			min, max,
			value: getPath(path),
			oninput: () => {
				const n = Number(input.value);
				const ok = input.value !== "" && Number.isInteger(n) && n >= min && n <= max;
				input.classList.toggle("is-invalid", !ok);
				if (ok) setPath(path, n);
			},
		});
		return field(label, input, help || `${min}-${max}`);
	}

	function checkField(path, label, help, after) {
		const input = el("input", {
			type: "checkbox",
			checked: !!getPath(path),
			onchange: () => {
				setPath(path, input.checked);
				if (after) after();
			},
		});
		return el("label", { class: "check" }, [input, el("span", {}, [label, help ? el("small", { class: "form-text", text: help }) : null])]);
	}

	function selectField(path, label, options, help, after) {
		const current = getPath(path);
		const select = el("select", {
			class: "custom-select custom-select-sm",
			onchange: () => {
				const option = options.find((o) => String(o[0]) === select.value);
				setPath(path, option ? option[0] : select.value);
				if (after) after();
			},
		}, options.map(([value, text]) => el("option", { value: String(value), text, selected: value === current })));
		return field(label, select, help);
	}

	function colorField(path, label, allowEmpty, help) {
		const value = getPath(path) || "";
		const text = el("input", { class: "form-control form-control-sm", type: "text", maxlength: 7, placeholder: allowEmpty ? "default" : "#552b9d", value, spellcheck: "false" });
		const picker = el("input", { class: "form-control form-control-sm", type: "color", value: HEX.test(value) ? value : "#552b9d" });
		text.addEventListener("input", () => {
			const v = text.value.trim();
			const ok = HEX.test(v) || (allowEmpty && v === "");
			text.classList.toggle("is-invalid", !ok);
			if (ok) {
				setPath(path, v.toLowerCase());
				if (v) picker.value = v;
			}
		});
		picker.addEventListener("input", () => {
			text.value = picker.value;
			text.classList.remove("is-invalid");
			setPath(path, picker.value.toLowerCase());
		});
		return field(label, el("div", { class: "color-row" }, [picker, text]), help);
	}

	function optionsFor(list, labeller) {
		// group channels by category with optgroups
		const groups = new Map();
		for (const item of list) {
			const group = item.category === undefined ? "" : item.category || "No category";
			if (!groups.has(group)) groups.set(group, []);
			groups.get(group).push(item);
		}
		const out = [];
		for (const [group, items] of groups) {
			const opts = items.map((item) => el("option", { value: item.id, text: labeller(item) }));
			out.push(group ? el("optgroup", { label: group }, opts) : opts);
		}
		return out.flat();
	}

	const channelText = (c) => (c.type === "category" ? `${c.name} (category)` : `${c.type === "text" ? "#" : c.type === "voice" ? "🔊 " : c.type + ": "}${c.name}`);
	const roleText = (r) => `@${r.name}${r.assignable === false ? " (can't assign)" : ""}`;

	function pickerList(kind, opts) {
		return kind === "channel" ? channels(opts.types) : roles(opts.assignable);
	}

	function idPicker(path, label, kind, opts) {
		// single channel/role. falls back to a plain id box with no server snapshot
		opts = opts || {};
		const list = pickerList(kind, opts);
		if (!list) {
			return textField(path, label, { max: 21, code: true, placeholder: `${kind} ID`, validate: (v) => /^\d{15,21}$/.test(v), help: opts.help, transform: (v) => v.replace(/\D/g, "") });
		}
		const current = getPath(path);
		const select = el("select", {
			class: "custom-select custom-select-sm",
			onchange: () => {
				setPath(path, select.value || null);
				if (opts.after) opts.after();
			},
		}, [el("option", { value: "", text: opts.none || "None" })].concat(
			current && !list.some((x) => x.id === current) ? [el("option", { value: current, text: kind === "channel" ? channelLabel(current) : roleLabel(current) })] : [],
			optionsFor(list.map((x) => kind === "role" ? Object.assign({}, x, { category: undefined }) : x), kind === "channel" ? channelText : roleText),
		));
		select.value = current || "";
		return field(label, select, opts.help);
	}

	function multiPicker(path, label, kind, opts) {
		opts = opts || {};
		const wrap = el("div");
		const draw = () => {
			const values = getPath(path);
			const list = pickerList(kind, opts);
			const chips = el("div", { class: "chips" }, values.map((id, i) => {
				const info = kind === "channel" ? channelById(id) : roleById(id);
				const swatch = kind === "role" && info && info.color ? el("span", { class: "swatch", style: `background:${info.color}` }) : null;
				return el("span", { class: "chip" + (meta() && !info ? " missing" : "") }, [
					swatch,
					el("span", { class: "name", text: kind === "channel" ? channelLabel(id) : roleLabel(id) }),
					el("button", { type: "button", title: "Remove", "aria-label": "Remove", text: "×", onclick: () => { values.splice(i, 1); changed(); draw(); } }),
				]);
			}));
			let adder;
			if (list) {
				const left = list.filter((x) => !values.includes(x.id));
				adder = el("select", {
					class: "custom-select custom-select-sm",
					onchange: () => {
						if (adder.value) {
							values.push(adder.value);
							changed();
							draw();
						}
					},
				}, [el("option", { value: "", text: left.length ? `Add ${kind}…` : `No more ${kind}s` })].concat(optionsFor(left.map((x) => kind === "role" ? Object.assign({}, x, { category: undefined }) : x), kind === "channel" ? channelText : roleText)));
			} else {
				adder = el("input", {
					class: "form-control form-control-sm",
					type: "text",
					placeholder: `Paste a ${kind} ID and press Enter`,
					onkeydown: (e) => {
						if (e.key !== "Enter") return;
						e.preventDefault();
						const v = adder.value.replace(/\D/g, "");
						if (/^\d{15,21}$/.test(v) && !values.includes(v)) {
							values.push(v);
							changed();
							draw();
						}
					},
				});
			}
			wrap.replaceChildren(values.length ? chips : el("div", { class: "small muted mb-1", text: opts.empty || "None" }), adder);
		};
		draw();
		return field(label, wrap, opts.help);
	}

	function stringList(path, label, opts) {
		// one per line textarea for word lists / domains
		const input = el("textarea", {
			class: "form-control form-control-sm",
			rows: opts.rows || 4,
			spellcheck: "false",
			placeholder: opts.placeholder || "",
			value: getPath(path).join("\n"),
			oninput: () => {
				const items = [];
				for (const line of input.value.split("\n")) {
					const v = (opts.lower ? line.trim().toLowerCase() : line.trim()).slice(0, opts.max || 100);
					if (v && !items.includes(v)) items.push(v);
				}
				setPath(path, items.slice(0, opts.limit || 500));
			},
		});
		return field(label, input, opts.help);
	}

	function listEditor(path, opts) {
		// array of objects shown as collapsible groups with move/remove
		const wrap = el("div");
		const open = new Set();
		const draw = () => {
			const list = getPath(path);
			const items = list.map((item, i) => {
				const details = el("details", { class: "group", open: open.has(item) || opts.openAll });
				details.addEventListener("toggle", () => (details.open ? open.add(item) : open.delete(item)));
				const move = (delta) => {
					const j = i + delta;
					if (j < 0 || j >= list.length) return;
					[list[i], list[j]] = [list[j], list[i]];
					changed();
					draw();
				};
				const titleNode = el("span", { class: "item-title", text: opts.title(item, i) });
				const summary = el("summary", {}, [
					titleNode,
					opts.tags ? opts.tags(item) : null,
					el("span", { class: "item-tools" }, [
						el("button", { type: "button", class: "btn btn-outline-light btn-sm", title: "Move up", "aria-label": "Move up", text: "↑", disabled: i === 0, onclick: (e) => { e.preventDefault(); move(-1); } }),
						el("button", { type: "button", class: "btn btn-outline-light btn-sm", title: "Move down", "aria-label": "Move down", text: "↓", disabled: i === list.length - 1, onclick: (e) => { e.preventDefault(); move(1); } }),
						el("button", { type: "button", class: "btn btn-outline-danger btn-sm", title: "Remove", "aria-label": "Remove", text: "×", onclick: (e) => {
							e.preventDefault();
							if (opts.confirmRemove && !window.confirm(`Remove ${opts.title(item, i)}?`)) return;
							list.splice(i, 1);
							changed();
							draw();
						} }),
					]),
				]);
				const retitle = () => { titleNode.textContent = opts.title(item, i); };
				details.append(summary, el("div", { class: "group-body" }, opts.body(path.concat(i), item, retitle, draw)));
				return details;
			});
			const full = opts.max && list.length >= opts.max;
			wrap.replaceChildren(
				...(items.length ? items : [el("div", { class: "empty-state", text: opts.empty || "Nothing here yet." })]),
				el("button", {
					type: "button",
					class: "btn btn-outline-light btn-sm",
					disabled: full,
					text: full ? `Max ${opts.max}` : opts.addLabel || "+ Add",
					onclick: () => {
						const item = opts.create(list);
						list.push(item);
						open.add(item);
						changed();
						draw();
					},
				}),
			);
		};
		draw();
		return wrap;
	}

	function panel(title, children, intro) {
		return el("div", { class: "panel" }, [title ? el("h2", { class: "h6", text: title }) : null, intro ? el("p", { class: "small muted", text: intro }) : null].concat(children));
	}

	function group(title, children, opts) {
		opts = opts || {};
		return el("details", { class: "group", open: opts.open }, [
			el("summary", {}, [el("span", { text: title }), opts.tag || null]),
			el("div", { class: "group-body" }, children),
		]);
	}

	function onTag(on, text) {
		return el("span", { class: "tag" + (on ? " on" : ""), text: text || (on ? "on" : "off") });
	}

	// ---- markdown-ish preview (escape first, then format, so user text can't inject html)

	const SAMPLE = () => {
		const m = meta();
		return {
			"{user}": "Rafi (@rafi)",
			"{user.mention}": "<span class=\"mention\">@Rafi</span>",
			"{user.name}": "rafi",
			"{user.display}": "Rafi",
			"{user.id}": "123456789012345678",
			"{user.avatar}": "",
			"{user.created}": "January 1, 2024",
			"{server}": escapeHtml(m ? m.guild_name : "Your Server"),
			"{server.id}": m ? m.guild_id : "123456789012345678",
			"{server.icon}": "",
			"{membercount}": "1,234",
			"{membercount.ordinal}": "1234th",
		};
	};

	function md(text) {
		const sample = SAMPLE();
		let s = escapeHtml(text || "");
		s = s.replace(/```(?:\w+\n)?([\s\S]*?)```/g, (_, c) => `<code>${c}</code>`)
			.replace(/`([^`\n]+)`/g, "<code>$1</code>")
			.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
			.replace(/__(.+?)__/g, "<u>$1</u>")
			.replace(/\*([^*\n]+)\*/g, "<i>$1</i>")
			.replace(/(^|\s)_([^_\n]+)_(?=\s|$)/g, "$1<i>$2</i>")
			.replace(/~~(.+?)~~/g, "<s>$1</s>")
			.replace(/\|\|(.+?)\|\|/g, "<span class=\"mention\">$1</span>")
			.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, "<a href=\"$2\" target=\"_blank\" rel=\"noopener noreferrer\">$1</a>")
			.replace(/&lt;#(\d+)&gt;/g, (_, id) => `<span class="mention">${escapeHtml(channelLabel(id))}</span>`)
			.replace(/&lt;@&amp;(\d+)&gt;/g, (_, id) => `<span class="mention">${escapeHtml(roleLabel(id))}</span>`)
			.replace(/&lt;@!?(\d+)&gt;/g, "<span class=\"mention\">@user</span>")
			.replace(/&lt;t:(\d+)(?::[tTdDfFR])?&gt;/g, (_, t) => `<span class="mention">${escapeHtml(new Date(Number(t) * 1000).toLocaleString())}</span>`)
			.replace(/\{[a-z.]+\}/g, (ph) => (ph in sample ? `<span class="ph">${sample[ph]}</span>` : ph))
			.replace(/^### (.*)$/gm, "<b>$1</b>")
			.replace(/^## (.*)$/gm, "<b style=\"font-size:1.1em\">$1</b>")
			.replace(/^# (.*)$/gm, "<b style=\"font-size:1.25em\">$1</b>")
			.replace(/^-# (.*)$/gm, "<small class=\"muted\">$1</small>")
			.replace(/^&gt; (.*)$/gm, "<span style=\"border-left:3px solid #4e5058;padding-left:8px;display:inline-block\">$1</span>");
		const span = document.createElement("span");
		span.innerHTML = s;
		return span;
	}

	function safeImg(url, cls) {
		if (!/^https?:\/\//.test(url || "")) return null;
		return el("img", { class: cls, src: url, alt: "", referrerpolicy: "no-referrer", onerror: (e) => e.target.remove() });
	}

	function embedPreview(e) {
		const isEmpty = !["title", "description", "author_name", "footer", "image", "thumbnail"].some((k) => e[k]) && !e.fields.length;
		if (isEmpty) return null;
		const color = HEX.test(e.color) ? e.color : state.data.general.embed_color;
		const fields = e.fields.filter((f) => f.name || f.value);
		const main = el("div", { class: "e-main" }, [
			e.author_name ? el("div", { class: "e-author" }, [safeImg(e.author_icon), md(e.author_name)]) : null,
			e.title ? el("div", { class: "e-title" }, /^https?:\/\//.test(e.url) ? el("a", { href: e.url, target: "_blank", rel: "noopener noreferrer" }, md(e.title)) : md(e.title)) : null,
			e.description ? el("div", { class: "e-desc" }, md(e.description)) : null,
			fields.length ? el("div", { class: "e-fields" }, fields.map((f) => el("div", { class: "e-field" + (f.inline ? " inline" : "") }, [el("b", {}, md(f.name)), el("div", {}, md(f.value))]))) : null,
		]);
		return el("div", { class: "dc-embed", style: `border-left-color:${color}` }, [
			main,
			safeImg(e.thumbnail, "e-thumb"),
			safeImg(e.image, "e-image"),
			e.footer || e.timestamp ? el("div", { class: "e-footer" }, [safeImg(e.footer_icon), md(e.footer || ""), e.timestamp ? (e.footer ? " • " : "") + "Today at 12:00" : null]) : null,
		]);
	}

	function messagePreview(build) {
		// build() -> { name, avatar, app, content, embeds, extra }
		const node = el("div", { class: "preview" });
		const refresh = () => {
			const m = build();
			const avatar = /^https?:\/\//.test(m.avatar || "") ? el("img", { class: "avatar", src: m.avatar, alt: "", referrerpolicy: "no-referrer", onerror: (e) => e.target.replaceWith(el("div", { class: "avatar" })) }) : el("div", { class: "avatar" });
			const embeds = (m.embeds || []).map(embedPreview).filter(Boolean);
			const empty = !m.content && !embeds.length && !m.extra;
			node.replaceChildren(
				el("div", { class: "preview-label", text: "Preview" }),
				el("div", { class: "msg" }, [
					avatar,
					el("div", { class: "body" }, [
						el("div", {}, [el("span", { class: "author", text: m.name || "Rafisol" }), el("span", { class: "badge-app", text: "APP" })]),
						m.content ? el("div", { class: "text" }, md(m.content)) : null,
						...embeds,
						m.extra || null,
						empty ? el("div", { class: "muted small", text: "(empty message - nothing will be sent)" }) : null,
					]),
				]),
			);
		};
		state.previews.push(refresh);
		refresh();
		return node;
	}

	const PLACEHOLDERS = ["{user}", "{user.mention}", "{user.name}", "{user.display}", "{user.id}", "{user.avatar}", "{user.created}", "{server}", "{server.id}", "{server.icon}", "{membercount}", "{membercount.ordinal}"];

	function placeholderHelp(serverOnly) {
		const list = serverOnly ? PLACEHOLDERS.filter((p) => p.startsWith("{server") || p.startsWith("{member")) : PLACEHOLDERS;
		return el("div", { class: "placeholders mb-2" }, ["Placeholders: ", ...list.flatMap((p, i) => [i ? " " : "", el("code", { text: p, title: "Click to copy", onclick: () => { navigator.clipboard && navigator.clipboard.writeText(p); setStatus(`Copied ${p}`); } })])]);
	}

	function embedEditor(path) {
		const fieldsPath = path.concat("fields");
		return el("div", {}, [
			el("div", { class: "grid" }, [
				textField(path.concat("title"), "Title", { max: 256 }),
				textField(path.concat("url"), "Title link", { max: 2048, placeholder: "https://…" }),
			]),
			textField(path.concat("description"), "Description", { max: 4096, multiline: true, rows: 5 }),
			el("div", { class: "grid" }, [
				colorField(path.concat("color"), "Colour", true, "Empty = server embed colour"),
				textField(path.concat("author_name"), "Author", { max: 256 }),
				textField(path.concat("author_icon"), "Author icon URL", { max: 2048, placeholder: "https://… or {user.avatar}" }),
				textField(path.concat("thumbnail"), "Thumbnail URL", { max: 2048, placeholder: "https://…" }),
				textField(path.concat("image"), "Image URL", { max: 2048, placeholder: "https://…" }),
				textField(path.concat("footer"), "Footer", { max: 2048 }),
				textField(path.concat("footer_icon"), "Footer icon URL", { max: 2048, placeholder: "https://…" }),
			]),
			checkField(path.concat("timestamp"), "Show timestamp"),
			el("label", { class: "small mb-1", text: "Fields" }),
			listEditor(fieldsPath, {
				max: 25,
				addLabel: "+ Add field",
				empty: "No fields.",
				title: (f, i) => f.name || `Field ${i + 1}`,
				create: () => clone(FIELD_DEFAULT),
				body: (p, f, retitle) => [
					textField(p.concat("name"), "Name", { max: 256, after: retitle }),
					textField(p.concat("value"), "Value", { max: 1024, multiline: true, rows: 2 }),
					checkField(p.concat("inline"), "Inline (sit next to other inline fields)"),
				],
			}),
		]);
	}

	// ---- sections

	const LEVEL_TEXT = { everyone: "Everyone", mod: "Mods", admin: "Admins" };
	const ACTION_TEXT = {
		log: "Log only (keep the message)", delete: "Delete message", warn: "Delete + warn", timeout: "Delete + timeout", mute: "Delete + mute", kick: "Delete + kick", ban: "Delete + ban",
	};
	const MODE_TEXT = { normal: "Normal - toggle any number of roles", unique: "Unique - only one role from this menu at a time", verify: "Verify - can only add roles", remove: "Remove - can only remove roles" };
	const CATEGORY_TEXT = { messages: "Messages", members: "Members", voice: "Voice", server: "Server (audit log)", moderation: "Moderation" };

	function pane(title, intro, children) {
		return [el("div", { class: "pane-title" }, [el("h2", { class: "h4 mb-0", text: title })]), intro ? el("p", { class: "pane-intro", text: intro }) : null].concat(children);
	}

	const SECTIONS = [
		{ id: "general", label: "Overview", render: renderGeneral },
		{ id: "permissions", label: "Permissions", render: renderPermissions, count: (d) => Object.keys(d.permissions.overrides).length },
		{ id: "moderation", label: "Moderation", render: renderModeration },
		{ id: "automod", label: "Automod", render: renderAutomod, on: (d) => d.automod.enabled },
		{ id: "honeypot", label: "Honeypot", render: renderHoneypot, on: (d) => d.honeypot.enabled },
		{ id: "logging", label: "Logging", render: renderLogging, count: (d) => Object.values(d.logging.channels).filter(Boolean).length + "/5" },
		{ id: "welcome", label: "Join / Leave", render: renderWelcome, on: (d) => d.welcome.join.enabled || d.welcome.leave.enabled || d.welcome.dm.enabled },
		{ id: "roles", label: "Roles", render: renderRoles },
		{ id: "reaction_roles", label: "Role Menus", render: renderMenus, count: (d) => d.reaction_roles.length },
		{ id: "posts", label: "Webhook Posts", render: renderPosts, count: (d) => d.posts.length },
		{ id: "guide", label: "Guide", render: renderGuide, always: true },
	];

	function renderGeneral() {
		const m = meta();
		const issues = findIssues();
		const server = m
			? panel("Server", [
				el("div", { class: "d-flex align-items-center mb-2" }, [m.guild_icon ? el("img", { class: "guild-icon", src: m.guild_icon, alt: "", referrerpolicy: "no-referrer" }) : null, el("div", {}, [el("div", { class: "h5 mb-0", text: m.guild_name }), el("div", { class: "small muted", text: `ID ${m.guild_id} • exported ${m.exported_at ? new Date(m.exported_at * 1000).toLocaleString() : "?"}` })])]),
				el("p", { class: "small muted mb-0", text: `${m.channels.length} channels and ${m.roles.length} roles from the export, so pickers show names. If you've made new channels or roles since, run /config export again.` }),
			])
			: panel("No server snapshot", [el("p", { class: "small muted mb-0", text: "This config has no channel/role list (you started blank), so channels and roles have to be pasted as IDs. Export from the bot with /config export to get name pickers." })]);
		return pane("Overview", "Rafisol's settings for your server. Pick a section on the left, then Export and upload the file with /config import.", [
			server,
			panel("Look", [colorField(["general", "embed_color"], "Embed colour", false, "Used for Rafisol's embeds unless one sets its own colour.")]),
			panel(`Things to check (${issues.length})`, issues.length ? [el("ul", { class: "issues" }, issues.map((t) => el("li", { text: t })))] : [el("p", { class: "small muted mb-0", text: "Nothing obviously wrong. The bot double-checks everything when you import." })]),
			panel("Applying your changes", [el("ol", { class: "small mb-0" }, [
				el("li", { text: "Click Export .json (top left)." }),
				el("li", {}, ["In Discord, run ", el("code", { text: "/config import" }), " and attach the file."]),
				el("li", { text: "Check the summary and hit Confirm. Undo any time with /config rollback." }),
				el("li", {}, ["Changed a role menu or post? Run ", el("code", { text: "/rolemenu post" }), " or ", el("code", { text: "/post update" }), " to refresh it."]),
			])]),
		]);
	}

	function renderPermissions() {
		const overrides = state.data.permissions.overrides;
		const names = Object.keys(R.commands);
		const list = el("div");
		let justAdded = null;
		const draw = () => {
			const used = Object.keys(overrides);
			const items = used.sort().map((name) => {
				const p = ["permissions", "overrides", name];
				const o = overrides[name];
				const tags = [];
				if (o.disabled) tags.push(el("span", { class: "tag warn", text: "disabled" }));
				return el("details", { class: "group", open: name === justAdded }, [
					el("summary", {}, [el("span", { text: `/${name}` }), ...tags, el("span", { class: "item-tools" }, [el("button", { type: "button", class: "btn btn-outline-danger btn-sm", text: "×", title: "Remove override", "aria-label": "Remove override", onclick: (e) => { e.preventDefault(); delete overrides[name]; changed(); draw(); } })])]),
					el("div", { class: "group-body" }, [
						el("p", { class: "small muted", text: R.commands[name] ? `${R.commands[name][2]}. Normally: ${LEVEL_TEXT[R.commands[name][0]]}${R.commands[name][1] ? ` (or anyone with ${R.commands[name][1].replace(/_/g, " ")})` : ""}.` : "Applies to every command in this group." }),
						checkField(p.concat("disabled"), "Disable this command", "Nobody except admins can use it."),
						el("div", { class: "grid" }, [
							multiPicker(p.concat("allow_roles"), "Allow roles", "role", { help: "These roles can use it even if they normally couldn't." }),
							multiPicker(p.concat("deny_roles"), "Deny roles", "role", { help: "These roles can't use it (beats allow)." }),
							multiPicker(p.concat("allow_channels"), "Only in channels", "channel", { types: null, help: "Empty = any channel. Categories cover their channels." }),
							multiPicker(p.concat("deny_channels"), "Never in channels", "channel", { types: null }),
						]),
					]),
				]);
			});
			const groups = [...new Set(names.filter((n) => n.includes(" ")).map((n) => n.split(" ")[0]))];
			const addable = names.concat(groups).filter((n) => !used.includes(n)).sort();
			const adder = el("select", {
				class: "custom-select custom-select-sm",
				style: "max-width:320px",
				onchange: () => {
					if (!adder.value) return;
					overrides[adder.value] = clone(R.overrideDefault);
					justAdded = adder.value;
					changed();
					draw();
				},
			}, [el("option", { value: "", text: "Add an override for…" })].concat(addable.map((n) => el("option", { value: n, text: `/${n}${groups.includes(n) ? " (whole group)" : ""}` }))));
			list.replaceChildren(...(items.length ? items : [el("div", { class: "empty-state", text: "No overrides - every command uses its normal permissions." })]), adder);
		};
		draw();
		const table = el("table", { class: "table table-sm table-dark small mb-0" }, [
			el("thead", {}, el("tr", {}, [el("th", { text: "Command" }), el("th", { text: "Who" }), el("th", { text: "Also allowed with" })])),
			el("tbody", {}, names.map((n) => el("tr", {}, [el("td", {}, el("code", { text: `/${n}` })), el("td", { text: LEVEL_TEXT[R.commands[n][0]] }), el("td", { text: R.commands[n][1] ? R.commands[n][1].replace(/_/g, " ") : "-" })]))),
		]);
		return pane("Permissions", "Who counts as a mod or admin, plus per-command overrides. The server owner and anyone with Administrator can always use everything.", [
			panel("Staff roles", [el("div", { class: "grid" }, [
				multiPicker(["permissions", "admin_roles"], "Admin roles", "role", { help: "Can use admin commands (settings, role menus, posts) and everything mods can." }),
				multiPicker(["permissions", "mod_roles"], "Mod roles", "role", { help: "Can use moderation commands. People with the matching Discord permission (e.g. Ban Members for /ban) can too." }),
			])]),
			panel("Command overrides", [list]),
			group("Command reference", [el("div", { class: "table-responsive" }, table)]),
		]);
	}

	function renderModeration() {
		const p = ["moderation"];
		const durationNeeded = (action) => ["timeout", "mute", "ban"].includes(action);
		return pane("Moderation", "How /ban, /kick, /timeout, /mute, /warn and /lockdown behave. Cases are logged to the moderation log channel (Logging).", [
			panel("General", [
				el("div", { class: "grid" }, [
					idPicker(p.concat("mute_role"), "Mute role", "role", { assignable: true, none: "Create one automatically", help: "Used by /mute. Rafisol makes a \"Muted\" role on first use if this is empty." }),
				]),
				checkField(p.concat("dm_on_action"), "DM people when they're actioned", "Can be overridden per command with the dm option."),
				textField(p.concat("dm_extra"), "Extra text in DMs", { max: 500, multiline: true, rows: 2, placeholder: "e.g. Appeal at https://…" }),
				checkField(p.concat("require_reason"), "Require a reason for every action"),
				checkField(p.concat("protect_mods"), "Protect mods", "Mods can't action other mods (admins still can)."),
			]),
			panel("Lockdown", [
				multiPicker(p.concat("lockdown_channels"), "Channels locked by /lockdown server:true", "channel", { types: R.lockableChannels, empty: "None - every public text channel gets locked" }),
				textField(p.concat("lockdown_message"), "Message posted in locked channels", { max: 1000, multiline: true, rows: 2 }),
			]),
			panel("Warning punishments", [
				el("p", { class: "small muted", text: "When someone reaches this many active warnings, Rafisol does this automatically." }),
				listEditor(p.concat("warn_thresholds"), {
					max: 10,
					addLabel: "+ Add punishment",
					empty: "No automatic punishments.",
					title: (t) => `${t.count} warnings → ${t.action}${durationNeeded(t.action) ? ` (${t.duration})` : ""}`,
					create: (list) => ({ count: (list.length ? Math.max(...list.map((t) => t.count)) : 0) + 2, action: "timeout", duration: "1h" }),
					body: (tp, t, retitle, redraw) => [el("div", { class: "grid" }, [
						numberField(tp.concat("count"), "Warnings", 1, 100),
						selectField(tp.concat("action"), "Action", [["timeout", "Timeout"], ["mute", "Mute"], ["kick", "Kick"], ["ban", "Ban"]], null, redraw),
						durationNeeded(t.action) ? durationField(tp.concat("duration"), "Duration", t.action === "ban" ? "How long the ban lasts" : null) : null,
					])],
				}),
			]),
		]);
	}

	function renderAutomod() {
		const p = ["automod"];
		const rules = state.data.automod.rules;
		const actions = R.automodActions.map((a) => [a, ACTION_TEXT[a]]);
		const ruleGroup = (name, title, intro, extra) => {
			const rp = p.concat("rules", name);
			const body = el("div");
			const draw = () => {
				const rule = rules[name];
				body.replaceChildren(
					el("p", { class: "small muted", text: intro }),
					checkField(rp.concat("enabled"), "Enabled", null, () => { tag.replaceWith(tag = onTag(rules[name].enabled)); }),
					...extra(rp),
					el("div", { class: "grid" }, [
						selectField(rp.concat("action"), "Action", actions, null, draw),
						["timeout", "mute", "ban"].includes(rule.action) ? durationField(rp.concat("duration"), "Duration") : null,
					]),
				);
			};
			let tag = onTag(rules[name].enabled);
			draw();
			return el("details", { class: "group" }, [el("summary", {}, [el("span", { text: title }), tag]), el("div", { class: "group-body" }, body)]);
		};
		return pane("Automod", "Rafisol's own filters. Mods, admins and anyone with Manage Messages are never filtered.", [
			panel("General", [
				checkField(p.concat("enabled"), "Automod enabled", null, renderNav),
				el("div", { class: "grid" }, [
					idPicker(p.concat("log_channel"), "Log channel", "channel", { types: R.postableChannels, none: "Use the moderation log channel" }),
				]),
				el("div", { class: "grid" }, [
					multiPicker(p.concat("ignored_roles"), "Ignored roles", "role"),
					multiPicker(p.concat("ignored_channels"), "Ignored channels", "channel", { types: null }),
				]),
			]),
			ruleGroup("words", "Blocked words", "One per line. Matches whole words; end with * to match anything starting with it (scam* blocks scammer, scams…).", (rp) => [stringList(rp.concat("list"), "Words", { lower: true, max: 100, limit: 500, rows: 6 })]),
			ruleGroup("invites", "Invite links", "Blocks Discord invites to other servers. Invites to this server are always allowed.", (rp) => [stringList(rp.concat("allow_guilds"), "Allowed server IDs", { rows: 2, placeholder: "one server ID per line" })]),
			ruleGroup("links", "Links", "Blocks every link except the allowed domains (subdomains count).", (rp) => [stringList(rp.concat("allow_domains"), "Allowed domains", { lower: true, max: 253, limit: 200, rows: 4, placeholder: "youtube.com\ntenor.com" })]),
			ruleGroup("mentions", "Mass mentions", "Too many different users/roles mentioned in one message.", (rp) => [numberField(rp.concat("max"), "Max mentions per message", 1, 50)]),
			ruleGroup("spam", "Spam", "Too many messages too quickly.", (rp) => [el("div", { class: "grid" }, [numberField(rp.concat("messages"), "Messages", 2, 30), numberField(rp.concat("seconds"), "Within seconds", 1, 60)])]),
			ruleGroup("caps", "Caps", "Messages that are mostly CAPITAL LETTERS.", (rp) => [el("div", { class: "grid" }, [numberField(rp.concat("percent"), "Caps %", 10, 100), numberField(rp.concat("min_length"), "Only messages with at least this many letters", 1, 2000)])]),
		]);
	}

	function renderHoneypot() {
		const p = ["honeypot"];
		const body = el("div");
		const draw = () => {
			const h = state.data.honeypot;
			body.replaceChildren(
				checkField(p.concat("enabled"), "Honeypot enabled", null, renderNav),
				el("div", { class: "grid" }, [
					idPicker(p.concat("channel"), "Honeypot channel", "channel", { types: ["text", "news", "voice", "stage_voice", "forum", "media"], help: "Put it at the top of the channel list. Or run /honeypot setup to make one." }),
					selectField(p.concat("action"), "What happens", [["softban", "Softban (ban + unban - wipes messages, they can rejoin)"], ["ban", "Ban"], ["kick", "Kick"], ["timeout", "Timeout"]], null, draw),
					["softban", "ban"].includes(h.action) ? selectField(p.concat("delete_seconds"), "Delete their messages from the last", R.honeypotDelete.map((s) => [s, { 3600: "hour", 86400: "24 hours", 259200: "3 days", 604800: "7 days (max)" }[s]])) : null,
					h.action === "timeout" ? durationField(p.concat("duration"), "Timeout length", "Max 28 days") : null,
				]),
				checkField(p.concat("dm"), "DM them about it", "Hacked accounts usually belong to real people who'll want to know."),
				textField(p.concat("warning"), "Warning posted in the channel", { max: 2000, multiline: true, rows: 3 }),
			);
		};
		draw();
		return pane("Honeypot", "A \"DO NOT TYPE HERE\" channel. Hacked accounts and spam bots post in every channel they can see, so anyone who talks here gets removed - and with softban, all their recent spam everywhere gets wiped too. Mods and admins are ignored.", [
			panel(null, [body]),
			messagePreview(() => ({ content: "", embeds: [Object.assign(clone(R.embedDefault), { title: "⚠️ DO NOT TYPE HERE", description: state.data.honeypot.warning, color: "#e74c3c", footer: "Anyone who sends a message here is removed automatically." })] })),
		]);
	}

	function renderLogging() {
		const p = ["logging"];
		const events = state.data.logging.events;
		const byCategory = {};
		for (const [id, [category, label]] of Object.entries(R.logEvents)) (byCategory[category] = byCategory[category] || []).push([id, label]);
		const groups = R.logCategories.map((category) => {
			const box = el("div", { class: "events-grid" });
			const draw = () => box.replaceChildren(...byCategory[category].map(([id, label]) => checkField(p.concat("events", id), label)));
			draw();
			const all = (value) => { for (const [id] of byCategory[category]) events[id] = value; changed(); draw(); };
			return el("div", { class: "panel" }, [
				el("div", { class: "d-flex align-items-center flex-wrap mb-2", style: "gap:8px" }, [
					el("h3", { class: "h6 mb-0", text: CATEGORY_TEXT[category] }),
					el("span", { class: "btn-row ml-auto" }, [
						el("button", { type: "button", class: "btn btn-outline-light btn-sm", text: "All", onclick: () => all(true) }),
						el("button", { type: "button", class: "btn btn-outline-light btn-sm", text: "None", onclick: () => all(false) }),
					]),
				]),
				el("div", { class: "grid" }, [idPicker(p.concat("channels", category), "Log channel", "channel", { types: R.postableChannels, none: "Off", after: renderNav })]),
				box,
			]);
		});
		return pane("Logging", "Logs are posted through a webhook Rafisol makes in each log channel (it needs Manage Webhooks there). Server logs come from the audit log, so they show who did it (needs View Audit Log).", [
			...groups,
			panel("Filters", [
				el("div", { class: "grid" }, [
					multiPicker(p.concat("ignored_channels"), "Ignored channels", "channel", { types: null, help: "Message and voice events here aren't logged. Categories cover their channels." }),
					multiPicker(p.concat("ignored_roles"), "Ignored roles", "role", { help: "Members with these roles aren't logged." }),
				]),
				checkField(p.concat("ignore_bots"), "Ignore bots"),
				el("div", { class: "grid" }, [numberField(p.concat("new_account_days"), "Flag accounts newer than (days)", 0, 365, "Shows a warning on join logs. 0 = off.")]),
			]),
		]);
	}

	function welcomeGroup(key, title, intro, withChannel) {
		const p = ["welcome", key];
		const w = () => state.data.welcome[key];
		let tag = onTag(w().enabled);
		return el("details", { class: "group", open: true }, [
			el("summary", {}, [el("span", { text: title }), tag]),
			el("div", { class: "group-body" }, [
				el("p", { class: "small muted", text: intro }),
				checkField(p.concat("enabled"), "Enabled", null, () => { const t = onTag(w().enabled); tag.replaceWith(t); tag = t; renderNav(); }),
				withChannel ? el("div", { class: "grid" }, [idPicker(p.concat("channel"), "Channel", "channel", { types: R.postableChannels })]) : null,
				placeholderHelp(false),
				el("div", { class: "embed-editor" }, [
					el("div", {}, [
						textField(p.concat("message"), "Message", { max: 2000, multiline: true, rows: 3 }),
						group("Embed", [embedEditor(p.concat("embed"))]),
					]),
					messagePreview(() => ({ content: w().message, embeds: [w().embed] })),
				]),
			]),
		]);
	}

	function renderWelcome() {
		const p = ["welcome"];
		return pane("Join / Leave", "Welcome and goodbye messages, a welcome DM, and roles for new members. (Join/leave logs are in Logging.)", [
			welcomeGroup("join", "Join message", "Posted when someone joins.", true),
			welcomeGroup("leave", "Leave message", "Posted when someone leaves. Mentions won't ping (they're gone).", true),
			welcomeGroup("dm", "Welcome DM", "Sent to new members privately. Lots of people have DMs from servers turned off.", false),
			panel("Roles on join", [
				el("div", { class: "grid" }, [
					multiPicker(p.concat("autoroles"), "Autoroles", "role", { assignable: true, help: "Given to new members (after membership screening, if you use it). Max 10." }),
					multiPicker(p.concat("bot_autoroles"), "Bot autoroles", "role", { assignable: true, help: "Given to new bots instead." }),
				]),
				checkField(p.concat("role_persist"), "Role persist", "Give people their roles back if they leave and rejoin (including the mute role, so leaving doesn't dodge a mute)."),
			]),
		]);
	}

	function renderRoles() {
		const p = ["roles"];
		return pane("Roles", "Self-assignable roles (/rank) and personal custom roles (/customrole). Role menus with buttons have their own section.", [
			panel("Self-assignable roles", [multiPicker(p.concat("self_assignable"), "Roles anyone can toggle with /rank", "role", { assignable: true })]),
			panel("Custom roles", [
				el("p", { class: "small muted", text: "Let people make their own role with a name and colour. The role is deleted if they leave or stop qualifying." }),
				checkField(p.concat("custom_roles", "enabled"), "Custom roles enabled"),
				checkField(p.concat("custom_roles", "allow_boosters"), "Server boosters can have one"),
				el("div", { class: "grid" }, [
					multiPicker(p.concat("custom_roles", "allowed_roles"), "Also allowed for these roles", "role"),
					idPicker(p.concat("custom_roles", "anchor_role"), "Place custom roles just below", "role", { none: "Just below Rafisol's role", help: "So their colour shows over normal roles." }),
				]),
			]),
		]);
	}

	function menuPreview(menu) {
		const options = menu.options.filter((o) => o.role);
		let extra;
		if (menu.type === "select") {
			extra = el("div", { class: "dc-select" }, [el("span", { text: menu.placeholder || "Make a selection" }), el("span", { text: "⌄" })]);
		} else {
			extra = el("div", { class: "dc-buttons" }, options.map((o) => el("span", { class: `dc-button ${o.style}` }, [o.emoji && !o.emoji.startsWith("<") ? o.emoji + " " : o.emoji ? "◆ " : "", o.label || (o.emoji ? "" : roleLabel(o.role).replace(/^@/, ""))])));
		}
		const hasMessage = menu.content || ["title", "description"].some((k) => menu.embed[k]);
		const embeds = hasMessage ? [menu.embed] : [Object.assign(clone(R.embedDefault), { title: "Pick your roles", description: options.map((o) => `${o.emoji ? o.emoji + " " : ""}<@&${o.role}> ${o.description}`.trim()).join("\n") })];
		return { content: menu.content, embeds, extra };
	}

	function renderMenus() {
		return pane("Role Menus", "Buttons or a dropdown people click to get roles. After importing, run /rolemenu post <id> to post (or refresh) a menu.", [
			listEditor(["reaction_roles"], {
				max: 50,
				confirmRemove: true,
				addLabel: "+ Add role menu",
				empty: "No role menus yet.",
				title: (m, i) => m.id || `Menu ${i + 1}`,
				tags: (m) => el("span", { class: "tag" + (m.message_id ? " on" : ""), text: m.message_id ? "posted" : "not posted" }),
				create: (list) => Object.assign(clone(R.rolemenuDefault), { id: `menu-${list.length + 1}` }),
				body: (mp, menu, retitle, redraw) => {
					const optionsBox = el("div");
					const drawOptions = () => optionsBox.replaceChildren(listEditor(mp.concat("options"), {
						max: 25,
						addLabel: "+ Add role",
						empty: "No roles yet.",
						title: (o, i) => o.label || (o.role ? roleLabel(o.role) : `Option ${i + 1}`),
						create: () => clone(R.rolemenuOptionDefault),
						body: (op, o, retitleOption) => [el("div", { class: "grid" }, [
							idPicker(op.concat("role"), "Role", "role", { assignable: true, none: "Pick a role", after: retitleOption }),
							textField(op.concat("label"), "Label", { max: 80, after: retitleOption, placeholder: "defaults to the role name" }),
							textField(op.concat("emoji"), "Emoji", { max: 64, placeholder: "😀 or <:name:id>" }),
							menu.type === "buttons" ? selectField(op.concat("style"), "Button colour", [["secondary", "Grey"], ["primary", "Blurple"], ["success", "Green"], ["danger", "Red"]]) : null,
							menu.type === "select" ? textField(op.concat("description"), "Description", { max: 100 }) : null,
						])],
					}));
					drawOptions();
					return [
						el("div", { class: "grid" }, [
							idField(mp.concat("id"), "ID", { after: retitle }),
							idPicker(mp.concat("channel"), "Channel", "channel", { types: R.postableChannels }),
							selectField(mp.concat("type"), "Style", [["buttons", "Buttons"], ["select", "Dropdown"]], null, () => { drawOptions(); }),
							selectField(mp.concat("mode"), "Mode", R.rolemenuModes.map((m) => [m, MODE_TEXT[m]])),
							textField(mp.concat("placeholder"), "Dropdown placeholder", { max: 150 }),
						]),
						menu.message_id ? el("p", { class: "small muted" }, [`Posted (message ${menu.message_id}). `, el("button", { type: "button", class: "btn btn-outline-light btn-sm", text: "Forget posted message", onclick: () => { menu.message_id = null; changed(); redraw(); } })]) : null,
						el("div", { class: "embed-editor" }, [
							el("div", {}, [
								textField(mp.concat("content"), "Message text", { max: 2000, multiline: true, rows: 2 }),
								group("Embed", [embedEditor(mp.concat("embed"))]),
								el("label", { class: "small mb-1", text: "Roles" }),
								optionsBox,
							]),
							messagePreview(() => menuPreview(menu)),
						]),
					];
				},
			}),
		]);
	}

	function renderPosts() {
		return pane("Webhook Posts", "Messages Rafisol posts through a webhook with a custom name and avatar - rules, info, FAQs. After importing, use /post send <id> to post one and /post update <id> to edit it in place.", [
			placeholderHelp(true),
			listEditor(["posts"], {
				max: 50,
				confirmRemove: true,
				addLabel: "+ Add post",
				empty: "No posts yet.",
				title: (p, i) => p.id || `Post ${i + 1}`,
				tags: (p) => el("span", { class: "tag" + (p.message_id ? " on" : ""), text: p.message_id ? "posted" : "not posted" }),
				create: (list) => Object.assign(clone(R.postDefault), { id: `post-${list.length + 1}`, embeds: [clone(R.embedDefault)] }),
				body: (pp, post, retitle, redraw) => [
					el("div", { class: "grid" }, [
						idField(pp.concat("id"), "ID", { after: retitle }),
						idPicker(pp.concat("channel"), "Channel", "channel", { types: R.postableChannels }),
						textField(pp.concat("username"), "Webhook name", { max: 80, placeholder: "defaults to the server name", validate: (v) => !/discord|clyde/i.test(v) }),
						textField(pp.concat("avatar_url"), "Webhook avatar URL", { max: 2048, placeholder: "defaults to the server icon" }),
					]),
					post.message_id ? el("p", { class: "small muted" }, [`Posted (message ${post.message_id}). `, el("button", { type: "button", class: "btn btn-outline-light btn-sm", text: "Forget posted message", onclick: () => { post.message_id = null; post.posted_channel = null; changed(); redraw(); } })]) : null,
					el("div", { class: "embed-editor" }, [
						el("div", {}, [
							textField(pp.concat("content"), "Message text", { max: 2000, multiline: true, rows: 3 }),
							el("label", { class: "small mb-1", text: "Embeds" }),
							listEditor(pp.concat("embeds"), {
								max: 10,
								openAll: post.embeds.length === 1,
								addLabel: "+ Add embed",
								empty: "No embeds.",
								title: (e, i) => e.title || `Embed ${i + 1}`,
								create: () => clone(R.embedDefault),
								body: (ep) => [embedEditor(ep)],
							}),
						]),
						messagePreview(() => {
							const m = meta();
							return { name: post.username || (m ? m.guild_name : "Your Server"), avatar: post.avatar_url || (m && m.guild_icon), app: "webhook", content: post.content, embeds: post.embeds };
						}),
					]),
				],
			}),
		]);
	}

	function renderGuide() {
		return pane("Guide", null, [
			panel("How it works", [el("ol", { class: "small mb-0" }, [
				el("li", {}, ["In your server, run ", el("code", { text: "/config export" }), " (needs Manage Server or an admin role). Rafisol sends you a .json file."]),
				el("li", { text: "Here, click Import… (or drop the file on the page)." }),
				el("li", { text: "Change whatever you like. Your work autosaves in this browser." }),
				el("li", {}, ["Click Export .json, then run ", el("code", { text: "/config import" }), " with the file attached and confirm."]),
				el("li", {}, [el("code", { text: "/config rollback" }), " undoes an import. ", el("code", { text: "/config history" }), " lists older versions."]),
			])]),
			panel("Good to know", [el("ul", { class: "small mb-0" }, [
				el("li", { text: "Everything happens in your browser - the file is never uploaded anywhere by this page." }),
				el("li", { text: "Exports never include tokens or webhook URLs, so they're safe to share with other admins." }),
				el("li", { text: "Rafisol checks the whole file on import and tells you about anything it had to fix or drop (deleted channels, roles above its own, etc)." }),
				el("li", { text: "Rafisol can only give out roles below its own highest role. Drag its role up in Server Settings → Roles if a role shows \"can't assign\"." }),
				el("li", { text: "Made new channels or roles? Export again from the bot so they show up in the pickers." }),
			])]),
			panel("Placeholders", [el("p", { class: "small muted", text: "Work in join/leave/DM messages, embeds and posts. {user...} ones only work where there's a member (join/leave/DM)." }), placeholderHelp(false)]),
		]);
	}

	function renderStart() {
		return el("div", { class: "start" }, [
			el("h2", { class: "h4", text: "Rafisol Settings Editor" }),
			el("p", { class: "muted", text: "Edit everything Rafisol does in your server - logging, automod, the honeypot, role menus, webhook posts and more - then upload it back to the bot." }),
			el("ol", {}, [
				el("li", {}, ["Run ", el("code", { text: "/config export" }), " in your server."]),
				el("li", {}, ["Click ", el("b", { text: "Import…" }), " (top left) or drop the file anywhere on this page."]),
				el("li", {}, ["Edit, ", el("b", { text: "Export" }), ", then ", el("code", { text: "/config import" }), "."]),
			]),
			el("div", { class: "btn-row" }, [
				el("label", { class: "btn btn-success btn-sm mb-0", for: "import-input", text: "Import…" }),
				el("button", { type: "button", class: "btn btn-outline-light btn-sm", text: "Try with sample data", onclick: loadSample }),
				el("button", { type: "button", class: "btn btn-outline-light btn-sm", text: "Start blank", onclick: () => load(normalize(clone(R.defaults)), "Started from the defaults. You'll need to paste channel and role IDs.") }),
			]),
		]);
	}

	async function loadSample() {
		try {
			const response = await fetch(SAMPLE_URL);
			if (!response.ok) throw new Error(response.status);
			importText(await response.text(), "sample_export.json");
		} catch (e) {
			setStatus("Couldn't load the sample (it only works when the page is served, not opened as a file).", true);
		}
	}

	// ---- rendering

	function renderHeader() {
		const m = meta();
		els.guildName.textContent = m ? m.guild_name : state.data ? "No server snapshot" : "No server loaded";
		els.guildIcon.classList.toggle("d-none", !(m && m.guild_icon));
		if (m && m.guild_icon) els.guildIcon.src = m.guild_icon;
	}

	function renderNav() {
		const d = state.data;
		els.nav.replaceChildren(...SECTIONS.map((section) => {
			let badge = null;
			if (d && section.on) badge = el("span", { class: "count", text: section.on(d) ? "on" : "off" });
			else if (d && section.count) badge = el("span", { class: "count", text: String(section.count(d)) });
			return el("button", {
				type: "button",
				role: "tab",
				class: section.id === state.section ? "active" : "",
				"aria-selected": section.id === state.section ? "true" : "false",
				disabled: !d && !section.always,
				onclick: () => {
					state.section = section.id;
					renderNav();
					renderPane();
					document.getElementById("main-col").scrollTop = 0;
				},
			}, [section.label, badge]);
		}));
	}

	function renderPane() {
		state.previews = [];
		if (!state.data && state.section !== "guide") {
			els.pane.replaceChildren(renderStart());
			return;
		}
		const section = SECTIONS.find((s) => s.id === state.section) || SECTIONS[0];
		els.pane.replaceChildren(...section.render().filter(Boolean));
	}

	// ---- wiring

	els.importInput.addEventListener("change", () => {
		importFile(els.importInput.files[0]);
		els.importInput.value = "";
	});

	els.exportBtn.addEventListener("click", exportFile);

	els.resetBtn.addEventListener("click", () => {
		if (!window.confirm("Reset every setting to the defaults? (The server's channel/role list is kept.)")) return;
		const keep = state.data._meta;
		const fresh = normalize(clone(R.defaults));
		if (keep) fresh._meta = keep;
		state.data = fresh;
		changed();
		renderPane();
		setStatus("Reset to defaults.");
	});

	["dragenter", "dragover"].forEach((type) => document.addEventListener(type, (e) => {
		if (e.dataTransfer && [...e.dataTransfer.types].includes("Files")) {
			e.preventDefault();
			els.dropZone.classList.add("drop");
		}
	}));
	["dragleave", "drop"].forEach((type) => document.addEventListener(type, (e) => {
		if (type === "dragleave" && e.relatedTarget) return;
		els.dropZone.classList.remove("drop");
	}));
	document.addEventListener("drop", (e) => {
		if (!e.dataTransfer || !e.dataTransfer.files.length) return;
		e.preventDefault();
		importFile(e.dataTransfer.files[0]);
	});

	window.addEventListener("beforeunload", (e) => {
		if (state.dirty) {
			e.preventDefault();
			e.returnValue = "";
		}
	});

	function offerRestore() {
		let saved = null;
		try {
			const key = localStorage.getItem(STORAGE_PREFIX + "last");
			saved = key && JSON.parse(localStorage.getItem(key));
		} catch (e) {
			return;
		}
		if (!saved || !isObj(saved.data)) return;
		const name = saved.data._meta ? saved.data._meta.guild_name : "a blank config";
		els.restoreText.textContent = `You have unsaved work for ${name} from ${new Date(saved.savedAt).toLocaleString()}.`;
		els.restoreBanner.classList.remove("d-none");
		els.restoreBtn.onclick = () => {
			load(normalize(saved.data), `Restored your work for ${name}.`);
			state.dirty = true;
			els.dirtyNote.classList.remove("d-none");
		};
		els.restoreDismiss.onclick = () => els.restoreBanner.classList.add("d-none");
	}

	renderNav();
	renderPane();
	offerRestore();
})();
