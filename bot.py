import praw
import config
import sqlite3
import re
import pprint as pp


categories = {
"python": "python,learnprogramming,dailyprogrammer,learnpython,programming,raspberry_pi",
"asoiaf": "asoiaf",
"entertainment": "anime,games,gamedeals,lowendgaming,patientgamers,fallout",
"life stuff": "getdisciplined,lifeprotips,anxiety,meditation,frugal",
"awws": "wholesomememes,wholesomegifs,rarepuppers,animalsbeingderps,animalssmiling,animaltextgifs,mademesmile,animalsbeingbros"}

subname = "ZynLinkSharing"
title = "Save organizer"

def sep():
    print("----------\n")


def bot_login():
    print("login in.")
    # We log into reddit
    r = praw.Reddit(username = config.username,
                password = config.password,
                client_id = config.client_id,
                client_secret = config.client_secret,
                user_agent = config.user_agent)
    print('logged in!')
    sep()

    # and fetch the user
    me = r.user.me()
    return r,me


def init_DB():
    print("Initializing databases")
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

        cat_to_db = [(k,v) for k,v in categories.items()]
        cursor.executemany("""INSERT INTO categories VALUES (?,?)""", cat_to_db)
        conn.commit()

        print("No tables found. Creating new ones.")

    # do nothing if it's already there
    except sqlite3.OperationalError:
        print("Tables already created, Updating categories")
        cursor.execute('DELETE FROM categories;')
        conn.commit()
        cat_to_db = [(k,v) for k,v in categories.items()]
        cursor.executemany("""INSERT INTO categories VALUES (?,?)""", cat_to_db)
        conn.commit()
        pass

    # Updating the categories table


    print("Database initialized")
    sep()
    return conn,cursor


def get_old_ids(conn,cursor):
    # Get the old saved ids
    print("Fetching saves from DB")
    cursor.execute("SELECT id FROM saves")
    print("Saves fetched")
    sep()

    # fetchall() returns a list of tuples, each with a string and NULL object
    # We use a list comprehension to make a new list, which only has the
    # string (first element) from each tuple.
    return [i[0] for i in cursor.fetchall()]


def get_new_saves(me,old,conn,cursor,lim = 25):
    print("Retrieving saves from reddit")
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
            post_id = i.id
            if post_id in old:
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
                if i.is_self:
                    toDatabase.append((post_id,i.title,i.shortlink,
                        i.shortlink,i.num_comments,i.subreddit.display_name))
                else:
                    toDatabase.append((post_id,i.title,i.shortlink,i.url,
                        i.num_comments,i.subreddit.display_name))

        # if it's a comment we don't
        elif postType == "comment":
            continue
        # if it's something else, I wanna know.
        else:
            print('It\'s something else: ' + postType)
            continue

    # After the loop has run, we commit the new saved submissions to the database
    cursor.executemany("""INSERT INTO saves VALUES (?,?,?,?,?,?)""", toDatabase)
    conn.commit()
    print("{} posts committed to table 'saves'".format(len(toDatabase)))
    sep()


def check_post(r,conn,cursor):
    # We get the current post
    print("Checking post")
    cursor.execute("SELECT * FROM current_post")
    data = cursor.fetchall()

    # if there's nothing in the DB we create a new post
    if len(data)  == 0:
        new_id = create_post(r,title)
        cursor.execute("""INSERT INTO current_post VALUES (?,?)""", [new_id,title])
        conn.commit()
        edit_post(r, conn, cursor, new_id)
        print('No post saved in DB. New post created. ID: {}'.format(new_id))
    # if there's something in the DB, we check if it's archived or not
    else:
        post_id = data[0][0]
        post_title = data[0][1]

        sub = r.submission(id = post_id)
        # if it's archived we create a new post
        if sub.archived:
            new_id = create_post(r,post_title)
            edit_post(r, conn, cursor, new_id)
            cursor.execute("""INSERT INTO current_post VALUES (?,?)""", [new_id,post_title])
            conn.commit()
            print("Post archived. New post created. ID: {}".format(new_id))
        # otherwise we just edit the existing one
        else:
            edit_post(r,conn,cursor,post_id)
            print("Post found and edited.")

    sep()


def read_post(r,post_id):

    # From when conn,cursor was also arguments
    # cursor.execute("SELECT * FROM current_post")
    # data = cursor.fetchall()
    # post_id = data[0][0]
    # post_title = data[0][1]

    p = r.submission(id = post_id)
    title = p.title
    body = p.selftext
    lines = body.split('\n')
    last_rows = []
    first_rows = []
    categories = []

    for num,text in enumerate(lines):
        if len(text) != 0:
            if text[0] == "#":
                # print("Found the title:")
                # print(text[1:])
                # print(lines[num+3])
                first_rows.append(num+3)
                categories.append(text[1:])
        else:
            # print("Found the last rows:")
            # print(lines[num-1])
            last_rows.append(num)

    post_lines = []
    for n in range(0,len(last_rows)):
        for i in lines[first_rows[n]:last_rows[n]]:
            post_lines.append(i)

    return title,post_id,categories,post_lines


