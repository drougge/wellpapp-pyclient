from __future__ import print_function

from sys import exit
from wellpapp import Client, InheritValue, vtparse
from optparse import OptionParser

def main(arg0, argv):
	p = OptionParser(usage="Usage: %prog [options] set_tag implied_tag [priority]", prog=arg0)
	p.add_option("-d", "--delete", help="Delete implication", action="store_true")
	p.add_option("-p", "--priority", help="Priority of implication", type="int")
	p.add_option("-n", "--negative", help="Negative implication", action="store_true")
	p.add_option("-f", "--filter", help="Filter on set_tag value")
	p.add_option("-v", "--value", help="Value of implied tag. '' means inherit.")
	opts, args = p.parse_args(argv)

	def usage():
		p.print_help()
		exit(1)

	if len(args) not in (2, 3):
		usage()

	client = Client()
	set_tag = client.find_tag(args[0])
	implied_tag = client.find_tag(args[1])
	if len(args) == 3:
		try:
			priority = int(args[2])
			assert opts.priority is None
		except Exception:
			usage()
	else:
		priority = opts.priority or 0

	if set_tag and implied_tag:
		if opts.negative:
			implied_tag = "-" + implied_tag
		if opts.filter:
			filter = opts.filter
			if len(filter) > 1 and filter[1] in "=~":
				comp = filter[:2]
				filter = filter[2:]
			else:
				comp = filter[0]
				filter = filter[1:]
			if comp not in ("=", "<", ">", "<=", ">=", "=~"):
				print("Unknown filter comparison")
				exit(1)
			tag = client.get_tag(set_tag)
			if not tag.valuetype:
				print("Set tag does not take a value")
				exit(1)
			filter = (comp, vtparse(tag.valuetype, filter, True))
		else:
			filter = None
		if opts.value is None:
			value = None
		else:
			if opts.value:
				if opts.delete:
					print("Don't specify value when deleting")
					exit(1)
				tag = client.get_tag(implied_tag)
				if not tag.valuetype:
					print("Implied tag does not take a value")
					exit(1)
				value = vtparse(tag.valuetype, opts.value, True)
			else:
				value = InheritValue
		if opts.delete:
			client.remove_implies(set_tag, implied_tag, filter)
		else:
			client.add_implies(set_tag, implied_tag, priority, filter, value)
	else:
		print("Not found")
