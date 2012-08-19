#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from sys import argv, exit
from dbclient import dbclient
from optparse import OptionParser

p = OptionParser(usage="Usage: %prog [options] tagname [tagtype]")
p.add_option("-v", "--valuetype", help="Valuetype of tag")
opts, args = p.parse_args()

if len(args) not in (1, 2):
	p.print_help()
	exit(1)

client = dbclient()
client.add_tag(*args, **opts.__dict__)
