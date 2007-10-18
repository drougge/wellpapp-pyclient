#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

import sys, os, md5
from qt import *
import dbclient

client = dbclient.dbclient("book", 2225)

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

# Surely there is some standard way of getting this (without subclassing)?
class SizedListBox(QListBox):
	def sizeHint(self):
		height = QListBox.sizeHint(self).height()
		width = self.maxItemWidth()
		return QSize(width, height)

class DanbooruWindow(QMainWindow):
	def __init__(self, *args):
		def sizepolicy(obj, *args):
			obj.setSizePolicy(QSizePolicy(*args))
		QMainWindow.__init__(self, *args)
		self.top        = QWidget(self, "Main")
		self.hlayout    = QHBoxLayout(self.top, 0, 0, "hLayout")
		self.fileList   = SizedListBox(self.top, "FileList")
		sizepolicy(self.fileList, QSizePolicy.Preferred, QSizePolicy.Expanding)
		self.hMiddle    = QWidget(self.top, "Horizontal Middle")
		self.tagList    = SizedListBox(self.top, "TagList")
		sizepolicy(self.tagList, QSizePolicy.Preferred, QSizePolicy.Expanding)
		self.hlayout.addWidget(self.fileList)
		self.hlayout.addWidget(self.hMiddle)
		self.hlayout.addWidget(self.tagList)

		self.hMLayout   = QVBoxLayout(self.hMiddle, 0, 0, "Horiz Middle Layout")
		self.quitButton = QPushButton("Quit", self.hMiddle)
		self.imgScroll  = QScrollView(self.hMiddle, "Image scroller")
		self.imgScroll.setResizePolicy(QScrollView.AutoOneFit)
		self.imgLabel   = QLabel("No image", self.hMiddle, "Image")
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
		if self.current_image == name: return
		self.imgLabel.clear()
		self.tagList.clear()
		filename = self.current_dir + os.path.sep + name
		md5 = md5file(filename)
		self.md5Label.setText("md5: " + md5)
		try:
			for tag in client.get_tags(md5)[0]:
				self.tagList.insertItem(tag)
		except:
			self.tagList.clear()
			self.tagList.insertItem("*ERROR*")
		img = QPixmap(filename)
		self.imgLabel.setPixmap(img)

app = QApplication(sys.argv)
win = DanbooruWindow()
for filename in os.listdir("."):
	if is_probably_image(filename):
		win.fileList.insertItem(filename)
win.fileList.sort()
app.connect(app, SIGNAL("lastWindowClosed()"), app, SLOT("quit()"))
app.connect(win.quitButton, SIGNAL("clicked()"), app, SLOT("quit()"))
app.connect(win.fileList, SIGNAL("highlighted(const QString &)"), win.showImage)
win.show()
app.exec_loop()
