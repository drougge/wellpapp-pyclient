# -*- coding: utf-8 -*-

from __future__ import print_function
from __future__ import division

from sys import version_info
if version_info[0] > 2:
	unicode = str
	unichr = chr
	ord = int
	import queue as Queue
else:
	import Queue

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk as gtk
from gi.repository import Gdk as gdk
from gi.repository import GdkPixbuf
from gi.repository.GObject import TYPE_STRING, TYPE_INT
from gi.repository import Pango
from gi.repository.GLib import markup_escape_text, idle_add

from itertools import chain
from os.path import commonprefix
from hashlib import md5
from threading import Thread
from multiprocessing import cpu_count

from wellpapp import Client, RawWrapper, WellpappError

def clean(n):
	n = _uni(n)
	if n[0] in u"-~": return n[1:]
	return n
def prefix(n):
	n = _uni(n)
	if n[0] in u"-~": return n[0]
	return u""

def ishex(s):
	return all(c in "1234567890abcdef" for c in s.lower())

def _uni(s):
	if not isinstance(s, unicode):
		try:
			s = s.decode("utf-8")
		except UnicodeDecodeError:
			s = s.decode("iso-8859-1")
	return s

_fuzz_ignore = u"".join(map(unichr, range(33))) + u"-_()[]{}.,!/\"'?<>@=+%$#|\\"
def _completefuzz(word):
	return [c for c in word.lower() if c not in _fuzz_ignore]

def complete(tw, word):
	assert u" " not in word
	pre = prefix(word)
	word = clean(word)
	fuzz_word = _completefuzz(word)
	if pre == "-":
		known_tags = set()
		if tw.thumbview.get_selected_items():
			lists = ("all", "allcurrent", "currentother")
		else:
			lists = ("any",)
		for li in lists:
			known_tags.update(clean(t) for t in tw.taglist[li])
		known_tags = [tw.ids[t] for t in known_tags]
		def gen():
			yield [t for t in known_tags if t.name.startswith(word)]
			yield [t for t in known_tags if any(a.startswith(word) for a in t.get("alias", ()))]
			yield [t for t in known_tags if _completefuzz(t.name)[:len(fuzz_word)] == fuzz_word]
			yield [t for t in known_tags if any(_completefuzz(a)[:len(fuzz_word)] == fuzz_word for a in t.get("alias", ()))]
		tags_gen = gen()
	else:
		tags_gen = (tw.client.find_tags(t, word) for t in ("EI", "EAI", "FI", "FAI"))
	for tags in tags_gen:
		if len(tags) == 1:
			candidates = [tags[0].name] + tags[0].get("alias", [])
			for name in candidates:
				if name.startswith(word):
					break
			else:
				for name in candidates:
					if _completefuzz(name)[:len(fuzz_word)] == fuzz_word:
						break
				else:
					name = candidates[0]
			return pre + name, [(name, tags[0])]
		if len(tags) > 1: break
	names = {}
	for t in tags:
		names[t.name] = t
		if "alias" in t:
			for n in t.alias:
				names[n] = t
	aliases = [t["alias"] if "alias" in t else [] for t in tags]
	aliases = list(chain(*aliases))
	tags = [t["name"] for t in tags]
	inc = lambda n: n[:len(word)] == word
	candidates = list(filter(inc, tags)) + list(filter(inc, aliases))
	if not candidates:
		inc = lambda n: _completefuzz(n)[:len(fuzz_word)] == fuzz_word
		candidates = list(filter(inc, tags)) + list(filter(inc, aliases))
	common = commonprefix(candidates)
	if _completefuzz(common)[:len(fuzz_word)] != fuzz_word:
		common = word
	word = pre + common
	candidates = [(c, names[c]) for c in candidates]
	return word, candidates

def complete_entry(tw, parent, window, tagfield, event):
	if gdk.keyval_name(event.keyval) == "Tab" and \
	   not event.state & (gdk.ModifierType.SHIFT_MASK | gdk.ModifierType.CONTROL_MASK):
		parent.tab_count += 1
		text = _uni(tagfield.get_text())
		pos = tagfield.get_position()
		spos = text.rfind(u" ", 0, pos - 1) + 1
		left = text[:spos]
		word = text[spos:pos].strip()
		right = text[pos:]
		def update(new_word):
			text = left + new_word + right
			tagfield.set_text(text)
			tagfield.set_position(pos + len(new_word) - len(word))
		if parent.tab_count == 1:
			parent.show_alts([])
			if word:
				new_word, alts = complete(tw, word)
				parent.tab_alts = alts
				if alts:
					parent.show_alts(alts)
					if new_word:
						if len(alts) == 1 and (not right or right[0] != u" "):
							new_word += u" "
						update(new_word)
		elif parent.tab_count == 2:
			parent.tab_count = 0
			if parent.tab_alts:
				left = left + prefix(word)
				word = clean(word)
				dialog = TagCompletionDialog(tw, tw.client, window, word, parent.tab_alts)
				if dialog.run() == gtk.ResponseType.ACCEPT:
					update(dialog.get_tt())
				dialog.destroy()
		return True
	parent.tab_count = 0

class FixedTreeView(gtk.TreeView):
	def __init__(self, **kw):
		gtk.TreeView.__init__(self, **kw)
		self._event = None
		self._select_all_state = False
		self.get_selection().set_select_function(self._sel)
		self.connect('button-press-event', self._press)
		self.connect('button-release-event', self._release)
		self.connect('select-all', self._select_all)

	def _sel(self, selection, model, path, current):
		if self._select_all_state:
			return model[path[0]][5] != "impl"
		return self._event == None

	def _press(self, tv, event, data=None):
		self._select_all_state = False
		if event.state & (gdk.ModifierType.CONTROL_MASK | gdk.ModifierType.SHIFT_MASK):
			return
		if event.button == 2:
			return
		ev = (int(event.x), int(event.y))
		path = self.get_path_at_pos(*ev)
		if not path: return True
		if self.get_selection().path_is_selected(path[0]):
			self._event = ev
		else:
			self._event = None

	def _release(self, tv, event, data=None):
		self._select_all_state = False
		if self._event:
			oldev = self._event
			self._event = None
			if oldev != (int(event.x), int(event.y)): return True
			path = self.get_path_at_pos(*oldev)
			if path: self.set_cursor(path[0], path[1])

	def _select_all(self, self_again):
		self._select_all_state = not self._select_all_state

taglisttypes = [TYPE_STRING] * 6

