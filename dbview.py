#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

import sys, os, md5
from qt import *
import dbclient

client = dbclient.dbclient("book.lundagatan.com", 2225)
minImgWidth, minImgHeight = 500, 500

def md5file(filename):
	m = md5.new()
	f = file(filename)
	for data in iter(lambda: f.read(1024 * 128), ''):
		m.update(data)
	return m.hexdigest()

exts = ("jpeg", "jpg", "gif", "png", "bmp")
def is_probably_image(filename):
	if not os.path.isfile(filename): return False
	if filename.split(".")[-1].lower() in exts: return True
	return False

def danbooru_path(md5, ext):
	base = "/home/danbooru/images/" + md5[0] + "/" + md5[1:3] + "/" + md5 + "."
	# A bit of magic because the DB and filesystem don't agree
	for test_ext in (ext, "jpg", "JPEG", "JPG", "GIF", "PNG"):
		filename = base + test_ext
		if os.path.exists(filename): return filename
	return "NO"

# Surely there is some standard way of getting this (without subclassing)?
class SizedListBox(QListBox):
	def sizeHint(self):
		height = QListBox.sizeHint(self).height()
		width = self.maxItemWidth()
		return QSize(width + 4, height)

# Try to get more space for the image with windows that are too small.
# Doesn't work well.
class SizedLabel(QLabel):
	def sizeHint(self):
		sh = QLabel.sizeHint(self)
		height = max(sh.height(), minImgHeight)
		width = max(sh.width(), minImgWidth)
		return QSize(width, height)

class DanbooruWindow(QMainWindow):
	def __init__(self, *args):
		def sizepolicy(obj, *args):
			obj.setSizePolicy(QSizePolicy(*args))
		QMainWindow.__init__(self, *args)
		self.top        = QSplitter(self, "Main")
		self.fileList   = SizedListBox(self.top, "FileList")
		sizepolicy(self.fileList, QSizePolicy.Preferred, QSizePolicy.Expanding)
		self.hMiddle    = QWidget(self.top, "Horizontal Middle")
		self.tagList    = SizedListBox(self.top, "TagList")
		sizepolicy(self.tagList, QSizePolicy.Preferred, QSizePolicy.Expanding)

		self.hMLayout   = QVBoxLayout(self.hMiddle, 0, 0, "Horiz Middle Layout")
		self.quitButton = QPushButton("Quit", self.hMiddle)
		self.imgScroll  = QScrollView(self.hMiddle, "Image scroller")
		self.imgScroll.setResizePolicy(QScrollView.AutoOneFit)
		self.imgLabel   = SizedLabel("No image", self.hMiddle, "Image")
		self.imgScroll.addChild(self.imgLabel)
		self.md5Label   = QLabel("md5: ", self.hMiddle, "md5")
		self.hMLayout.addWidget(self.quitButton)
		self.hMLayout.addWidget(self.imgScroll)
		self.hMLayout.addWidget(self.md5Label)
		self.setCentralWidget(self.top)

		self.current_dir = "."
		self.current_image = None
		self.quitButton.setFocus()

		self.imgLabel.setAlignment(QLabel.AlignCenter)
		sizepolicy(self.imgLabel, QSizePolicy.Expanding, QSizePolicy.Expanding)

	def showImage(self, name):
		name = str(name)
		if self.current_image == name: return
		self.imgLabel.clear()
		self.tagList.clear()
		if self.mode == "files":
			filename = self.current_dir + os.path.sep + name
			md5 = md5file(filename)
			self.md5Label.setText("md5: " + md5)
			try:
				for tag in client.get_post(md5)[0]:
					self.tagList.insertItem(tag)
			except:
				self.tagList.clear()
				self.tagList.insertItem("*ERROR*")
		else:
			post = self.search[name]
			filename = danbooru_path(name, post["ext"])
			self.md5Label.setText("md5: " + name)
			for tag in post["tagname"]:
				self.tagList.insertItem(tag)
		if file(filename).read(6) == "GIF89a":
			mov = QMovie(filename)
			self.imgLabel.setMovie(mov)
		else:
			img = QPixmap(filename)
			self.imgLabel.setPixmap(img)

app = QApplication(sys.argv)
win = DanbooruWindow()
tags = sys.argv[1:]
if tags:
	win.mode = "search"
	win.search = client.search_post(wanted=("tagname", "ext"), tags=tags)
	for md5 in win.search.keys():
		win.fileList.insertItem(md5)
else:
	win.mode = "files"
	for filename in os.listdir("."):
		if is_probably_image(filename):
			win.fileList.insertItem(filename)
win.fileList.sort()
app.connect(app, SIGNAL("lastWindowClosed()"), app, SLOT("quit()"))
app.connect(win.quitButton, SIGNAL("clicked()"), app, SLOT("quit()"))
app.connect(win.fileList, SIGNAL("highlighted(const QString &)"), win.showImage)
win.show()
app.exec_loop()
