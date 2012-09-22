#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from wellpapp import Client

if len(argv) != 3:
	print "Usage:", argv[0], "tagname alias"
	exit(1)

client = Client()
tag = client.find_tag(argv[1])
if tag:
	client.add_alias(argv[2], tag)
else:
	print "No such tag", argv[1]