# In GTK3 the mnemonics are really slow, so I'll fake it with manual
# underlining and an AccelGroup.
def button_with_mnemonic(ag, text, func, *args):
	cb = lambda *a: func(*args)
	button = gtk.Button.new_with_label(text)
	apos = text.index(u"_")
	accel = text[apos + 1]
	key, mod = gtk.accelerator_parse("<Alt>" + accel)
	ag.connect(key, mod, 0, cb)
	text = u"%s<u>%s</u>%s" % (text[:apos], accel, text[apos + 2:])
	button.get_child().set_markup(text)
	button.connect("clicked", cb)
	return button

class TagWindow:
	def __init__(self):
		self.client = Client()
		self.window = gtk.Window(type=gtk.WindowType.TOPLEVEL)
		self.window.set_border_width(2)
		self.window.connect("destroy", self.destroy)
		self.bbox = gtk.HBox(homogeneous=False, spacing=0)
		ag = gtk.AccelGroup()
		self.window.add_accel_group(ag)
		self.b_apply = button_with_mnemonic(ag, u"_Apply", self.apply_action)
		self.b_apply.set_sensitive(False)
		self.b_quit = button_with_mnemonic(ag, u"_Quit", self.destroy)
		self.bbox.pack_start(self.b_apply, True, True, 0)
		self.bbox.pack_end(self.b_quit, False, False, 0)
		self.msg = gtk.Label(label=u"Starting..")
		self.msg.set_ellipsize(Pango.EllipsizeMode.END)
		self.msgbox = gtk.EventBox()
		self.msgbox.add(self.msg)
		self.progress_bar = gtk.ProgressBar()
		self.thumbs = gtk.ListStore(TYPE_STRING, GdkPixbuf.Pixbuf, TYPE_STRING)
		self.thumbview = gtk.IconView(model=self.thumbs)
		self.thumbview.set_pixbuf_column(1)
		self.thumbview.set_tooltip_column(2)
		self.thumbview.set_selection_mode(gtk.SelectionMode.MULTIPLE)
		self.thumbview.connect("selection-changed", self.thumb_selected)
		self.thumbview.connect("item-activated", self.thumb_activated)
		self.thumbview.connect("button-press-event", self.middle_toggle_select)
		self.tagbox = gtk.VBox(homogeneous=False, spacing=0)
		self.tags_all = gtk.ListStore(*taglisttypes)
		self.tags_allcurrent = gtk.ListStore(*taglisttypes)
		self.tags_currentother = gtk.ListStore(*taglisttypes)
		self.tags_other = gtk.ListStore(*taglisttypes)
		self.tags_allview = FixedTreeView(model=self.tags_all)
		celltext = gtk.CellRendererText()
		tvc = gtk.TreeViewColumn("ALL", celltext, markup=0)
		tvc.add_attribute(celltext, "cell-background", 2)
		tvc.add_attribute(celltext, "foreground", 3)
		self.tags_allview.append_column(tvc)
		self.tags_allcurrentview = FixedTreeView(model=self.tags_allcurrent)
		celltext = gtk.CellRendererText()
		tvc = gtk.TreeViewColumn("All Current", celltext, markup=0)
		tvc.add_attribute(celltext, "cell-background", 2)
		tvc.add_attribute(celltext, "foreground", 3)
		self.tags_allcurrentview.append_column(tvc)
		self.tags_currentotherview = FixedTreeView(model=self.tags_currentother)
		celltext = gtk.CellRendererText()
		tvc = gtk.TreeViewColumn("Some Current", celltext, markup=0)
		tvc.add_attribute(celltext, "cell-background", 2)
		tvc.add_attribute(celltext, "foreground", 3)
		self.tags_currentotherview.append_column(tvc)
		self.tags_otherview = FixedTreeView(model=self.tags_other)
		for tv in self.tags_allview, self.tags_allcurrentview, \
		          self.tags_currentotherview, self.tags_otherview:
			tv.connect("row-activated", self.modify_tag)
			tv.connect("button-press-event", self.middle_toggle_select)
		celltext = gtk.CellRendererText()
		tvc = gtk.TreeViewColumn("Some", celltext, markup=0)
		tvc.add_attribute(celltext, "cell-background", 2)
		tvc.add_attribute(celltext, "foreground", 3)
		self.tags_otherview.append_column(tvc)
		guidtype = gtk.TargetEntry.new("text/x-wellpapp-tagguid", 0, 1)
		nametype = gtk.TargetEntry.new("text/x-wellpapp-tagname", 0, 4)
		posttype = gtk.TargetEntry.new("text/x-wellpapp-post-id", 0, 0)
		texttypes = [gtk.TargetEntry.new("STRING", 0, 4), gtk.TargetEntry.new("text/plain", 0, 4)]
		srctypes = texttypes + [nametype, guidtype]
		for widget in self.tags_allview, self.tags_allcurrentview, self.tags_currentotherview, self.tags_otherview:
			widget.drag_source_set(gdk.ModifierType.BUTTON1_MASK, srctypes, gdk.DragAction.COPY)
			widget.drag_source_set_icon_name("text-x-generic")
			widget.connect("drag_data_get", self.drag_get_list)
		for widget, all in (self.tags_allview, True), (self.tags_allcurrentview, False):
			widget.drag_dest_set(gtk.DestDefaults.ALL, [guidtype], gdk.DragAction.COPY)
			widget.connect("drag_data_received", self.drag_put, all)
		self.thumbview.drag_source_set(gdk.ModifierType.BUTTON1_MASK, [posttype] + texttypes, gdk.DragAction.COPY)
		self.thumbview.connect("drag_data_get", self.drag_get_icon)
		self.thumbview.connect("drag_begin", self.drag_icon_begin)
		self.thumbview.drag_dest_set(gtk.DestDefaults.ALL, [guidtype, posttype], gdk.DragAction.COPY)
		self.thumbview.connect("drag_data_received", self.drag_put_thumb)
		self.tagbox.pack_start(self.tags_allview, False, False, 0)
		self.tagbox.pack_start(self.tags_allcurrentview, False, False, 0)
		self.tagbox.pack_start(self.tags_currentotherview, False, False, 0)
		self.tagbox.pack_start(self.tags_otherview, False, False, 0)
		self.mbox = gtk.HPaned()
		self.mbox.set_position(650)
		self.thumbscroll = gtk.ScrolledWindow()
		self.thumbscroll.set_policy(gtk.PolicyType.AUTOMATIC, gtk.PolicyType.ALWAYS)
		self.thumbscroll.add(self.thumbview)
		self.tagscroll = gtk.ScrolledWindow()
		self.tagscroll.set_size_request(150, -1)
		self.tagscroll.set_policy(gtk.PolicyType.AUTOMATIC, gtk.PolicyType.AUTOMATIC)
		tagbox_wp = gtk.Viewport()
		tagbox_wp.add(self.tagbox)
		self.tagscroll.add(tagbox_wp)
		self.mbox.pack1(self.thumbscroll, resize=True, shrink=False)
		self.mbox.pack2(self.tagscroll, resize=True, shrink=False)
		self.vbox = gtk.VBox(homogeneous=False, spacing=0)
		self.vbox.pack_start(self.msgbox, False, False, 0)
		self.vbox.pack_start(self.progress_bar, False, False, 0)
		self.vbox.pack_start(self.mbox, True, True, 0)
		self.vbox.pack_end(self.bbox, False, False, 0)
		self.tagfield = gtk.Entry()
		self.tagfield.set_placeholder_text('tag tag tag')
		self.tagfield.connect("activate", self.apply_action, None)
		self.tagfield.connect("key-press-event", self.tagfield_key)
		key, mod = gtk.accelerator_parse('<Alt>s')
		ag.connect(key, mod, 0, self._focus_tagfield)
		self.tagfield.drag_dest_set(gtk.DestDefaults.ALL, [nametype] + texttypes, gdk.DragAction.COPY)
		self.tagfield.connect("drag_data_received", self.drag_put_tagfield)
		self.vbox.pack_end(self.tagfield, False, False, 0)
		self.window.add(self.vbox)
		self.window.set_default_size(int(self.client.cfg.tagwindow_width), int(self.client.cfg.tagwindow_height))
		self.window.show_all()
		# msgbox and progress_bar occupy the same space (one at a time), so make them the same size
		widgets = (self.msgbox, self.progress_bar,)
		y = max(widget.get_preferred_size().natural_size.height for widget in widgets)
		for widget in widgets:
			widget.set_size_request(-1, y)
		self.progress_bar.hide()
		self.type2colour = dict([cs.split("=") for cs in self.client.cfg.tagcolours.split()])
		self.fullscreen_open = False
		self.taglist = {}
		for pre in ("", "impl"):
			for suf in ("any", "all", "allcurrent", "currentother", "other"):
				self.taglist[pre + suf] = set()
		self.tab_count = 0
		self.tab_alts = []
		self._tagfield_prev_ctx = None

	def _focus_tagfield(self, *a):
		self.tagfield.grab_focus()
		self.tagfield.select_region(-1, -1)

	def drag_icon_begin(self, widget, ctx):
		for path in widget.get_selected_items():
			pixbuf = widget.get_model()[path][1]
			widget.drag_source_set_icon_pixbuf(pixbuf)
			break
		else:
			widget.drag_source_set_icon_name("image")

	def drag_put_tagfield(self, widget, context, x, y, selection, targetType, eventTime):
		# This gets called twice (why?), so ignore it the second time
		if self._tagfield_prev_ctx != context:
			self._tagfield_prev_ctx = context
			tag = _uni(selection.get_data()) + u" "
			text = _uni(self.tagfield.get_text())
			if text and text[-1] not in (u" ", u"="): text += u" "
			text += tag
			self.tagfield.set_text(text)
		# When recieving standard types, we also have to stop the default handler
		context.finish(True, False, eventTime)
		widget.emit_stop_by_name("drag_data_received")

	def drag_put_thumb_guid(self, x, y, selection):
		x += int(self.thumbscroll.get_hadjustment().get_value())
		y += int(self.thumbscroll.get_vadjustment().get_value())
		item = self.thumbview.get_item_at_pos(x, y)
		if not item: return
		iter = self.thumbs.get_iter(item[0])
		m = self.thumbs.get_value(iter, 0)
		# @@ check for changing tag values?
		self._apply([((t, None), None) for t in _uni(selection.get_data()).split()], [], [m])

	def drag_put_thumb_post(self, selection):
		try:
			data = _uni(selection.get_data()).lower()
		except Exception:
			from traceback import print_exc
			print_exc()
			return
		md5s = {t[0] for t in self.thumbs}
		add = [m for m in data.split() if len(m) == 32 and ishex(m) and m not in md5s]
		if add:
			fl = FileLoader(self, add)
			fl.start()

	def drag_put_thumb(self, widget, context, x, y, selection, targetType, eventTime):
		data_type = str(selection.get_data_type())
		if data_type == "text/x-wellpapp-tagguid":
			self.drag_put_thumb_guid(x, y, selection)
		if data_type == "text/x-wellpapp-post-id":
			self.drag_put_thumb_post(selection)

	def drag_put(self, widget, context, x, y, selection, targetType, eventTime, all):
		# @@ check for changing tag values?
		self.apply([((t, None), None) for t in _uni(selection.get_data()).split()], [], all)

	def _drag_get_each(self, model, path, iter, data):
		targetType, l = data
		data = model.get_value(iter, targetType)
		l.append(data)

	def drag_get_list(self, widget, context, selection, targetType, eventTime):
		l = []
		sel = widget.get_selection()
		sel.selected_foreach(self._drag_get_each, (targetType, l))
		# All the examples pass 8, what does it mean?
		selection.set(selection.get_target(), 8, " ".join(l).encode("utf-8"))

	def drag_get_icon(self, widget, context, selection, targetType, eventTime):
		data = ""
		for path in widget.get_selected_items():
			data += self.thumbs[path][0] + " "
		selection.set(selection.get_target(), 8, data[:-1].encode("utf-8"))

	def implications(self, parent, guid):
		dialog = ImplicationsDialog(self, self.client, parent, guid)
		dialog.run()
		self._needs_refresh = dialog.did_something
		dialog.destroy()

	def aliases(self, parent, guid):
		dialog = AliasesDialog(self.client, parent, guid)
		dialog.run()
		dialog.destroy()

	def modify_tag(self, tv, row, *a):
		model = tv.get_model()
		if not model[row][0]:
			return
		pre = prefix(model[row][0])
		guid = clean(model[row][1])[:27]
		tag = self.client.get_tag(guid)
		dialog = TagDialog(self.client, self.window, u"Modify tag", tag.name, tag.type)
		if tag.valuetype:
			vt = markup_escape_text(tag.valuetype)
			mu = "<span color=\"#ff0000\">" + vt + "</span>"
			vtlab = gtk.Label()
			vtlab.set_markup(mu)
			dialog.vbox.pack_start(vtlab, True, True, 0)
		entry = gtk.Entry()
		entry.set_text(tag.name)
		dialog.vbox.pack_start(entry, True, True, 0)
		ag = gtk.AccelGroup()
		dialog.add_accel_group(ag)
		implbutton = button_with_mnemonic(ag, u"_Implications", self.implications, dialog, guid)
		dialog.vbox.pack_start(implbutton, True, True, 0)
		aliasbutton = button_with_mnemonic(ag, u"_Aliases", self.aliases, dialog, guid)
		dialog.vbox.pack_start(aliasbutton, True, True, 0)
		entry.connect("activate", lambda *a: dialog.response(gtk.ResponseType.ACCEPT))
		dialog.show_all()
		self._needs_refresh = False
		if dialog.run() == gtk.ResponseType.ACCEPT:
			new_type = None
			t = dialog.get_tt()
			if t and t != tag.type:
				new_type = t
			new_name = _uni(entry.get_text().strip())
			if new_name == tag.name: new_name = None
			if new_type or new_name:
				try:
					self.client.mod_tag(guid, type=new_type, name=new_name)
					# Don't refresh, just update this tag without re-sorting
					if new_type:
						self.ids[guid].type = new_type
					if new_name:
						self.ids[guid].name = new_name
						model[row][0] = self.fmt_tag(pre + guid)
						model[row][4] = self.txt_tag(pre + guid)
					model[row][3] = self.tag_colour_guid(guid)
				except Exception:
					from traceback import print_exc
					print_exc()
		dialog.destroy()
		if self._needs_refresh: self.refresh()

	def middle_toggle_select(self, widget, event):
		if event.button == 2:
			pathinfo = widget.get_path_at_pos(int(event.x), int(event.y))
			if pathinfo:
				# Why would lists with text and lists with icons have the same interface? Sigh..
				if hasattr(widget, "get_selection"):
					sel = widget.get_selection()
					path = pathinfo[0]
				else:
					sel = widget
					path = pathinfo
				if sel.path_is_selected(path):
					sel.unselect_path(path)
				else:
					sel.select_path(path)
				return True

	def tag_colour(self, type):
		if type in self.type2colour: return self.type2colour[type]
		if isinstance(type, unicode):
			type = type.encode("utf-8")
		return "#%02x%02x%02x" % tuple([int(ord(c) / 1.6) for c in md5(type).digest()[:3]])

	def tag_colour_guid(self, guid):
		return self.tag_colour(self.ids[guid].type)

	def fmt_tag(self, g):
		t = self.ids[clean(g)]
		name = markup_escape_text(prefix(g) + t.name)
		if t.valuetype in (None, "none"): return name
		name = " <span color=\"#ff0000\">★ </span>" + name + " <span color=\"#ff0000\">" + t.valuetype
		if "valuelist" not in t: return name + "</span>"
		if t.localcount == len(t.valuelist) and len(set(t.valuelist)) == 1: # all have the same value
			name += "=" + markup_escape_text(str(t.valuelist[0]))
		else:
			name += " ..."
		return name + "</span>"

	def txt_tag(self, g):
		t = self.ids[clean(g)]
		v = prefix(g) + t.name
		if not t.valuelist: return v
		return " ".join([v + "=" + val.format() for val in set(t.valuelist)])

	def _guid_with_val(self, g):
		t = self.ids[clean(g)]
		if not t.valuelist: return g
		return " ".join([g + "=" + val.format() for val in set(t.valuelist)])

	def put_in_list(self, li):
		lo = getattr(self, "tags_" + li)
		view = getattr(self, "tags_" + li + "view")
		data = []
		for pre, bg in ("", "#ffffff"), ("impl", "#ffd8ee"):
			# unformatted name first for sorting, not put in lo
			data.extend((self.ids[clean(t)].name, self.fmt_tag(t), self._guid_with_val(t), bg, self.tag_colours[clean(t)], self.txt_tag(t), pre) for t in self.taglist[pre + li])
		lo.clear()
		if data:
			view.get_selection().set_mode(gtk.SelectionMode.MULTIPLE)
			# gtk.ListStore doesn't have extend
			for t in sorted(data):
				lo.append(t[1:])
		else:
			# One empty unselectable row to give a bigger drop-target for this group
			view.get_selection().set_mode(gtk.SelectionMode.NONE)
			lo.append()

	def refresh(self):
		self.b_apply.set_sensitive(False)
		PostRefresh(self).start()

	def update_thumb_tooltips(self):
		for thumb in self.thumbs:
			if thumb[0] in self.posts:
				post = self.posts[thumb[0]]
				tip = [post.md5]
				tags = sorted(post.datatags.names.items())
				tip += [name + u": " + unicode(tag.value) for name, tag in tags]
				thumb[2] = u"\n".join(tip)

	def _tagcompute(self, posts, pre):
		def guids(p):
			gs = set(t.pguid for t in p[pre + "fulltags"].values())
			gs.update(t.pguid for t in p[pre + "weaktags"].values())
			return gs
		self.taglist[pre + "all"] = guids(posts[0])
		self.taglist[pre + "any"] = guids(posts[0])
		for p in posts:
			self.taglist[pre + "all"].intersection_update(guids(p))
			self.taglist[pre + "any"].update(guids(p))

	def add_thumbs(self, thumbs):
		for thumb in thumbs:
			self.thumbs.append(thumb)
		self.refresh()

	def known_tag(self, tag):
		return tag["guid"] in self.ids

	def thumb_selected(self, iconview):
		self.update_from_selection()

	def thumb_activated(self, iconview, path):
		if self.fullscreen_open: return
		try:
			self.fullscreen_open = True
			m = self.thumbs[path][0]
			fn = self.client.image_path(m)
			f = FullscreenWindowThread(fn, self)
			f.start()
		except Exception:
			from traceback import print_exc
			print_exc()
			self.fullscreen_open = False

	def update_from_selection(self):
		self._update_from_selection("")
		self._update_from_selection("impl")
		self.put_in_list("allcurrent")
		self.put_in_list("currentother")
		self.put_in_list("other")

	def _update_from_selection(self, pre):
		common = None
		all = set()
		count = 0
		def guids(p):
			gs = set(t.pguid for t in p[pre + "fulltags"].values())
			gs.update(t.pguid for t in p[pre + "weaktags"].values())
			return gs
		for path in self.thumbview.get_selected_items():
			m = self.thumbs[path][0]
			g = guids(self.posts[m])
			if common is None:
				common = g
			else:
				common.intersection_update(g)
			all.update(g)
			count += 1
		if count < 2:
			self.tags_currentotherview.hide()
		else:
			self.tags_currentotherview.show()
		if count == 0:
			self.tags_allcurrentview.hide()
		else:
			self.tags_allcurrentview.show()
		if not common: common = set()
		all.difference_update(self.taglist[pre + "all"])
		all.difference_update(common)
		unique = common.difference(self.taglist[pre + "all"])
		self.taglist[pre + "allcurrent"] = unique
		self.taglist[pre + "currentother"] = all
		other = set(self.taglist[pre + "any"])
		other.difference_update(unique)
		other.difference_update(all)
		other.difference_update(self.taglist[pre + "all"])
		self.taglist[pre + "other"] = other

	def destroy(self, *a):
		gtk.main_quit()

	def fmt_tagalt(self, name, t):
		name = markup_escape_text(name)
		col = self.tag_colour(t)
		return "<span color=\"" + col + "\">" + name + "</span>"

	def show_alts(self, alts):
		self.set_msg(u"")
		mu = " ".join(self.fmt_tagalt(name, t.type) for name, t in alts)
		self.msg.set_markup(mu)

	def tagfield_key(self, tagfield, event):
		return complete_entry(self, self, self.window, tagfield, event)

	def create_tag(self, name):
		dialog = TagDialog(self.client, self.window, u"Create tag", name)
		if dialog.run() == gtk.ResponseType.ACCEPT:
			t = dialog.get_tt()
			if t:
				self.client.add_tag(name, t)
		dialog.destroy()

	def apply_action(self, *a):
		self.set_msg(u"")
		orgtext = _uni(self.tagfield.get_text().strip())
		if not orgtext:
			gtk.main_quit()
			return
		if not len(self.thumbs):
			return
		good = []
		failed = []
		for t in orgtext.split():
			tag = self.client.parse_tag(t)
			if not tag and prefix(t) != u"-":
				self.create_tag(clean(t))
				tag = self.client.parse_tag(t)
			if tag:
				good.append((tag, t))
			else:
				failed.append(t)
		if self.apply(good, failed, False):
			self.tagfield.set_text(orgtext)
		else:
			self.tagfield.set_text(u" ".join(failed))

	def apply(self, good, failed, all):
		if all:
			posts = self.posts
		else:
			posts = [self.thumbs[p][0] for p in self.thumbview.get_selected_items()] or self.posts
		return self._apply(good, failed, posts)

	def _apply(self, good, failed, posts):
		todo = {}
		for tag, t in good:
			try:
				for m in posts:
					if m not in todo: todo[m] = ([], [], [])
					p = prefix(tag[0])
					ctag = clean(tag[0])
					post = self.posts[m]
					if p == "-" and (ctag in post.settags.guids or "~" + ctag in post.settags.guids):
						todo[m][2].append(ctag)
					do_set = False
					if p != "-" and tag[0] not in post.settags.guids:
						do_set = True
					elif tag[1]:
						v = post.tags[tag[0]].value
						if v is None or tag[1].format() != v.format():
							do_set = True
					if do_set:
						if p == "~":
							todo[m][1].append((ctag, tag[1]))
						else:
							assert not p
							todo[m][0].append(tag)
			except Exception:
				from traceback import print_exc
				print_exc()
				failed.append(t)
		bad = False
		todo_m = [m for m, t in todo.items() if t != ([], [], [])]
		if todo_m: self.client.begin_transaction()
		try:
			for m in todo_m:
				full, weak, remove = map(set, todo[m])
				self.client.tag_post(m, full, weak, remove)
		except WellpappError:
			bad = True
		finally:
			if todo_m: self.client.end_transaction()
		self.refresh()
		return bad

	def set_msg(self, msg, bg="#FFFFFF"):
		self.msgbox.modify_bg(gtk.StateType.NORMAL, gdk.color_parse(bg))
		self.msg.set_text(msg)

	def error(self, msg):
		self.set_msg(msg, "#FF4466")

	def progress_begin(self, total_steps):
		self._progress_step = 0
		self._progress_total_steps = total_steps
		self.progress_bar.set_fraction(0.0)
		self.progress_bar.show()
		self.msgbox.hide()

	def progress_step(self):
		if self._progress_step < self._progress_total_steps:
			self._progress_step += 1
			self.progress_bar.set_fraction(self._progress_step / self._progress_total_steps)

	def progress_end(self):
		self._progress_total_steps = 0
		self.progress_bar.hide()
		self.msgbox.show()
		self.b_apply.set_sensitive(True)

	def main(self):
		self.window.show()
		self.tagfield.grab_focus()
		gtk.main()