def populate_db(r,conn,cursor,post_id):
    title,post_id,categories,post_lines = read_post(r,post_id)
    # The lines in the table of the post is formatted like:
    # [title](url) (num_comments) | [id](shortlink) | /r/subreddit
    # Prototype Regex:
    # (\[[A-Za-z 0-9,.?\-\|\/\\_\[\]\(\)\{\}:;!]*\])(\([a-zA-Z0-9:/.\-?=]*\)) (\([0-9]*\)) \| (\[[A-Za-z 0-9]*\])(\([a-zA-Z0-9:/.\-?=]*\)) \| \/r\/([a-zA-Z]*)
    # Prototype 2
    # (\[[\w\s.,!?:;<>\\\/\-\{\[\]\}\(\)]*\])(\([a-zA-Z0-9:/.\-?=]*\)) (\([0-9]*\)) \| (\[[A-Za-z 0-9]*\])(\([a-zA-Z0-9:/.\-?=]*\)) \| \/r\/([a-zA-Z]*)
    # Prototype 3, now with proper wildcards
    # \[(.*)\]\((.*)\) \((\d*)\) \| \[(.*)\]\((.*)\) \| \/r\/(\w*)
    table_reg = re.compile(r'\[(.*)\]\((.*)\) \((\d*)\) \| \[(.*)\]\((.*)\) \| \/r\/(\w*)')
    saves = []
    for line in post_lines:
        # What we need (in order)
        # - post id (id) (group 3)
        # - post title (title) (group 0)
        # - link to the post (shortlink) (group 4)
        # - link to the "link" (url) (group 1)
        # - number of comments (num_comments) (group 2)
        # - Subreddit (subreddit) (group 5)
        s = table_reg.findall(line)[0]
        toDatabase = (s[3],s[0],s[4],s[1],s[2],s[5])
        saves.append(toDatabase)

    cursor.executemany("""INSERT INTO saves VALUES (?,?,?,?,?,?)""", saves)
    conn.commit()
    print("{} posts committed to table 'saves'".format(len(saves)))
    cursor.execute("""INSERT INTO current_post VALUES (?,?)""", (post_id,title))
    conn.commit()
    print("Current post details commited to table 'current_post'")


def create_post(r,title):
    # Just creates the new self post and returns the ID.
    subreddit = r.subreddit(subname)
    submission = subreddit.submit(title,selftext="hello")
    return submission.id


def edit_post(r,conn,cursor,post_id):
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

    # Now to create the lines for the post. First create a list of n+1 empty
    # lists, and pupulate each of those sublists with strings. One for each
    # saved post.
    formatted_posts = [[] for x in range(len(cats)+1)]
    for num,cat in enumerate(sorted_posts):
        for post in cat:
            iid,title,short,link,num_comments,sub = post
            title = title.replace('|','-')
            formatted_posts[num].append("""[{}]({}) ({}) | [{}]({}) | /r/{}""".format(title,link,num_comments,iid,short,sub))

    # These sublists are then converted to a full string, separated by newline
    # characters.
    formatted_strings = []
    for cat in formatted_posts:
        formatted_strings.append("""\n""".join(cat))

    # The full tables are then created. First the category title, then the
    # table title row, seperator and lastly the table data itself.
    body = []
    for num,table in enumerate(formatted_strings):
        try:
            body.append('#{}'.format(cats[num]))
        except IndexError:
            body.append("#Other")
        body.append('Post | Comments | Subreddit')
        body.append("---|---|----")
        body.append("{}\n".format(table))


    # Next we split up the table into a post and several comments to comply with
    # reddits character limits

    comms = create_comments("""\n""".join(body).split('\n'))

    # create the main post
    bodyStr = """\n""".join(comms[0])
    submission = r.submission(id = post_id)
    submission.edit(bodyStr)

    # submit the comments with the rest of the saves
    for com in comms[1:]:
        comment = """\n""".join(com)
        submission.reply(comment)



def create_comments(l):
    # initialize variables needed
    length = 0
    commentLists = [[]]
    comCount = 0
    startNum = 0
    maxLength = 40000
    # loop over all of the lines in the list l
    for num, line in enumerate(l):
        # record the cummulative length
        length += len(line)

        # if we encounter a new category (header), set the category
        if len(line) != 0 and line[0] == "#":
            cat = line[1:]

        # if we're over 10K (40K for post) characters, start new comment
        if length >= maxLength:
            # Change max length from post to comments
            maxLength = 10000

            # Put the links in the current comment and create a new one

            commentLists[comCount] = commentLists[comCount] + l[startNum:num]
            commentLists.append(
                ['#{}'.format(cat), 'Post | Comments | Subreddit',
                 '---|---|----'])

            # Increase Comment count
            comCount += 1

            # Reset startNum
            startNum = num

            # Reset length
            length = len(commentLists[comCount])

    return commentLists



if __name__ == '__main__':
    r,me = bot_login()
    conn,cursor = init_DB()
    old_ids = get_old_ids(conn,cursor)
    # get_new_saves(me,old_ids,conn,cursor,lim = None)
    check_post(r,conn,cursor)
    # populate_db(r,conn,cursor,"661mz0")