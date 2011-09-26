#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient
from os.path import exists, lexists
from os import unlink

def rmthumbs(post):
	m = post["md5"]
	sizes = map(int, client.cfg.thumb_sizes.split()) + ["normal", "large"]
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
	post = client.get_post(m, True, ["tagguid", "ext"])
	if not post:
		print m, "post not found"
		return 1
	tags = post["tagguid"]
	if tags:
		if force:
			client.tag_post(m, remove_tags=[t[-27:] for t in tags])
		else:
			print m, "post has tags"
			return 1
	rels = client.post_rels(m)
	if rels:
		if force:
			client.remove_rels(m, rels)
		else:
			print m, "post has related posts"
			return 1
	client.delete_post(m)
	rmthumbs(post)
	rmimg(m)
	return 0

if __name__ == "__main__":
	if len(argv) < 2:
		print "Usage:", argv[0], "[-f] post-spec [post-spec [..]]"
		print "\t-f: Force delete, even if post has tags/rels."
		exit(1)
	client = dbclient()
	ret = 0
	force = False
	for ps in argv[1:]:
		if ps == '-f':
			force = True
			continue
		m = client.postspec2md5(ps)
		if m:
			ret |= delete_post(m, force)
		else:
			print "Post not found:", ps
			ret = 1
	exit(ret)
