from __future__ import print_function

from wellpapp import Client
from os.path import exists, lexists
from os import unlink

def main(arg0, argv):
	if len(argv) < 1:
		print("Usage:", arg0, "[-f] post-spec [post-spec [..]]")
		print("\t-f: Force delete, even if post has tags/rels.")
		return 1

	def rmthumbs(post):
		m = post["md5"]
		sizes = list(map(int, client.cfg.thumb_sizes.split())) + ["normal", "large"]
		for z in sizes:
			if isinstance(z, int):
				path = client.thumb_path(m, z)
			else:
				path = client.pngthumb_path(m, post["ext"], z)
			if exists(path):
				unlink(path)

	def rmimg(m):
		path = client.image_path(m)
		if lexists(path):
			unlink(path)

	def delete_post(m, force):
		post = client.get_post(m, True, ["tagguid", "ext", "implied"])
		if not post:
			print(m, "post not found")
			return 1
		if post.tags:
			if force:
				client.tag_post(m, remove_tags=[t.guid for t in post.settags])
			else:
				print(m, "post has tags")
				return 1
		rels = client.post_rels(m)
		if rels:
			if force:
				client.remove_rels(m, rels)
			else:
				print(m, "post has related posts")
				return 1
		client.delete_post(m)
		rmthumbs(post)
		rmimg(m)
		return 0

	client = Client()
	ret = 0
	force = False
	for ps in argv:
		if ps == '-f':
			force = True
			continue
		m = client.postspec2md5(ps)
		if m:
			ret |= delete_post(m, force)
		else:
			print("Post not found:", ps)
			ret = 1
	return ret
