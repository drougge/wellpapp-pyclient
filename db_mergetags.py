#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient

if len(argv) != 3:
	print "Usage:", argv[0], "into-tag from-tag"
	exit(1)

client = dbclient()
into_t, from_t = map(client.find_tag, argv[1:])
if not into_t or not from_t:
	print "Tag not found"
	exit(1)
client.merge_tags(into_t, from_t)
