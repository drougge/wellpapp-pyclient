#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient
from itertools import chain
import pygtk
pygtk.require("2.0")
import gtk
from gobject import threads_init, idle_add, TYPE_STRING
from pango import ELLIPSIZE_END
threads_init()
from os.path import commonprefix
from hashlib import md5
from threading import Thread

def clean(n):
	if n[0] in u"-~": return n[1:]
	return n
def prefix(n):
	if n[0] in u"-~": return n[0]
	return ""

def ishex(s):
	return False not in [c in "1234567890abcdef" for c in s.lower()]

def _uni(s):
	if type(s) is not unicode:
		try:
			s = s.decode("utf-8")
		except Exception:
			s = s.decode("iso-8859-1")
	return s

_fuzz_ignore = u"".join(map(unichr, range(33))) + u"-_()[]{}.,!/\"'?<>@=+%$#|\\"
def _completefuzz(word):
	return filter(lambda c: c not in _fuzz_ignore, word.lower())

def complete(word):
	assert u" " not in word
	pre = prefix(word)
	word = clean(word)
	for t, get in ("EI", lambda t: t["name"]), ("EAI", lambda t: t["alias"][0]), \
	              ("FI", lambda t: t["name"]), ("FAI", lambda t: t["alias"][0]):
		tags = client.find_tags(t, word)
		if pre == "-": tags = filter(tw.known_tag, tags)
		if len(tags) == 1: return pre + get(tags[0]), False
		if len(tags) > 1: break
	aliases = [t["alias"] if "alias" in t else [] for t in tags]
	aliases = chain(*aliases)
	tags = [t["name"] for t in tags]
	inc = lambda n: n[:len(word)] == word
	candidates = filter(inc, tags) + filter(inc, aliases)
	if not candidates:
		word = _completefuzz(word)
		inc = lambda n: _completefuzz(n)[:len(word)] == word
		candidates = filter(inc, tags) + filter(inc, aliases)
		candidates = map(unicode.lower, candidates)
	return pre + commonprefix(candidates), candidates

class FixedTreeView(gtk.TreeView):
	def __init__(self, *args):
		gtk.TreeView.__init__(self, *args)
		self._event = None
		self.get_selection().set_select_function(self._sel)
		self.connect('button-press-event', self._press)
		self.connect('button-release-event', self._release)

	def _sel(self, *args):
		return self._event == None

	def _press(self, tv, event, data=None):
		if event.state & (gtk.gdk.CONTROL_MASK | gtk.gdk.SHIFT_MASK):
			return
		ev = map(int, (event.x, event.y))
		path = self.get_path_at_pos(*ev)
		if not path: return True
		if self.get_selection().path_is_selected(path[0]):
			self._event = ev
		else:
			self._event = None

	def _release(self, tv, event, data=None):
		if self._event:
			oldev = self._event
			self._event = None
			if oldev != map(int, (event.x, event.y)): return True
			path = self.get_path_at_pos(*oldev)
			if path: self.set_cursor(path[0], path[1])

