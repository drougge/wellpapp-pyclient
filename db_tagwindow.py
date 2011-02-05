#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient
from itertools import chain
import pygtk
pygtk.require("2.0")
import gtk, gobject
from os.path import commonprefix

def clean(n):
	if n[0] in "-~": return n[1:]
	return n
def prefix(n):
	if n[0] in "-~": return n[0]
	return ""

def complete(word):
	assert u" " not in word
	tags = client.find_tags("EI", word).values()
	if len(tags) == 1: return tags[0]["name"], True
	tags = client.find_tags("EAI", word).values()
	if len(tags) == 1: return tags.values()[0]["alias"][0], True
	names = [t["name"] for t in tags]
	aliases = [t["alias"] if "alias" in t else [] for t in tags]
	candidates = names + list(chain(*aliases))
	return commonprefix(candidates), False

class TagWindow:
	def __init__(self):
		self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
		self.window.set_border_width(2)
		self.window.connect("destroy", self.destroy)
		self.bbox = gtk.HBox(False, 0)
		self.b_apply = gtk.Button(u"_Apply")
		self.b_apply.connect("clicked", self.apply, None)
		self.b_quit = gtk.Button(u"_Quit")
		self.b_quit.connect("clicked", self.destroy, None)
		self.bbox.pack_start(self.b_apply, True, True, 0)
		self.bbox.pack_end(self.b_quit, False, False, 0)
		self.msg = gtk.Label(u"")
		self.msgbox = gtk.EventBox()
		self.msgbox.add(self.msg)
		self.thumbs = gtk.ListStore(gobject.TYPE_STRING, gtk.gdk.Pixbuf)
		self.thumbview = gtk.IconView(self.thumbs)
		self.thumbview.set_pixbuf_column(1)
		self.thumbview.connect("item-activated", self.thumb_clicked)
		self.tagbox = gtk.VBox(False, 0)
		self.tags_all = gtk.ListStore(gobject.TYPE_STRING)
		self.tags_current = gtk.ListStore(gobject.TYPE_STRING)
		celltext = gtk.CellRendererText()
		self.tags_allview = gtk.TreeView(self.tags_all)
		self.tags_allview.append_column(gtk.TreeViewColumn("ALL", celltext, text=0))
		self.tags_currentview = gtk.TreeView(self.tags_current)
		self.tags_currentview.append_column(gtk.TreeViewColumn("Current", celltext, text=0))
		self.tagbox.pack_start(self.tags_allview, False, False, 0)
		self.tagbox.pack_start(gtk.HSeparator(), False, False, 0)
		self.tagbox.pack_start(self.tags_currentview, False, False, 0)
		self.mbox = gtk.HBox(False, 0)
		self.scroll = gtk.ScrolledWindow()
		self.scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_ALWAYS)
		self.scroll.add(self.thumbview)
		self.mbox.pack_start(self.scroll, True, True, 0)
		self.mbox.pack_end(self.tagbox, False, False, 0)
		self.vbox = gtk.VBox(False, 0)
		self.vbox.pack_start(self.msgbox, False, False, 0)
		self.vbox.pack_start(self.mbox, True, True, 0)
		self.vbox.pack_end(self.bbox, False, False, 0)
		self.tagfield = gtk.Entry()
		self.tagfield.connect("activate", self.apply)
		self.tagfield.connect("key-press-event", self.tagfield_key)
		self.vbox.pack_end(self.tagfield, False, False, 0)
		self.window.add(self.vbox)
		self.window.set_default_size(840, 600)
		self.window.show_all()

	def put_in_list(self, lo, li):
		names = sorted([prefix(t) + self.ids[clean(t)] for t in li])
		lo.clear()
		map(lambda n: lo.append((n,)), names)

	def refresh(self):
		posts = map(lambda m: client.get_post(m, True), self.md5s)
		if None in posts:
			self.error(u"Post(s) not found")
			posts = filter(None, posts)
		self.ids = dict(zip(chain(*[map(clean, p["tagguid"] + p["impltagguid"]) for p in posts]),
		                    chain(*[map(clean, p["tagname"] + p["impltagname"]) for p in posts])))
		self.thumbs.clear()
		for p in posts:
			fn = client.pngthumb_path(p["md5"], p["ext"], "normal")
			thumb = gtk.gdk.pixbuf_new_from_file(fn)
			self.thumbs.append((p["md5"], thumb,))
		self.posts = dict([(p["md5"], p) for p in posts])
		self.all_tags = set(posts[0]["tagguid"])
		for p in posts:
			self.all_tags.intersection_update(p["tagguid"])
		self.put_in_list(self.tags_all, self.all_tags)

	def thumb_clicked(self, iconview, path):
		m = self.thumbs[path][0]
		post = self.posts[m]
		unique = set(post["tagguid"]).difference(self.all_tags)
		self.put_in_list(self.tags_current, unique)

	def destroy(self, widget, data=None):
		gtk.main_quit()

	def tagfield_key(self, tagfield, event):
		if event.state: return
		if event.keyval == 65289: # tab
			text = tagfield.get_text()
			pos = tagfield.get_position()
			spos = text.rfind(" ", 0, pos) + 1
			left = text[:spos]
			word = text[spos:pos]
			right = text[pos:]
			if word:
				new_word, full = complete(word)
				if new_word:
					if full:
						if not right or right[0] != " ":
							new_word += " "
					text = left + new_word + right
					tagfield.set_text(text)
					tagfield.set_position(pos + len(new_word) - len(word))
			return True

	def apply(self, widget, data=None):
		orgtext = self.tagfield.get_text()
		if not orgtext:
			gtk.main_quit()
			return
		good = []
		failed = []
		for t in orgtext.split():
			tag = client.find_tag(clean(t))
			if tag:
				good.append((prefix(t) + tag, t))
			else:
				failed.append(t)
		todo = {}
		for tag, t in good:
			try:
				for m in self.posts:
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
		self.tagfield.set_text(u" ".join(failed))
		todo_m = filter(lambda m: todo[m] != ([], [], []), todo)
		if todo_m: client.begin_transaction()
		try:
			for m in todo_m:
				client.tag_post(m, *todo[m])
		except:
			self.tagfield.set_text(orgtext)
		finally:
			if todo_m: client.end_transaction()
		self.refresh()

	def error(self, msg):
		self.b_apply.hide()
		self.msgbox.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("#FF4466"))
		self.msg.set_text(msg)

	def main(self, md5s):
		self.window.show()
		self.tagfield.grab_focus()
		self.md5s = md5s
		self.refresh()
		gtk.main()

if __name__ == "__main__":
	if len(argv) < 2:
		print "Usage:", argv[0], "post-spec [post-spec [...]]"
		exit(1)
	client = dbclient()
	md5s = map(client.postspec2md5, argv[1:])
	tw = TagWindow()
	if None in md5s:
		tw.error(u"File(s) not found")
		md5s = filter(None, md5s)
	tw.main(md5s)