class TagDialog(gtk.Dialog):
	def __init__(self, client, mainwin, title, tagname, tagtype=None):
		gtk.Dialog.__init__(self, title=title, parent=mainwin, modal=True, destroy_with_parent=True)
		self.add_button(gtk.STOCK_CANCEL, gtk.ResponseType.REJECT)
		self.add_button(gtk.STOCK_OK, gtk.ResponseType.ACCEPT)
		self.set_default_response(gtk.ResponseType.ACCEPT)
		self._client = client
		lab = gtk.Label(label=tagname)
		self.vbox.pack_start(lab, True, True, 0)
		# Workaround for it being impossible to have no selected row, but
		# I still really don't want an immediate enter to be "ok".
		# (Because then when I press enter twice with a misspelled tag
		# I create that tag.)
		self._can_enter = False
		self._cursor_count = 0
		self._tv = self._make_tt_tv(tagtype, tagname)
		self._tv.connect("row-activated", self._accept_maybe)
		self._tv.connect("cursor-changed", self._cursor_changed)
		self.vbox.pack_end(self._tv, True, True, 0)
		self.show_all()

	def _make_tt_tv(self, selname, tagname):
		selpos = None
		ls = gtk.ListStore(TYPE_STRING)
		tt = self._client.metalist(u"tagtypes")
		for pos, t in zip(range(len(tt)), tt):
			ls.append((t,))
			if t == selname: selpos = pos
			if selname is None and tagname[:len(t)] == t: selpos = pos
		tv = gtk.TreeView(model=ls)
		crt = gtk.CellRendererText()
		tv.append_column(gtk.TreeViewColumn(u"Type", crt, text=0))
		if selpos is not None:
			tv.get_selection().select_path((selpos,))
		return tv

	def get_tt(self):
		ls, iter = self._tv.get_selection().get_selected()
		if iter:
			return ls.get_value(iter, 0)

	def _cursor_changed(self, *a):
		# This happens once when the dialog opens, so only set _can_enter the second time
		if self._cursor_count:
			self._can_enter = True
		self._cursor_count += 1

	def _accept_maybe(self, *a):
		if self._can_enter:
			self.response(gtk.ResponseType.ACCEPT)
		else:
			self._can_enter = True