class TagWindow:
	def __init__(self):
		self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
		self.window.set_border_width(2)
		self.window.connect("destroy", self.destroy)
		self.bbox = gtk.HBox(False, 0)
		self.b_apply = gtk.Button(u"_Apply")
		self.b_apply.connect("clicked", self.apply_action, None)
		self.b_quit = gtk.Button(u"_Quit")
		self.b_quit.connect("clicked", self.destroy, None)
		self.bbox.pack_start(self.b_apply, True, True, 0)
		self.bbox.pack_end(self.b_quit, False, False, 0)
		self.msg = gtk.Label(u"Starting..")
		self.msg.set_ellipsize(ELLIPSIZE_END)
		self.msgbox = gtk.EventBox()
		self.msgbox.add(self.msg)
		self.thumbs = gtk.ListStore(TYPE_STRING, gtk.gdk.Pixbuf)
		self.thumbview = gtk.IconView(self.thumbs)
		self.thumbview.set_pixbuf_column(1)
		self.thumbview.set_tooltip_column(0)
		self.thumbview.set_reorderable(True)
		self.thumbview.set_selection_mode(gtk.SELECTION_MULTIPLE)
		self.thumbview.connect("selection-changed", self.thumb_selected)
		self.thumbview.connect("item-activated", self.thumb_activated)
		self.tagbox = gtk.VBox(False, 0)
		taglisttypes = [TYPE_STRING] * 4
		self.tags_all = gtk.ListStore(*taglisttypes)
		self.tags_allcurrent = gtk.ListStore(*taglisttypes)
		self.tags_currentother = gtk.ListStore(*taglisttypes)
		self.tags_other = gtk.ListStore(*taglisttypes)
		self.tags_allview = FixedTreeView(self.tags_all)
		celltext = gtk.CellRendererText()
		tvc = gtk.TreeViewColumn("ALL", celltext, text=0)
		tvc.add_attribute(celltext, "cell-background", 2)
		tvc.add_attribute(celltext, "foreground", 3)
		self.tags_allview.append_column(tvc)
		self.tags_allcurrentview = FixedTreeView(self.tags_allcurrent)
		celltext = gtk.CellRendererText()
		tvc = gtk.TreeViewColumn("All Current", celltext, text=0)
		tvc.add_attribute(celltext, "cell-background", 2)
		tvc.add_attribute(celltext, "foreground", 3)
		self.tags_allcurrentview.append_column(tvc)
		self.tags_currentotherview = FixedTreeView(self.tags_currentother)
		celltext = gtk.CellRendererText()
		tvc = gtk.TreeViewColumn("Some Current", celltext, text=0)
		tvc.add_attribute(celltext, "cell-background", 2)
		tvc.add_attribute(celltext, "foreground", 3)
		self.tags_currentotherview.append_column(tvc)
		self.tags_otherview = FixedTreeView(self.tags_other)
		for tv in self.tags_allview, self.tags_allcurrentview, \
		          self.tags_currentotherview, self.tags_otherview:
			sel = tv.get_selection()
			sel.set_mode(gtk.SELECTION_MULTIPLE)
			tv.connect("row-activated", self.modify_tag)
		celltext = gtk.CellRendererText()
		tvc = gtk.TreeViewColumn("Some", celltext, text=0)
		tvc.add_attribute(celltext, "cell-background", 2)
		tvc.add_attribute(celltext, "foreground", 3)
		self.tags_otherview.append_column(tvc)
		guidtype = ("text/x-wellpapp-tagguid", 0, 1)
		nametype = ("text/x-wellpapp-tagname", 0, 0)
		posttype = ("text/x-wellpapp-post-id", 0, 0)
		texttypes = [("STRING", 0, 0), ("text/plain", 0, 0)]
		srctypes = texttypes + [guidtype, nametype]
		for widget in self.tags_allview, self.tags_allcurrentview, self.tags_currentotherview, self.tags_otherview:
			widget.drag_source_set(gtk.gdk.BUTTON1_MASK, srctypes, gtk.gdk.ACTION_COPY)
			widget.connect("drag_data_get", self.drag_get_list)
		for widget, all in (self.tags_allview, True), (self.tags_allcurrentview, False):
			widget.drag_dest_set(gtk.DEST_DEFAULT_ALL, [guidtype], gtk.gdk.ACTION_COPY)
			widget.connect("drag_data_received", self.drag_put, all)
		self.thumbview.drag_source_set(gtk.gdk.BUTTON1_MASK, [posttype] + texttypes, gtk.gdk.ACTION_COPY)
		self.thumbview.connect("drag_data_get", self.drag_get_icon)
		self.thumbview.drag_dest_set(gtk.DEST_DEFAULT_ALL, [guidtype, posttype], gtk.gdk.ACTION_COPY)
		self.thumbview.connect("drag_data_received", self.drag_put_thumb)
		self.tagbox.pack_start(self.tags_allview, False, False, 0)
		self.tagbox.pack_start(self.tags_allcurrentview, False, False, 0)
		self.tagbox.pack_start(self.tags_currentotherview, False, False, 0)
		self.tagbox.pack_start(self.tags_otherview, False, False, 0)
		self.mbox = gtk.HPaned()
		self.mbox.set_position(650)
		self.thumbscroll = gtk.ScrolledWindow()
		self.thumbscroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_ALWAYS)
		self.thumbscroll.add(self.thumbview)
		self.tagscroll = gtk.ScrolledWindow()
		self.tagscroll.set_size_request(150, -1)
		self.tagscroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		self.tagscroll.add_with_viewport(self.tagbox)
		self.mbox.pack1(self.thumbscroll, resize=True, shrink=False)
		self.mbox.pack2(self.tagscroll, resize=True, shrink=False)
		self.vbox = gtk.VBox(False, 0)
		self.vbox.pack_start(self.msgbox, False, False, 0)
		self.vbox.pack_start(self.mbox, True, True, 0)
		self.vbox.pack_end(self.bbox, False, False, 0)
		self.tagfield = gtk.Entry()
		self.tagfield.connect("activate", self.apply_action, None)
		self.tagfield.connect("key-press-event", self.tagfield_key)
		self.tagfield.drag_dest_set(gtk.DEST_DEFAULT_ALL, [nametype] + texttypes, gtk.gdk.ACTION_COPY)
		self.tagfield.connect("drag_data_received", self.drag_put_tagfield)
		self.vbox.pack_end(self.tagfield, False, False, 0)
		self.window.add(self.vbox)
		self.window.set_default_size(int(client.cfg.tagwindow_width), int(client.cfg.tagwindow_height))
		self.window.show_all()
		self.b_apply.hide()
		self.type2colour = dict([cs.split("=") for cs in client.cfg.tagcolours.split()])
		self.md5s = []
		self.fullscreen_open = False

	def drag_put_tagfield(self, widget, context, x, y, selection, targetType, eventTime):
		tag = _uni(selection.data) + u" "
		text = _uni(self.tagfield.get_text())
		# This gets called twice (why?), so ignore it if we already have the tag
		if text[-len(tag):] != tag:
			if text and text[-1] != u" ": text += u" "
			text += tag
			self.tagfield.set_text(text)
		# When recieving standard types, we also have to stop the default handler
		context.finish(True, False, eventTime)
		widget.emit_stop_by_name("drag_data_received")

	def drag_put_thumb_guid(self, x, y, selection):
		x += int(self.thumbscroll.get_hadjustment().value)
		y += int(self.thumbscroll.get_vadjustment().value)
		item = self.thumbview.get_item_at_pos(x, y)
		if not item: return
		iter = self.thumbs.get_iter(item[0])
		m = self.thumbs.get_value(iter, 0)
		self._apply([(t, None) for t in selection.data.split()], [], [m])

	def drag_put_thumb_post(self, selection):
		try:
			data = str(selection.data).lower()
		except Exception:
			return
		add = []
		for m in data.split():
			if len(m) == 32 and ishex(m) and m not in self.md5s:
				add.append(m)
				self.md5s.append(m)
		if add:
			fl = FileLoader(self, add)
			fl.start()

	def drag_put_thumb(self, widget, context, x, y, selection, targetType, eventTime):
		if selection.type == "text/x-wellpapp-tagguid":
			self.drag_put_thumb_guid(x, y, selection)
		if selection.type == "text/x-wellpapp-post-id":
			self.drag_put_thumb_post(selection)

	def drag_put(self, widget, context, x, y, selection, targetType, eventTime, all):
		self.apply([(t, None) for t in selection.data.split()], [], all)

	def _drag_get_each(self, model, path, iter, data):
		targetType, l = data
		data = model.get_value(iter, targetType)
		l.append(data)

	def drag_get_list(self, widget, context, selection, targetType, eventTime):
		l = []
		sel = widget.get_selection()
		sel.selected_foreach(self._drag_get_each, (targetType, l))
		# All the examples pass 8, what does it mean?
		selection.set(selection.target, 8, " ".join(l))

	def drag_get_icon(self, widget, context, selection, targetType, eventTime):
		data = ""
		for path in widget.get_selected_items():
			data += self.thumbs[path][0] + " "
		selection.set(selection.target, 8, data[:-1])

	def modify_tag(self, tv, row, *a):
		model = tv.get_model()
		pre = prefix(model[row][0])
		guid = clean(model[row][1])
		tag = client.get_tag(guid)
		dialog, tv = self._make_tag_dialog(u"Modify tag", tag.name, tag.type)
		entry = gtk.Entry()
		entry.set_text(tag.name)
		dialog.vbox.pack_start(entry)
		entry.connect("activate", lambda *a: dialog.response(gtk.RESPONSE_ACCEPT))
		dialog.show_all()
		if dialog.run() == gtk.RESPONSE_ACCEPT:
			ls, iter = tv.get_selection().get_selected()
			new_type = None
			if iter:
				t = ls.get_value(iter, 0)
				if t != tag.type:
					new_type = t
			new_name = _uni(entry.get_text())
			if new_name == tag.name: new_name = None
			if new_type or new_name:
				try:
					client.mod_tag(guid, type=new_type, name=new_name)
					if new_name: model[row][0] = pre + new_name
					model[row][3] = self.tag_colour(guid)
				except Exception:
					pass
		dialog.destroy()

	def tag_colour(self, guid):
		type = client.get_tag(guid)["type"]
		if type in self.type2colour: return self.type2colour[type]
		return "#%02x%02x%02x" % tuple([int(ord(c) / 1.6) for c in md5(type).digest()[:3]])

	def put_in_list(self, lo, li):
		data = []
		for pre, bg in ("", "#ffffff"), ("impl", "#ffd8ee"):
			data += [(prefix(t) + self.ids[clean(t)], t, bg, self.tag_colours[clean(t)]) for t in self.taglist[pre + li]]
		lo.clear()
		map(lambda d: lo.append(d), sorted(data))

	def refresh(self):
		posts = map(lambda m: client.get_post(m, True), self.md5s)
		if None in posts:
			self.error(u"Post(s) not found")
			posts = filter(None, posts)
		if not posts:
			self.error(u"No posts found")
			return
		self.ids = dict(zip(chain(*[map(clean, p["tagguid"] + p["impltagguid"]) for p in posts]),
		                    chain(*[map(clean, p["tagname"] + p["impltagname"]) for p in posts])))
		self.posts = dict([(p["md5"], p) for p in posts])
		agl = self.ids.keys()
		self.tag_colours = dict(zip(agl, [self.tag_colour(clean(tg)) for tg in agl]))
		self.taglist = {}
		self._tagcompute(posts, "")
		self._tagcompute(posts, "impl")
		self.put_in_list(self.tags_all, "all")
		self.update_from_selection()

	def _tagcompute(self, posts, pre):
		self.taglist[pre + "all"] = set(posts[0][pre + "tagguid"])
		self.taglist[pre + "any"] = set(posts[0][pre + "tagguid"])
		for p in posts:
			self.taglist[pre + "all"].intersection_update(p[pre + "tagguid"])
			self.taglist[pre + "any"].update(p[pre + "tagguid"])

	def add_thumbs(self, thumbs):
		for thumb in thumbs:
			self.thumbs.append(thumb)

	def known_tag(self, tag):
		return tag["guid"] in self.ids

	def thumb_selected(self, iconview):
		self.update_from_selection()

	def thumb_activated(self, iconview, path):
		if self.fullscreen_open: return
		try:
			self.fullscreen_open = True
			m = self.thumbs[path][0]
			fn = client.image_path(m)
			self.set_msg(u"Loading image")
			f = FullscreenWindowThread(fn, tw)
			f.start()
		except Exception:
			self.fullscreen_open = False

	def update_from_selection(self):
		self._update_from_selection("")
		self._update_from_selection("impl")
		self.put_in_list(self.tags_allcurrent, "allcurrent")
		self.put_in_list(self.tags_currentother, "currentother")
		self.put_in_list(self.tags_other, "other")

	def _update_from_selection(self, pre):
		common = None
		all = set()
		count = 0
		for path in self.thumbview.get_selected_items():
			m = self.thumbs[path][0]
			post = self.posts[m]
			if common == None:
				common = set(post[pre + "tagguid"])
			else:
				common.intersection_update(post[pre + "tagguid"])
			all.update(post[pre + "tagguid"])
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

	def destroy(self, widget, data=None):
		gtk.main_quit()

	def tagfield_key(self, tagfield, event):
		if event.state & (gtk.gdk.SHIFT_MASK | gtk.gdk.CONTROL_MASK): return
		if gtk.gdk.keyval_name(event.keyval) == "Tab":
			self.set_msg(u"")
			text = _uni(tagfield.get_text())
			pos = tagfield.get_position()
			spos = text.rfind(u" ", 0, pos) + 1
			left = text[:spos]
			word = text[spos:pos]
			right = text[pos:]
			if word:
				new_word, alts = complete(word)
				if len(new_word) > 1:
					if alts:
						self.set_msg(u" ".join(sorted(alts)))
					else:
						if not right or right[0] != u" ":
							new_word += u" "
					text = left + new_word + right
					tagfield.set_text(text)
					tagfield.set_position(pos + len(new_word) - len(word))
			return True

	def _make_tt_tv(self, selname=None):
		selpos = 0
		ls = gtk.ListStore(TYPE_STRING)
		tt = client.metalist(u"tagtypes")
		for pos, t in zip(range(len(tt)), tt):
			ls.append((t,))
			if t == selname: selpos = pos
		tv = gtk.TreeView(ls)
		crt = gtk.CellRendererText()
		tv.append_column(gtk.TreeViewColumn(u"Type", crt, text=0))
		tv.get_selection().select_path((selpos,))
		return tv
	
	def _make_tag_dialog(self, title, tagname, tagtype=None):
		dialog = gtk.Dialog(title, self.window, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
		dialog.set_default_response(gtk.RESPONSE_ACCEPT)
		lab = gtk.Label(tagname)
		dialog.vbox.pack_start(lab)
		tv = self._make_tt_tv(tagtype)
		tv.connect("row-activated", lambda *a: dialog.response(gtk.RESPONSE_ACCEPT))
		dialog.vbox.pack_end(tv)
		dialog.show_all()
		return dialog, tv

	def create_tag(self, name):
		dialog, tv = self._make_tag_dialog(u"Create tag", name)
		if dialog.run() == gtk.RESPONSE_ACCEPT:
			ls, iter = tv.get_selection().get_selected()
			if iter:
				t = ls.get_value(iter, 0)
				client.add_tag(name, t)
		dialog.destroy()

	def apply_action(self, widget, data=None):
		self.set_msg(u"")
		orgtext = _uni(self.tagfield.get_text())
		if not orgtext:
			gtk.main_quit()
			return
		if not self.md5s: return
		good = []
		failed = []
		for t in orgtext.split():
			tag = client.find_tag(clean(t))
			if not tag:
				self.create_tag(clean(t))
				tag = client.find_tag(clean(t))
			if tag:
				good.append((prefix(t) + tag, t))
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
					p = prefix(tag)
					ctag = clean(tag)
					if p == "-" and (ctag in self.posts[m]["tagguid"] or "~" + ctag in self.posts[m]["tagguid"]):
						todo[m][2].append(ctag)
					if p != "-" and tag not in self.posts[m]["tagguid"]:
						if p == "~":
							todo[m][1].append(ctag)
						else:
							assert not p
							todo[m][0].append(ctag)
			except Exception:
				failed.append(t)
		bad = False
		todo_m = filter(lambda m: todo[m] != ([], [], []), todo)
		if todo_m: client.begin_transaction()
		try:
			for m in todo_m:
				full, weak, remove = map(set, todo[m])
				client.tag_post(m, full, weak, remove)
		except:
			bad = True
		finally:
			if todo_m: client.end_transaction()
		self.refresh()
		return bad

	def add_md5s(self, md5s):
		for m in md5s:
			if m not in self.md5s: self.md5s.append(m)
		self.refresh()
		self.b_apply.show()

	def set_msg(self, msg, bg="#FFFFFF"):
		self.msgbox.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse(bg))
		self.msg.set_text(msg)

	def error(self, msg):
		self.set_msg(msg, "#FF4466")

	def main(self):
		self.window.show()
		self.tagfield.grab_focus()
		gtk.main()

