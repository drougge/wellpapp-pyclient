#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient

if len(argv) not in (3, 4):
	print "Usage:", argv[0], "set_tag implied_tag [priority]"
	exit(1)

client = dbclient()
set_tag = client.find_tag(argv[1])
implied_tag = client.find_tag(argv[2], with_prefix=True)
priority = 0
if len(argv) == 4: priority = int(argv[3])
if set_tag and implied_tag:
	client.add_implies(set_tag, implied_tag, priority)
else:
	print "Not found"
