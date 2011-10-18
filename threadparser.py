#!/usr/bin/python

# Built ins
import datetime
import logging
import re
from pprint import pprint

# OKP lib stuff.
try:
   from okp import REPLY_URL, get_default_time_offset
except ImportError:
   BASE_URL   = "http://board.okayplayer.com/okp.php"
   REPLY_URL  = BASE_URL + "?az=show_topic&forum=%d&topic_id=%d#%d"
   # OKP's time stamps are WAY off, but by a constant amount (I hope)
   get_default_time_offset = lambda: datetime.timedelta(0, 3757)


class Token(object):
   
   # Token type constants
   MESG_ID = 'MESG_ID'
   MESG_TITLE = 'MESG_TITLE'
   MESG_PARENT = 'MESG_PARENT'
   MESG_TEXT = 'MESG_TEXT'
   MESG_DATE = 'MESG_DATE'
   MESG_NUM = 'MESG_NUM'
   AUTHOR_NAME = 'AUTHOR_NAME'
   AUTHOR_AVATAR = 'AUTHOR_AVATAR'
   AUTHOR_ID = 'AUTHOR_ID'
   AUTHOR_CHARTER = 'AUTHOR_CHARTER'
   AUTHOR_NEWBIE = 'AUTHOR_NEWBIE'
   AUTHOR_POSTS = 'AUTHOR_POSTS'
   BREAKER = 'BREAKER'

   tokenizers = {
      MESG_ID : re.compile(r'a name="(\d+)"'),
      MESG_TITLE : re.compile(r'<strong>.*?"(.*?)"</strong>'),
      MESG_NUM : re.compile(r'<strong>(\d+).*?".*?"</strong>'),
      MESG_TEXT : re.compile(r'<p class="dcmessage">(.*?)</p>', re.DOTALL),
      MESG_DATE : re.compile(r'class="dcdate">(.*?)<'),
      MESG_PARENT : re.compile(r'Reply # (\d+)'),
      AUTHOR_AVATAR: re.compile(r'src="(.*?)" height="60"'),
      AUTHOR_CHARTER : re.compile(r'class="dcauthorinfo">(Charter member)<'),
      AUTHOR_NEWBIE : re.compile(r'class="dcauthorinfo">Member since (.*?)<'),
      AUTHOR_POSTS : re.compile(r'class="dcauthorinfo">.*?(\d+) post'),
      AUTHOR_ID : re.compile(r'user_profiles&u_id=(.*?)"\s*?class') ,
      AUTHOR_NAME : re.compile(r'class="dcauthorlink">(.*?)<'),
      BREAKER : re.compile(r'(Printer-friendly copy)'),
   }

   def __init__(self, type, data, position):
      self.type = type
      self.data = data
      self.position = position

   def __str__(self):
      s = ''
      s += 'TYPE: %s\n' % self.type
      s += 'DATA: %s\n' % self.data[:60]
      s += 'POS:  %s\n' % self.position
      return s


