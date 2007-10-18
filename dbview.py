#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

import sys, os, md5
from qt import *

def md5file(filename):
	m = md5.new()
	f = file(filename)
	for data in iter(lambda: f.read(1024 * 128), ''):
		m.update(data)
	return m.hexdigest()

class DanbooruWindow(QMainWindow):
	def __init__(self, *args):
		QMainWindow.__init__(self, *args)
		self.top        = QWidget(self, "Main")
		self.hlayout    = QHBoxLayout(self.top, 0, 0, "hLayout")
		self.fileList   = QListBox(self.top, "FileList")
		self.hMiddle    = QWidget(self.top, "Horizontal Middle")
		self.tagList    = QListBox(self.top, "TagList")
		self.hlayout.addWidget(self.fileList)
		self.hlayout.addWidget(self.hMiddle)
		self.hlayout.addWidget(self.tagList)

		self.hMLayout   = QVBoxLayout(self.hMiddle, 0, 0, "Horiz Middle Layout")
		self.quitButton = QPushButton("Quit", self.hMiddle)
		self.imgLabel   = QLabel("No image", self.hMiddle, "Image")
		self.md5Label   = QLabel("md5: ", self.hMiddle, "md5")
		self.hMLayout.addWidget(self.quitButton)
		self.hMLayout.addWidget(self.imgLabel)
		self.hMLayout.addWidget(self.md5Label)
		self.setCentralWidget(self.top)

		self.current_dir = "/home/drougge"
		self.current_image = None
		self.quitButton.setFocus()

	def showImage(self, name):
		print "ohh:", name
		if self.current_image == name: return
		filename = self.current_dir + os.path.sep + name
		self.md5Label.setText("md5: " + md5file(filename))
		img = QPixmap(filename)
		self.imgLabel.setPixmap(img)

app = QApplication(sys.argv)
win = DanbooruWindow()
for img in ["1093607539792.jpg", "1093607692688.jpg", "1093603071292.jpg", "1093575914759.jpg"]:
	win.fileList.insertItem(img)
app.connect(app, SIGNAL("lastWindowClosed()"), app, SLOT("quit()"))
app.connect(win.quitButton, SIGNAL("clicked()"), app, SLOT("quit()"))
app.connect(win.fileList, SIGNAL("highlighted(const QString &)"), win.showImage)
win.show()
app.exec_loop()
