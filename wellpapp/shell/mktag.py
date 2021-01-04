from __future__ import print_function

from wellpapp import Client
from optparse import OptionParser

def main(arg0, argv):
	p = OptionParser(usage="Usage: %prog [options] tagname [tagtype]", prog=arg0)
	p.add_option("-v", "--valuetype", help="Valuetype of tag")
	opts, args = p.parse_args(argv)

	if len(args) not in (1, 2):
		p.print_help()
		return 1

	client = Client()
	client.add_tag(*args, **opts.__dict__)