class ImplicationsDialog(gtk.Dialog):
	def __init__(self, tw, client, parent, guid):
		gtk.Dialog.__init__(self, title=u"Implications", parent=parent, modal=True, destroy_with_parent=True)
		self.add_button(gtk.STOCK_CLOSE, gtk.ResponseType.ACCEPT)
		self._tw = tw
		self._client = client
		self.guid = guid
		impl = client.tag_implies(self.guid, True)
		if impl:
			lab = gtk.Label(label=u"Implied by")
			self.vbox.pack_start(lab, True, True, 0)
			rev_impl = gtk.ListStore(TYPE_STRING, TYPE_INT, TYPE_STRING, TYPE_STRING)
			lines = []
			complex = False
			for i in impl[:10]:
				tag = client.get_tag(i.guid, with_prefix=True)
				if i.filter:
					filt = i.filter[0] + unicode(i.filter[1])
				else:
					filt = ""
				val = unicode(i.value or u"")
				if filt or val:
					complex = True
				lines.append((tag.pname, i.prio, filt, val))
			for d in sorted(lines):
				rev_impl.append(d)
			if len(impl) > 10:
				rev_impl.append(("... hidden:", len(impl) - 10, "", ""))
			rev_impl = gtk.TreeView(model=rev_impl)
			if complex:
				headings = ("Tag", "Priority", "Filter", "Value")
			else:
				headings = ("Tag", "Priority")
			for i, n in enumerate(headings):
				crt = gtk.CellRendererText()
				tvc = gtk.TreeViewColumn(n, crt, text=i)
				rev_impl.append_column(tvc)
			rev_impl.get_selection().set_mode(gtk.SelectionMode.NONE)
			self.vbox.pack_start(rev_impl, True, True, 0)
			self.vbox.pack_start(gtk.HSeparator(), True, True, 0)
		lab = gtk.Label(label=u"Implies")
		self.vbox.pack_start(lab, True, True, 0)
		self._ibox = gtk.Table(n_rows=1, n_columns=4)
		self.vbox.pack_start(self._ibox, True, True, 0)
		self._add_name = gtk.Entry()
		self._add_name.connect("activate", self._add)
		self._add_name.connect("key-press-event", self._complete)
		self._add_prio = gtk.Entry()
		self._add_prio.set_width_chars(5)
		self._add_prio.set_text(u"0")
		self._add_prio.connect("activate", self._add)
		self._add_btn = gtk.Button.new_with_label(u"Add")
		self._add_btn.connect("clicked", self._add)
		self._show_impl()
		self.did_something = False
		self.tab_count = 0
		self.tab_alts = []
		self.show_all()

	def _show_impl(self):
		impl = self._client.tag_implies(self.guid)
		[self._ibox.remove(c) for c in self._ibox.get_children()]
		if impl:
			lines = list(map(self._impl_wids, impl))
			self._ibox.resize(len(lines) + 1, 4)
			for row, l in enumerate(sorted(lines)):
				for col, wid in zip(range(4), l[1]):
					self._ibox.attach(wid, col, col + 1, row, row + 1)
			row = len(lines)
		else:
			row = 0
		self._ibox.attach(self._add_name, 0, 1, row, row + 1)
		self._ibox.attach(self._add_prio, 1, 2, row, row + 1)
		self._ibox.attach(self._add_btn, 2, 4, row, row + 1)
		self._ibox.show_all()
		self._add_name.grab_focus()

	def _impl_wids(self, impl):
		name = self._client.get_tag(impl.guid, with_prefix=True).pname
		lab = gtk.Label(label=name)
		if impl.filter or impl.value:
			# Ideally, we'd have support for updating this too.
			prio = gtk.Label(label=str(impl.prio))
			if impl.filter:
				filt = gtk.Label(label=impl.filter[0] + unicode(impl.filter[1]))
			else:
				filt = gtk.Label(label="")
			if impl.value:
				val = gtk.Label(label=unicode(impl.value))
			else:
				val = gtk.Label(label="")
			wids = (lab, prio, filt, val)
		else:
			entry = gtk.Entry()
			entry.set_width_chars(5)
			entry.set_text(unicode(impl.prio))
			entry.connect("activate", lambda *a: self._update(entry, impl.guid))
			update = gtk.Button.new_with_label(u"Update")
			update.connect("clicked", lambda *a: self._update(entry, impl.guid))
			remove = gtk.Button.new_with_label(u"Remove")
			wids = (lab, entry, update, remove)
			remove.connect("clicked", lambda *a: self._remove(wids, impl.guid))
		return name, wids

	def _update(self, entry, guid):
		try:
			prio = int(entry.get_text())
		except ValueError:
			prio = 0
		self._client.add_implies(self.guid, guid, prio)
		self.did_something = True
		entry.set_text(unicode(prio))

	def _remove(self, wids, guid):
		self._client.remove_implies(self.guid, guid)
		self.did_something = True
		for w in wids:
			w.hide()

	def _add(self, *a):
		name = self._add_name.get_text().strip()
		if not name:
			self.emit("close")
			return
		try:
			prio = int(self._add_prio.get_text())
		except ValueError:
			prio = 0
		pre = prefix(name)
		if pre and pre != u"-": return
		tag = self._client.find_tag(name, with_prefix=True)
		if not tag: return
		self._client.add_implies(self.guid, tag, prio)
		self.did_something = True
		self._add_name.set_text(u"")
		self._add_prio.set_text(u"0")
		self._show_impl()

	def show_alts(self, alts):
		# I suppose I should show these, but meh.
		pass

	def _complete(self, tagfield, event):
		return complete_entry(self._tw, self, self, tagfield, event)

