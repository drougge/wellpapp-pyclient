#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient

if len(argv) not in (2, 3):
	print "Usage:", argv[0], "tagname [tagtype]"
	exit(1)

client = dbclient()
client.add_tag(*argv[1:])
