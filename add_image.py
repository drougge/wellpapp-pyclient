#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

import sys, md5
from qt import *
import dbclient

client = dbclient.dbclient("book.lundagatan.com", 2225)

THUMBSIZES = (100, 150, 200) # The last is used for display

def img_path(md5):
	return "/db/images/" + md5[0] + "/" + md5[1:3] + "/" + md5
def thumb_path(md5, size):
	return "/db/thumbs/" + str(size) + "/" + md5[0] + "/" + md5[1:3] + "/" + md5

class ImportWindow(QMainWindow):
	def __init__(self, *args):
		QMainWindow.__init__(self, *args)
		self.top        = QWidget(self, "Main")
		self.hlayout    = QHBoxLayout(self.top, 0, 0, "Horiz Layout")
		self.imgLabel   = QLabel("Wait ..", self.top, "Image")
		self.md5Label   = QLabel("md5: ", self.top, "md5")
		self.quitButton = QPushButton("Quit", self.top)
		self.hlayout.addWidget(self.imgLabel)
		self.hlayout.addWidget(self.md5Label)
		self.hlayout.addWidget(self.quitButton)
		self.setCentralWidget(self.top)
		self.quitButton.setFocus()

def mkthumb(img, m, z):
	if img.width() > z or img.height() > z:
		img = img.smoothScale(z, z, QImage.ScaleMin)
	img.save(thumb_path(m, z), "JPEG", 50)
	return img

def determine_filetype(data):
	if data[:3] == "\xff\xd8\xff": return "jpeg"
	if data[:4] == "GIF8": return "gif"
	if data[:4] == "\x89PNG": return "png"
	if data[:2] == "BM": return "bmp"
	if data[:3] == "FWS" or data[:3] == "CWS": return "swf"

def import_image(name):
		imgdata = file(name).read()
		m = md5.new(imgdata).hexdigest()
		win.md5Label.setText("md5: " + m)
		post = client.get_post(m)
		if post:
			win.imgLabel.setText("Already exists")
			return post
		ftype = determine_filetype(imgdata)
		dbname = img_path(m)
		file(dbname, "wb").write(imgdata)
		imgdata = None
		img = QImage(dbname)
		for z in THUMBSIZES:
			thumb = mkthumb(img, m, z)
		thumb = QPixmap(thumb)
		win.imgLabel.setPixmap(thumb)
		client.add_post(md5=m, width=img.width(), height=img.height(), filetype=ftype)
		return client.get_post(m)

app = QApplication(sys.argv)
win = ImportWindow()
app.connect(app, SIGNAL("lastWindowClosed()"), app, SLOT("quit()"))
app.connect(win.quitButton, SIGNAL("clicked()"), app, SLOT("quit()"))
win.show()
app.setOverrideCursor(app.waitCursor)
print import_image("/home/drougge/1093607539792.jpg")
app.restoreOverrideCursor()
app.exec_loop()