class AliasesDialog(gtk.Dialog):
	def __init__(self, client, parent, guid):
		gtk.Dialog.__init__(self, title=u"Aliases", parent=parent, modal=True, destroy_with_parent=True)
		self.add_button(gtk.STOCK_CLOSE, gtk.ResponseType.ACCEPT)
		self._client = client
		self.guid = guid
		self._add_name = gtk.Entry()
		self._add_name.connect("activate", self._add)
		self._add_btn = gtk.Button.new_with_label("Add")
		self._add_btn.connect("clicked", self._add)
		self._list = gtk.Table(n_rows=1, n_columns=2)
		self.vbox.pack_start(self._list, True, True, 0)
		self._refresh()
		self.show_all()

	def _refresh(self):
		tag = self._client.get_tag(self.guid)
		[self._list.remove(c) for c in self._list.get_children()]
		if "alias" in tag:
			lines = [self._wids(n) for n in sorted(tag.alias)]
			self._list.resize(len(lines) + 1, 2)
			for row, wids in zip(range(len(lines)), lines):
				self._list.attach(wids[0], 0, 1, row, row + 1)
				self._list.attach(wids[1], 1, 2, row, row + 1)
			row = len(lines)
		else:
			row = 0
		self._list.attach(self._add_name, 0, 1, row, row + 1)
		self._list.attach(self._add_btn, 1, 2, row, row + 1)
		self._list.show_all()
		self._add_name.grab_focus()

	def _wids(self, name):
		lab = gtk.Label(label=name)
		btn = gtk.Button.new_with_label("Remove")
		btn.connect("clicked", lambda *a: self._rm(name))
		return lab, btn

	def _rm(self, name):
		self._client.remove_alias(name)
		self._refresh()

	def _add(self, *a):
		name = self._add_name.get_text().strip()
		if not name:
			self.emit("close")
			return
		self._client.add_alias(name, self.guid)
		self._add_name.set_text(u"")
		self._refresh()

