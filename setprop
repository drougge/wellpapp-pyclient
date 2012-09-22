#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from wellpapp import Client

if len(argv) < 3:
	print "Usage:", argv[0], "post-spec property=value [property=value [...]]"
	print "or:", argv[0], "-r property=value post-spec [post-spec [...]]"
	print "Properties as specified in decimal format where possible."
	print "(So width=42, not width=2a)"
	exit(1)

def set_prop(props, spec):
	prop, val = spec.split("=", 1)
	props[prop] = val

client = Client()
props = {}
if argv[1] == "-r":
	set_prop(props, argv[2])
	client.begin_transaction()
	for post in argv[3:]:
		md5 = client.postspec2md5(post)
		if not md5 or not client.get_post(md5):
			print post, "not found"
			continue
		try:
			client.modify_post(md5, **props)
		except Exception:
			print "Failed to set on", post
	client.end_transaction()
else:
	md5 = client.postspec2md5(argv[1])
	if not md5 or not client.get_post(md5):
		print "Post not found"
		exit(1)
	for prop in argv[2:]:
		set_prop(props, prop)
	if props:
		client.modify_post(md5, **props)