# This doesn't actually manage the window, it just loads the image for it.
# Only the main thread ever touches visible objects, because I don't want to
# mess with the locking system (thread_enter etc).
class FullscreenWindowThread(Thread):
	def __init__(self, fn, tw):
		Thread.__init__(self)
		self.name = "FullscreenWindow"
		self._fn = fn
		self._tw = tw

	def run(self):
		try:
			pixbuf = gtk.gdk.pixbuf_new_from_file(self._fn)
			self._win = FullscreenWindow()
			idle_add(self._win._init, self._tw, pixbuf)
			idle_add(self._tw.set_msg, u"")
		except Exception:
			self._cleanup()

	def _cleanup(self, *args):
		self._tw.fullscreen_open = False
		gtk.Window.destroy(self._win, *args)

class FullscreenWindow(gtk.Window):
	def _init(self, tw, pixbuf):
		self._tw = tw
		self.pixbuf = pixbuf
		self.set_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.KEY_PRESS_MASK)
		self.set_title("Fullscreen window")
		self.modify_bg(gtk.STATE_NORMAL, gtk.gdk.Color(0, 0, 0))
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
			scalefactor = min(float(win_w) / self.pix_w,
			                  float(win_h) / self.pix_h)
			self.scale_pixbuf_to_scalefactor(scalefactor)
		else:
			self.image.set_from_pixbuf(self.pixbuf)
			self.show_all()

	def scale_pixbuf_to_scalefactor(self, scalefactor):
		new_w = int(round(self.pix_w * scalefactor))
		new_h = int(round(self.pix_h * scalefactor))
		new_pixbuf = self.pixbuf.scale_simple(new_w, new_h, gtk.gdk.INTERP_HYPER)
		self.image.set_from_pixbuf(new_pixbuf)
		self.show_all()

	def key_press_event(self, spin, event):
		key = gtk.gdk.keyval_name(event.keyval).lower()
		# All normal keys and a few special
		if len(key) == 1 or key in ("escape", "space", "return"):
			self.destroy()

	def destroy(self, *args):
		self._tw.fullscreen_open = False
		gtk.Window.destroy(self)

