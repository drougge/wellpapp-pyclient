#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient

if len(argv) < 3:
	print "Usage:", argv[0], "post-spec tag [tag [...]]"
	print "or:", argv[0], "-r tag post-spec [post-spec [...]]"
	exit(1)

def set_tag(full, weak, remove, tag):
	tag = client.parse_tag(tag)
	if not tag: return
	tag, val = tag
	s = full
	if tag[0] == "-":
		s = remove
		tag = tag[1:]
	elif tag[0] == "~":
		s = weak
		tag = tag[1:]
	s.add((tag, val))
	return True

client = dbclient()
full = set()
weak = set()
remove = set()
if argv[1] == "-r":
	if not set_tag(full, weak, remove, argv[2]):
		print "Tag not found"
		exit(1)
	client.begin_transaction()
	for post in argv[3:]:
		md5 = client.postspec2md5(post)
		if not md5 or not client.get_post(md5):
			print post, "not found"
			continue
		try:
			client.tag_post(md5, full, weak, remove)
		except Exception:
			print "Failed to set on", post
	client.end_transaction()
else:
	md5 = client.postspec2md5(argv[1])
	if not md5 or not client.get_post(md5):
		print "Post not found"
		exit(1)
	for tag in argv[2:]:
		if not set_tag(full, weak, remove, tag):
			print "Unknown tag " + tag
	if full or weak or remove:
		client.tag_post(md5, full, weak, remove)
