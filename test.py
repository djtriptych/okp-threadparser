import pprint
import threadparser

# Grab the HTML of an OKP post.
html = open('post.html').read()

# And parse the post (relatively quickly!)
TP = threadparser.ThreadParser(html)

# Then you can play with the replies in the post....
# For instance, this will show the data parsed from the 4th reply in the post.
reply = TP.replies[3]
pprint.pprint(reply.__dict__)

# have fun...