class TagCompletionDialog(gtk.Dialog):
	def __init__(self, tw, client, parent, word, alts):
		gtk.Dialog.__init__(self, title=u"Completing " + word, parent=parent, modal=True, destroy_with_parent=True)
		self.add_button(gtk.STOCK_CANCEL, gtk.ResponseType.REJECT)
		self.add_button(gtk.STOCK_OK, gtk.ResponseType.ACCEPT)
		self.set_default_response(gtk.ResponseType.ACCEPT)
		self.word = word
		self.alts = gtk.ListStore(*taglisttypes)
		for name, t in sorted(alts):
			m_name = markup_escape_text(name)
			tooltip = [t.name]
			if t.alias:
				tooltip.extend(u"    " + a for a in sorted(t.alias))
			tooltip.append(t.type)
			tooltip.append(u"%d posts, %d weak posts" % (t.posts, t.weak_posts))
			tooltip = [markup_escape_text(l) for l in tooltip]
			for heading, reverse in (("\nImplies", False), ("\nImplied by", True)):
				impl = sorted(client.tag_implies(t.guid, reverse))
				if impl:
					tooltip.append(heading)
					max_show = 12
					if len(impl) > max_show:
						dots = len(impl) - max_show + 1
						impl = impl[:max_show - 1]
					else:
						dots = False
					for i in impl:
						i_t = client.get_tag(i.guid, with_prefix=True)
						iname = markup_escape_text(i_t.pname)
						if i.filter or i.value:
							iname = '<span color="#ff0000">*</span> ' + iname
						tc = tw.tag_colour(i_t.type)
						tooltip.append('    <span color="%s">%s</span>' % (tc, iname))
					if dots:
						tooltip.append("... (%d more)" % (dots,))
			tooltip = "\n".join(tooltip)
			self.alts.append((m_name, t.guid, "#ffffff", tw.tag_colour(t.type), name, tooltip))
		self.altsview = gtk.TreeView(model=self.alts)
		self.altsview.set_tooltip_column(5)
		celltext = gtk.CellRendererText()
		tvc = gtk.TreeViewColumn("Alternatives", celltext, markup=0)
		tvc.add_attribute(celltext, "cell-background", 2)
		tvc.add_attribute(celltext, "foreground", 3)
		self.altsview.append_column(tvc)
		self.altsview.connect("row-activated", lambda *a: self.response(gtk.ResponseType.ACCEPT))
		self.scroll = gtk.ScrolledWindow()
		self.scroll.set_policy(gtk.PolicyType.NEVER, gtk.PolicyType.ALWAYS)
		self.scroll.add(self.altsview)
		self.vbox.pack_start(self.scroll, True, True, 0)
		# This can't be the right way. (Why isn't the size automatically right anyway?)
		initial_y = self.get_preferred_size().natural_size.height
		self.show_all() # This changes all reported sizes
		x = max(el.get_preferred_size().natural_size.width for el in (self.altsview, self.scroll, self))
		y = self.altsview.get_preferred_height_for_width(x).natural_height + initial_y + 5
		self.resize(x, min(y, int(client.cfg.tagwindow_height)))

	def get_tt(self):
		ls, iter = self.altsview.get_selection().get_selected()
		if iter:
			return ls.get_value(iter, 4) + u" "
		else:
			return self.word