class FileLoader(Thread):
	def __init__(self, tw, argv):
		Thread.__init__(self)
		self.name = "FileLoader"
		self.daemon = True
		self._tw = tw
		self._argv = argv

	def run(self):
		client = dbclient()
		md5s = map(client.postspec2md5, self._argv)
		good = True
		if None in md5s:
			idle_add(self._tw.error, u"File(s) not found")
			md5s = filter(None, md5s)
			good = False
		else:
			idle_add(self._tw.set_msg, u"Loading thumbs")
		if not md5s:
			idle_add(self._tw.error, u"No posts found")
			return
		idle_add(self._tw.add_md5s, md5s)
		z = int(client.cfg.thumb_sizes.split()[0])
		thumbs = []
		for m in md5s:
			try:
				fn = client.thumb_path(m, z)
				thumb = gtk.gdk.pixbuf_new_from_file(fn)
				thumbs.append((m, thumb,))
			except Exception:
				good = False
		idle_add(self._tw.add_thumbs, thumbs)
		if good: idle_add(self._tw.set_msg, u"")

if __name__ == "__main__":
	if len(argv) < 2:
		print "Usage:", argv[0], "post-spec [post-spec [...]]"
		exit(1)
	client = dbclient()
	tw = TagWindow()
	fl = FileLoader(tw, argv[1:])
	fl.start()
	tw.main()
