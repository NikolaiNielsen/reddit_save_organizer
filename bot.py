import praw
import config
import sqlite3
import re
import pprint as pp


categories = {"python": "python,learnprogramming,dailyprogrammer,learnpython",
			  "asoiaf": "asoiaf",
			  "entertainment": "anime,games,gamedeals,lowendgamer,patientgamers,fallout",
			  "life stuff": "getdisciplined,lifeprotips,anxiety,meditation"}

subname = "slowboardtest"

def bot_login():
	# We log into reddit
	r = praw.Reddit(username = config.username,
				password = config.password,
				client_id = config.client_id,
				client_secret = config.client_secret,
				user_agent = config.user_agent)
	print('logged in!')

	# and fetch the user
	me = r.user.me()
	return r,me


def init_DB():
	# We open the database (and create the table, if it's not already there)
	conn = sqlite3.connect('redditSaves.db')
	cursor = conn.cursor()

	# Try to create the table
	try:

		cursor.execute("""CREATE TABLE saves
						  (id text, title text, link text, url text,
						  comments integer, subreddit text)""")
		cursor.execute("""CREATE TABLE categories
						  (title text, subreddits text)""")
		cursor.execute("""CREATE TABLE current_post
						  (id text, title text)""")

		# populate the categories table
		cat_to_db = [(k,v) for k,v in categories.items()]
		cursor.executemany("""INSERT INTO categories VALUES (?,?)""", cat_to_db)
		conn.commit()

		# print("Tables created")
	# nothing if it's already there
	except sqlite3.OperationalError:
		# print("Tables already created")
		pass

	print("Database initialized")
	return conn,cursor


def get_old_ids(conn,cursor):
	# Get the old saved ids
	cursor.execute("SELECT id FROM saves")

	# fetchall() returns a list of tuples, each with a string and NULL object
	# We use a list comprehension to make a new list, which only has the
	# string (first element) from each tuple.
	return [i[0] for i in cursor.fetchall()]


def get_new_saves(me,old,conn,cursor,lim = 25):
	# Get x number of saved items. Check which ones are comments and which
	# and which are submissions. If submission isn't in DB, put it in there

	# Temporary list of items to put into database
	toDatabase = []

	# Get the saves and loop over them
	saves = me.saved(limit=lim)
	for i in saves:
		# We get the name of the class
		postType = i.__class__.__name__.lower()

		# if it's a submission we proceed
		if postType == "submission":
			# We check if the post is already in the DB
			Id = i.id
			if Id in old:
				# print('This post is already in the DB! ' + Id)
				continue
			else:
				# What we need (in order)
				# - post id (id)
				# - post title (title)
				# - link to the post (shortlink)
				# - link to the "link" (url)
				# - number of comments (num_comments)
				# - Subreddit (subreddit)
				# print('It\'s a submission, id = ' + Id)
				if i.is_self:
					toDatabase.append((Id,i.title,i.shortlink,i.shortlink,
						i.num_comments,i.subreddit.display_name))
				else:
					toDatabase.append((Id,i.title,i.shortlink,i.url,
						i.num_comments,i.subreddit.display_name))

		# if it's a comment we don't
		elif postType == "comment":
			# print('It\'s a comment')
			continue
		# if it's something else, I wanna know.
		else:
			print('It\'s something else: ' + postType)
			continue

	# After the loop has run, we commit the new saved submissions to the database
	cursor.executemany("""INSERT INTO saves VALUES (?,?,?,?,?,?)""", toDatabase)
	conn.commit()
	print("{} posts committed to table 'saves'".format(len(toDatabase)))


def check_post(r,me,conn,cursor):
	# We get the current post
	cursor.execute("SELECT * FROM current_post")
	data = cursor.fetchall()
	post_id = data[0][0]
	post_title = data[0][1]

	sub = r.submission(id = post_id)
	if sub.archived:
		new_id = create_post(r,me,post_title)
		edit_post(r,me,conn,cursor,new_id)
	else:
		edit_post(r,me,conn,cursor,post_id)


# Actually, this might not be needed anyway. I can just keep a running tally
# in the database, and just edit the submission from there
def read_post(r,me,conn,cursor):

	cursor.execute("SELECT * FROM current_post")
	data = cursor.fetchall()
	post_id = data[0][0]
	post_title = data[0][1]

	p = r.submission(id = post)
	text = p.selftext

	# This regex searches for a new line charactor, followed by 3 times (some amount of
	# words and spaces and a vertical bar) and lastly two newline characters.
	re_last_row = re.compile(r"""(\n[A-Za-z0-9 '"]*\|[A-Za-z0-9 ]*\|[A-Za-z0-9 ]*)(\n)(\n)""")
	last_rows = re_last_row.findall(text)

	# This regex searches for the titles of the table.
	re_title = re.compile(r"""#([A-Za-z0-9 '"]*)\n""")
	titles = re_title.findall(text)

	return text,titles,last_rows

def create_post(r,me,title):
	# Just creates the new self post and returns the ID.
	subreddit = r.subreddit(subname)
	submission = subreddit.submit(title,selftext="")
	return submission.id


def edit_post(r,me,conn,cursor,post_id):
	# The purpose of this function is to read the table of saved posts in the
	# database, and then create the post necessary.
	# To do this, the saves need to be loaded from the DB, along with the
	# categories. Next a table from each category (along with an "other"
	# category) should be created, and finally the tables should be joined
	# to one long string, and passed as the argument for edit().

	# Getting the categories
	cursor.execute("SELECT * FROM categories")
	raw = cursor.fetchall()
	cats = [x[0] for x in raw]
	cats_subs = [x[1].split(',') for x in raw]

	# Getting the saves
	cursor.execute("SELECT * FROM saves")
	raw = cursor.fetchall()

	# sorting the saves
	# list of n+1 empty lists for the n categories (and the other category)
	sorted_posts = [[] for x in range(len(cats)+1)]

	# The actual sorting, it ain't pretty. Check each post in raw.
	for post in raw:
		sub = post[5].lower()
		# Check if the post is in each of the categories
		for num,cat in enumerate(cats):
			# if it is in the given category, append it and break
			if sub in cats_subs[num]:
				sorted_posts[num].append(post)
				break
		# If it isn't in any category, it goes into other.
		else:
			sorted_posts[-1].append(post)

	# Now to create the lines for the post. First we
	formatted_posts = [[] for x in range(len(cats)+1)]
	for num,cat in enumerate(sorted_posts):
		for post in cat:
			iid,title,short,link,num_comments,sub = post
			formatted_posts[num].append("""
				[{}]({}) ({}) | [link]({})| /r/{} | {}
				""".format(title,short,num_comments,link,sub,iid))

	formatted_strings = []
	for cat in formatted_posts:
		formatted_strings.append("""\n""".join(cat))

	# Creating the tables
	body = []
	for num,table in enumerate(formatted_strings):
		body.append('#{}'.format(cats[num]))
		body.append(table)

	return """\n""".join(body)








if __name__ == '__main__':
	r,me = bot_login()
	conn,cursor = init_DB()
	old_ids = get_old_ids(conn,cursor)
	get_new_saves(me,old_ids,conn,cursor,lim = 5)
	check_post(r,me,conn,cursor)