# This doesn't actually manage the window, it just loads the image for it.
# Only the main thread ever touches visible objects, because I don't want to
# mess with the locking system (thread_enter etc).
class FullscreenWindowThread(Thread):
	def __init__(self, fn, tw):
		Thread.__init__(self)
		self.name = "FullscreenWindow"
		self._fn = fn
		self._tw = tw
		self._win = None

	def run(self):
		loader = None
		try:
			fh = RawWrapper(open(self._fn, "rb"))
			loader = GdkPixbuf.PixbufLoader()
			fh.seek(0, 2)
			l = fh.tell()
			fh.seek(0)
			r = 0
			Z = 1024 * 256
			steps = (l - 1) // Z + 1
			idle_add(self._tw.progress_begin, steps * 2)
			while r < l:
				data = fh.read(Z)
				if not data:
					break
				idle_add(self._tw.progress_step)
				loader.write(data)
				r += len(data)
				idle_add(self._tw.progress_step)
			if r != l:
				msg = "File changed size while reading (%s)" % (self._fn,)
				idle_add(self._tw.error, msg)
				raise RuntimeError(msg)
			pixbuf = loader.get_pixbuf()
			self._win = FullscreenWindow()
			idle_add(self._win._init, self._tw, pixbuf)
			idle_add(self._tw.set_msg, u"")
		except Exception:
			from traceback import print_exc
			print_exc()
			self._cleanup()
		finally:
			if loader:
				loader.close()
			idle_add(self._tw.progress_end)

	def _cleanup(self, *args):
		self._tw.fullscreen_open = False
		if self._win:
			gtk.Window.destroy(self._win, *args)

