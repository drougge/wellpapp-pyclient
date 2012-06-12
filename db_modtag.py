#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient

a = {}
if len(argv) == 4:
	a["type"] = argv[3]
elif len(argv) != 3:
	print "Usage:", argv[0], "tag new_name [new_type]"
	exit(1)

client = dbclient()
tag = client.find_tag(argv[1])
a["name"] = argv[2]
if not tag:
	print "Tag not found"
	exit(1)
client.mod_tag(tag, **a)
