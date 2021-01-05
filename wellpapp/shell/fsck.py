from __future__ import print_function

from hashlib import md5
from PIL import Image
from os.path import exists
from os import stat, walk
from sys import version_info, exit
from wellpapp import Client

if version_info[0] > 2:
	basestring = str

def main(arg0, argv):
	def usage():
		print("Usage:", arg0, "-opts")
		print("Where opts can be:")
		print("\t-t Check thumb existance")
		print("\t-T Check thumb integrity (decodeability and timestamp)")
		print("\t-i Check image existance")
		print("\t-I Check image integrity (md5)")
		print("\t-f Check that all existing symlinks/thumbnails have a corresponding post")
		print("\t-s Check that all posts have the same tags they are findable by.")
		print("\t-a All of the above")
		exit(1)

	optchars = "tTiIfs"
	opts = ""
	for a in argv:
		if a[0] != "-": usage()
		for c in a[1:]:
			if c in optchars and c not in opts:
				opts += c
			elif c == "a":
				opts = optchars
			else:
				usage()
	if not opts: usage()

	def check_images(integrity):
		print("Checking images")
		bad = set()
		for m in posts:
			path = client.image_path(m)
			if not exists(path):
				print("Missing image", m)
				bad.add(m)
				continue
			if integrity:
				if md5(open(path, "rb").read()).hexdigest() != m:
					print("Bad file", m)
					bad.add(m)
		return bad

	def check_thumbs(integrity):
		print("Checking thumbs")
		sizes = list(map(int, client.cfg.thumb_sizes.split())) + ["normal", "large"]
		bad = set()
		for m in posts:
			thumbs = []
			for z in sizes:
				if isinstance(z, int):
					path = client.thumb_path(m, z)
				else:
					path = client.pngthumb_path(m, posts[m]["ext"], z)
				thumbs.append((path, z))
			for path, z in thumbs:
				if not exists(path):
					print(m, "missing thumb", z)
					bad.add(m)
			if integrity and m not in bad:
				for path, z in thumbs:
					img = Image.open(path)
					try:
						# img.verify() doesn't work on jpeg
						# (and load() is pretty forgiving too, but that's
						#  probably a problem with the format.)
						img.load()
					except Exception:
						print(m, "bad thumb", z)
						bad.add(m)
						continue
					if isinstance(z, basestring):
						if "Thumb::URI" not in img.info or "Thumb::MTime" not in img.info:
							print(m, "bad thumb", z)
							bad.add(m)
							continue
						t_mtime = int(img.info["Thumb::MTime"])
						f_mtime = int(stat(client.image_path(m)).st_mtime)
						if t_mtime != f_mtime:
							print(m, "outdated thumb", z)
							bad.add(m)
							continue
		return bad

	def _check_imagestore(msg, bad, dp, fns, name2md5):
		initial = dp[-4] + dp[-2:]
		for fn in fns:
			p = dp + "/" + fn
			if fn[:3] != initial:
				print("Misplaced", msg, p)
				bad.add(p)
				continue
			if name2md5(p)[-32:] not in posts:
				print(msg.title(), "without post", fn)
				bad.add(p)

	def _pngthumb2md5(fn):
		img = Image.open(fn)
		return img.info["Thumb::URI"][:32]

	def check_imagestore():
		bad = set()
		print("Checking for stray images")
		for dp, dns, fns in walk(client.cfg.image_base):
			_check_imagestore("image", bad, dp, fns, str)
		print("Checking for stray thumbnails")
		jpegz = client.cfg.thumb_sizes.split()
		for z, name2md5 in zip(jpegz + ["normal", "large"], [str] * len(jpegz) + [_pngthumb2md5] * 2):
			print("  " + z)
			for dp, dns, fns in walk(client.cfg.thumb_base + "/" + z):
				_check_imagestore("thumb", bad, dp, fns, name2md5)
		return bad

	def check_connectivity():
		print("Checking tags")
		for t in tags:
			strong = client.search_post(guids=["!" + t.guid])
			weak = client.search_post(guids=["~" + t.guid])
			if len(strong) != t.posts or len(weak) != t.weak_posts:
				print("Post count mismatch on", t.guid)
				print("\tclaims", t.posts, "+", t.weak_posts)
				print("\tfinds", len(strong), "+", len(weak))
			for res, prefix in ((strong, ""), (weak, "~")):
				for p in res:
					p = posts[p.md5]
					if prefix + t.guid not in p.tags.guids:
						print(p["md5"], "reachable with", t.guid, "but not tagged")
		print("Checking posts")
		for m, p in posts.items():
			guids = ["!" + t.guid for t in p.fulltags] + ["~" + t.guid for t in p.weaktags]
			while guids:
				p = client.search_post(guids=guids[:16])
				if m not in map(lambda f: f["md5"], p):
					print("Post", m, "not findable with all tags")
				guids = guids[16:]

	client = Client()
	posts = client._search_post("SPFtagguid Fimplied Fext", ["tagguid", "datatags", "implied", "ext"])
	print(len(posts), "posts")
	posts = dict(map(lambda f: (f["md5"], f), posts))
	tags = client.find_tags("EAI", "")
	print(len(tags), "tags")
	bad_images = None
	bad_thumbs = None
	stray = None
	connectivity = None
	optlow = opts.lower()
	if "i" in optlow: bad_images = check_images("I" in opts)
	if "t" in optlow: bad_thumbs = check_thumbs("T" in opts)
	if "f" in opts: stray = check_imagestore()
	if "s" in opts: connectivity = check_connectivity()

if __name__ == '__main__':
	from sys import argv
	main(argv[0], argv[1:])
