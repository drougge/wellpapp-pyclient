from __future__ import print_function

from os import walk, readlink, stat
from os.path import join
from wellpapp.client import Client
from wellpapp.util import identify_raw, RawWrapper, raw_exts
from io import open

def main(arg0, argv):
	if len(argv) < 1 or argv[0][0] == "-":
		print("Usage: " + arg0 + " . or raw or post-spec [post-spec [..]]")
		print("\t.         - Regenerate full cache")
		print("\traw       - Regenerate cache for all raw images")
		print("\tpost-spec - add post-spec to cache")
		print("Run in image_base")
		return 1

	def add(m, fn):
		try:
			dest = readlink(fn)
			s = stat(dest)
			z = s.st_size
			mt = int(s.st_mtime)
			fh = open(dest, "rb")
			if identify_raw(fh):
				fh.seek(0)
				jfh = RawWrapper(fh, True)
				jfh.seek(0, 2)
				jz = jfh.tell()
				jfh.close()
				l = "1 %s %d %d %d %s\n" % (m, z, mt, jz, dest)
			else:
				l = "0 %s %d %d %s\n" % (m, z, mt, dest)
			fh.close()
			res.write(l)
		except Exception:
			print(m, "failed")

	res = open("cache", "a", encoding="utf-8")
	if argv == ["."]:
		for dp, dns, fns in walk("."):
			for n in [n for n in fns if len(n) == 32]:
				add(n, join(dp, n))
	elif argv == ["raw"]:
		client = Client()
		ms = []
		for ext in raw_exts:
			p = client.search_post(guids=[("aaaaaa-aaaacr-faketg-FLekst", ext)])
			ms += [p.md5 for p in p]
		for m in ms:
			add(m, client.image_path(m))
	else:
		client = Client()
		for n in argv:
			m = client.postspec2md5(n)
			if m:
				add(m, client.image_path(m))
			else:
				print("Failed to convert " + n + " to post")
	res.close()
