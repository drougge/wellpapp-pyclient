#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from wellpapp import Client

if len(argv) != 2:
	print "Usage:", argv[0], "alias"
	exit(1)

client = Client()
client.remove_alias(argv[1])
