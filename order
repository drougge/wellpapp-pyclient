#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from wellpapp import Client
from re import match
from time import strftime, localtime
from os.path import exists
from hashlib import md5
from os import readlink

if len(argv) < 3:
	print "Usage:", argv[0], "tagname post-spec [post-spec [...]]"
	exit(1)

client = Client()
data = {}
tag = client.find_tag(argv[1], data)
if not tag:
	print "Tag not found"
	exit(1)
if data["weak_posts"]:
	print "Can't order a tag with weak posts"
	exit(1)
posts = map(client.postspec2md5, argv[2:])
wtag = "~" + tag
for post, spec in zip(posts, argv[2:]):
	if post == None:
		print "Post " + spec + " not found"
		exit(1)
	post = client.get_post(post, True)
	if tag in post["impltagguid"] or wtag in post["impltagguid"]:
		print "Post " + spec + " has tag implied."
		print "Can't order a tag with implied posts."
		exit(1)
	if tag not in post["tagguid"]:
		print "Post " + spec + " doesn't have tag."
		exit(1)
client.order(tag, posts)