class FullscreenWindow(gtk.Window):
	def _init(self, tw, pixbuf):
		self._tw = tw
		self.pixbuf = pixbuf
		self.set_events(gdk.EventMask.BUTTON_PRESS_MASK | gdk.EventMask.KEY_PRESS_MASK)
		self.set_title("Fullscreen window")
		self.modify_bg(gtk.StateType.NORMAL, gdk.Color(0, 0, 0))
		self.show()
		self.fullscreen()
		self.set_size_request(1, 1)
		self.pix_w = self.pixbuf.get_width()
		self.pix_h = self.pixbuf.get_height()
		self.image = gtk.Image()
		self.add(self.image)
		self.connect("configure_event", self._on_configure)
		self.connect('key-press-event', self.key_press_event)
		self.connect("button-press-event", self.destroy)
		self.show_all()

	def _on_configure(self, *args):
		self._scale_pixbuf_to_fit_win()

	def _scale_pixbuf_to_fit_win(self):
		win_w, win_h = self.get_size()
		if (win_w < self.pix_w) or (win_h < self.pix_h):
			scalefactor = min(win_w / self.pix_w, win_h / self.pix_h)
			self.scale_pixbuf_to_scalefactor(scalefactor)
		else:
			self.image.set_from_pixbuf(self.pixbuf)
			self.show_all()

	def scale_pixbuf_to_scalefactor(self, scalefactor):
		new_w = int(round(self.pix_w * scalefactor))
		new_h = int(round(self.pix_h * scalefactor))
		new_pixbuf = self.pixbuf.scale_simple(new_w, new_h, GdkPixbuf.InterpType.HYPER)
		self.image.set_from_pixbuf(new_pixbuf)
		self.show_all()

	def key_press_event(self, spin, event):
		key = gdk.keyval_name(event.keyval).lower()
		# All normal keys and a few special
		if len(key) == 1 or key in ("escape", "space", "return"):
			self.destroy()

	def destroy(self, *args):
		self._tw.fullscreen_open = False
		gtk.Window.destroy(self)

class PostRefresh(Thread):
	def __init__(self, tw):
		Thread.__init__(self)
		self.name = "PostRefresh"
		self.daemon = True
		self.client = Client()
		self.tw = tw

	def run(self):
		if not self.tw._progress_total_steps:
			idle_add(self.tw.progress_begin, len(self.tw.thumbs) + 1)
		posts = []
		to_remove = []
		seen = set()
		for ix, t in enumerate(self.tw.thumbs):
			if t[0] in seen:
				to_remove.append(ix)
			else:
				seen.add(t[0])
				p = self.client.get_post(t[0], True)
				if p:
					posts.append(p)
				else:
					to_remove.append(ix)
					idle_add(self.tw.error, u"Post(s) not found")
			idle_add(self.tw.progress_step)
		for ix in reversed(to_remove):
			del self.tw.thumbs[ix]
		if not posts:
			idle_add(self.tw.error, u"No posts found")
			return
		ids = {}
		for t in chain(*[p.tags for p in posts]):
			tt = ids.setdefault(t.guid, t)
			tt.localcount = tt.get("localcount", 0) + 1
			if "value" in t:
				tt.setdefault("valuelist", []).append(t.value)
		self.tw.ids = ids
		self.tw.posts = {p.md5: p for p in posts}
		self.tw.tag_colours = {tg: self.tw.tag_colour_guid(clean(tg)) for tg in ids}
		idle_add(self.tw.progress_step)
		self.tw._tagcompute(posts, "")
		self.tw._tagcompute(posts, "impl")
		idle_add(self.tw.put_in_list, "all")
		idle_add(self.tw.update_from_selection)
		idle_add(self.tw.update_thumb_tooltips)
		idle_add(self.tw.progress_end)

class FileLoaderWorker(Thread):
	def __init__(self, client, tw, q_in, d_out, z):
		Thread.__init__(self)
		self.name = "FileLoaderWorker"
		self.daemon = True
		self._client = client
		self._tw = tw
		self._q_in = q_in
		self._d_out = d_out
		self._z = z

	def run(self):
		try:
			while True:
				d = self._q_in.get(False)
				m = thumb = None
				try:
					m = self._client.postspec2md5(d)
				except Exception as e:
					print(e)
				idle_add(self._tw.progress_step)
				if m:
					try:
						fn = self._client.thumb_path(m, self._z)
						thumb = GdkPixbuf.Pixbuf.new_from_file(fn)
					except Exception as e:
						print(e)
				self._d_out[d] = (m, thumb,)
				self._q_in.task_done()
				idle_add(self._tw.progress_step)
		except Queue.Empty:
			pass

class FileLoader(Thread):
	def __init__(self, tw, argv):
		Thread.__init__(self)
		self.name = "FileLoader"
		self.daemon = True
		self._tw = tw
		self._argv = argv

	def run(self):
		client = Client()
		q_in = Queue.Queue()
		for d in self._argv:
			q_in.put(d)
		d_out = {}
		# 3 per arg: md5, thumb load, post load, plus one extra at the end in tw.refresh
		idle_add(self._tw.progress_begin, len(self._argv) * 3 + 1)
		z = int(client.cfg.thumb_sizes.split()[0])
		for _ in range(min(cpu_count(), len(self._argv))):
			FileLoaderWorker(client, self._tw, q_in, d_out, z).start()
		q_in.join()
		good = True
		ordered_out = [d_out[d] for d in self._argv]
		if any(not m for m, _ in ordered_out):
			idle_add(self._tw.error, u"File(s) not found")
			org_len = len(ordered_out)
			ordered_out = [v for v in ordered_out if v[0]]
			good = False
			for _ in range(org_len - len(ordered_out)):
				idle_add(self._tw.progress_step)
		if not ordered_out:
			idle_add(self._tw.error, u"No files found")
			idle_add(self._tw.progress_end)
			return
		fallback = None
		if any(not tn for _, tn in ordered_out):
			if good:
				idle_add(self._tw.error, u"Thumbs(s) not found")
			good = False
			fallback = gtk.IconTheme().load_icon("image-missing", z, 0)
		thumbs = [(m, tn or fallback, m) for m, tn in ordered_out]
		idle_add(self._tw.add_thumbs, thumbs)
		if good:
			idle_add(self._tw.set_msg, u"")
		else:
			idle_add(self._tw.progress_end)

def main(arg0, argv):
	if len(argv) < 1:
		print("Usage:", arg0, "post-spec [post-spec [...]]")
		return 1
	tw = TagWindow()
	fl = FileLoader(tw, argv)
	fl.start()
	tw.main()
