from __future__ import print_function

from os.path import lexists, realpath
from os import unlink, rename, symlink, stat
from optparse import OptionParser
from hashlib import md5
from PIL import Image, PngImagePlugin
from wellpapp import Client, make_pdirs

def main(arg0, argv):
	p = OptionParser(usage="Usage: %prog [-t] post-spec new-file", prog=arg0)
	p.add_option("-t", "--regenerate-thumbs",
	             action="store_true",
	             help="Regenerate thumbnails from new-file"
	            )
	opts, args = p.parse_args(argv)
	if len(args) != 2:
		p.print_help()
		return 1

	client = Client()

	oldfile, newfile = args
	m = client.postspec2md5(oldfile)
	post = client.get_post(m, wanted=(["ext", "rotate"]))
	if not post:
		print("Post not found")
		return 1
	data = open(newfile, "rb").read()
	newm = md5(data).hexdigest()
	mtime = stat(newfile).st_mtime
	if client.get_post(newm, wanted=()):
		print("New file already has post")
		return 1
	path = client.image_path(newm)
	if lexists(path):
		unlink(path)
	make_pdirs(path)
	symlink(realpath(newfile), path)
	if opts.regenerate_thumbs:
#		@@ assumes same ext
		client.save_thumbs(newm, None, post.ext, post.rotate, True)
	else:
		meta = PngImagePlugin.PngInfo()
		meta.add_text("Thumb::URI", str(newm + "." + post.ext), 0)
		meta.add_text("Thumb::MTime", str(int(mtime)), 0)
	sizes = list(map(int, client.cfg.thumb_sizes.split())) + ["normal", "large"]
	for z in sizes:
		if isinstance(z, int):
			oldpath = client.thumb_path(m, z)
			if opts.regenerate_thumbs:
				unlink(oldpath)
			else:
				newpath = client.thumb_path(newm, z)
				make_pdirs(newpath)
				rename(oldpath, newpath)
		else:
			oldpath = client.pngthumb_path(m, post.ext, z)
			if opts.regenerate_thumbs:
				unlink(oldpath)
			else:
				t = Image.open(oldpath)
				t.load()
				newpath = client.pngthumb_path(newm, post.ext, z)
				make_pdirs(newpath)
				t.save(newpath, format="PNG", pnginfo=meta)
	client.modify_post(m, MD5=newm)
	path = client.image_path(m)
	if lexists(path):
		unlink(path)