class ThreadParser(object):
   
   def __init__(self, html):
      self.html = html
      self.replies = []

      # Do all the dirty work
      self.title = re.search('<strong>\s*"(.*?)"\s*</strong>', self.html).group(1)
      self.forum_id = re.search('forum=(\d+)', self.html).group(1)
      self.topic_id = re.search('topic_id=(\d+)', self.html).group(1)
      self.parse()

      self.get_replies()

      # And reap the benefits
      #self.thread = dict((p.num, p) for p in self.replies) 

   def parse(self):
      """ OKP's HTML is extremely fragile, non-standard, and even inconsistent
      within a single post. You cannot count on every reply in a thread having,
      for instance, a title, author, and post number. The backend software is
      buggy enough to sometimes omit those fields, and the moderation process
      may sometimes wipe out this data as well (posts from a user which has
      since been deleted will have different HTML than a still-active user).

      My strategy here is to parse ALL post-related data from the HTML, along
      with a special marker datum that marks the end of a post. This datum tends
      to be stable even when other data is broken. I can then chunk all of the
      data, using the marker as a boundary, and try to create a post from a
      chunk of data. Where constructing a post object with the data fails, I can
      discard the data and continue. """

      # Grab all the post data
      self.tokens = []
      for type, tokenizer in Token.tokenizers.iteritems():
         for match in re.finditer(tokenizer, self.html):
            self.tokens.append (
               Token (
                  type = type,
                  data = match.group(1),
                  position = match.start()
               )
            )

      # Return to HTML source order, so we can break into posts later
      self.tokens.sort(key = lambda x: x.position)

   def iter_posts(self):
      """ Returns groups of tokens corresponding to posts """

      group = []
      for token in self.tokens:
         if token.type != Token.BREAKER:
            group.append(token)
         elif group:
            yield group
            group = []

   def get_replies(self):
      for post in self.iter_posts():
         try:
            reply = Reply(self.forum_id, self.topic_id)
            reply.consume(post)
            self.replies.append(reply)
         except Exception, e:
            raise e

      self.replies[0].message_num = 0
      self.replies[0].message_parent = -1
   
   def do_post_stats(self):
      max_depth = 20
      for base in self.replies:
         reply = base
         depth = 0
         while reply.parent_num > 0 and depth < max_depth:
            depth += 1
            reply = self.thread[reply.parent_num]
         base.depth = depth

         base.responses = [p for p in self.replies if p.parent_num == base.num]
         base.popularity = len(base.responses)
      

class Reply(object):
   def __init__(self, forum_id, topic_id):
      self.forum_id = forum_id
      self.topic_id = topic_id

      # models.Reply does not require most of these fields to have meaningful
      # values, but Reply.from_parse does assume that they are all defined
      self.message_id = None
      self.message_title = None
      self.message_parent = None
      self.message_text = None
      self.message_date = None
      self.message_num = None
      self.author_name = None
      self.author_avatar = None
      self.author_id = None
      self.author_is_charter = False
      self.author_join_date = False
      self.author_num_posts = 0
      self.url = ''

   def consume(self, post):

      self.message = []

      for token in post:

         if token.type == Token.MESG_ID:
            self.message_id = int(token.data)

         elif token.type == Token.MESG_TITLE:
            self.message_title = token.data

         elif token.type == Token.MESG_PARENT:
            self.message_parent = int(token.data)

         elif token.type == Token.MESG_TEXT:
            self.message.append(token.data)
            
         elif token.type == Token.MESG_DATE:
            self.message_date = datetime.datetime.strptime(token.data[4:], "%b-%d-%y %I:%M %p")
            self.message_date += get_default_time_offset()

         elif token.type == Token.MESG_NUM:
            self.message_num = int(token.data)

         elif token.type == Token.AUTHOR_NAME:
            self.author_name = token.data

         elif token.type == Token.AUTHOR_AVATAR:

            # Moderator (^ok) images might also be caught, but they'll have
            # relative paths
            img = token.data.lower()
            if (img.startswith('http') and img.endswith(('jpg','gif','png'))):
               self.author_avatar = img

         elif token.type == Token.AUTHOR_ID:
            self.author_id = int(token.data)

         elif token.type == Token.AUTHOR_CHARTER:
            self.author_is_charter = True
            self.author_join_date = False
            
         elif token.type == Token.AUTHOR_NEWBIE:
            self.author_join_date = re.sub(r'st|nd|rd|th', '', token.data)
            self.author_join_date = datetime.datetime.strptime(self.author_join_date, '%b %d %Y')
            self.author_is_charter = False

         elif token.type == Token.AUTHOR_POSTS:
            self.author_num_posts = int(token.data)

      self.message_text = ''.join(self.message)

      self.url = REPLY_URL % (int(self.forum_id), 
                                  int(self.topic_id), 
                                  int(self.message_id))

   def __str__(self):
      fields = 'forum_id topic_id message_id message_date message_num '
      fields += 'message_parent message_title message_text '
      fields += 'author_name author_id author_join_date author_num_posts author_is_charter'
      fields = fields.split()

      s = u''
      for field in fields:
         if field in self.__dict__:
            value = self.__dict__[field]
            s += "%-20s: %s\n" % (field, unicode(self.__dict__[field])[:40])
      return s

