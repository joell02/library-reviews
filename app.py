import os, json
import requests

from flask import Flask, session, render_template, redirect, request, jsonify, flash
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from helpers import login_required

from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))


@app.route("/", methods=["GET"])
def index():
    return render_template("startscreen.html", isLoggedIn=False)

@app.route("/login", methods=["GET", "POST"])
def login():

    session.clear()
    error=None
    
    if request.method == "POST":
        
        if not request.form.get("username"):
            error = 'No username entered. Please try again.'
            return render_template("login.html", error=error)
        elif not request.form.get("password"):
            error = 'No password entered. Please try again.'
            return render_template("login.html", error=error)
        
        result = db.execute("SELECT * FROM users WHERE username= :username",
                    {"username": request.form.get("username")}).fetchone()
        
        if result == None or not check_password_hash(result.hash, request.form.get("password")):
            error='Invalid credentials. Please try again.'
            return render_template("login.html", error=error)
        
        session["user_id"] = result.id
        session["user_name"]= result.username
        session.logged_in = True #if user credentials are correct 
        flash ('Login successful.')
        return redirect('/search')
    return render_template("login.html", error=error)

@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash('Logged out of account.')
    return redirect("/")

@app.route("/register", methods=["GET", "POST"])
def register():
    session.clear()
    error=None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmPassword = request.form.get("confirmPassword")

        if not username:
            error = 'No username entered. Please try again.'
            return render_template("register.html", error=error)

        if db.execute("SELECT * FROM users WHERE username = :username", {"username": username}).fetchone():
            error='Username already exists. Please try again.'
            return render_template("register.html", error=error)

        elif not password:
            error='No password entered. Please try again.'
            return render_template("register.html", error=error)

        elif not confirmPassword:
            error='No password confirmation entered. Please try again.'
            return render_template("register.html", error=error)

        elif password != confirmPassword:
            error='Passwords do not match. Please try again.'
            return render_template("register.html", error=error)

        hashedPassword = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)",
                    {"username": username, "password": hashedPassword})
        db.commit()
        flash('Account created', 'info')
        return redirect('/login')
    else:
        return render_template("register.html")

@app.route("/search")
@login_required
def search():
    return render_template("search.html")

@app.route("/searchResults", methods=["GET", "POST"])
@login_required
def searchResults():
    error = None
    search = request.form.get("search")
    if not search:
        error='Nothing was entered. Please try again.'
        return render_template("search.html", error=error)
    
    query = "%" + search  + "%"
    query = query.title()
    searchResults = db.execute("SELECT isbn, title, author, year FROM books WHERE \
        isbn LIKE :query OR \
        title LIKE :query OR \
        author LIKE :query LIMIT 15",
        {"query": query})
    

    if searchResults.rowcount == 0:
        error="Sorry, no books matched this search."
        return render_template("search.html", error=error)
    
    books = searchResults.fetchall()

    return render_template("results.html", books=books)

@app.route("/book/<isbn>", methods=["GET","POST"])
@login_required
def book(isbn):

    if request.method == "POST":
        currentUser = session["user_id"]

        rating = request.form.get("rating")
        message = request.form.get("comment")

        row = db.execute("SELECT id FROM books WHERE isbn = :isbn",
                        {"isbn": isbn}).fetchone()
        bookId = row[0] #save id of book into variable

        #check for user submission(only 1 per user per book)
        row2 = db.execute("SELECT * FROM reviews WHERE user_id=:user_id AND book_id=:book_id",
                            {"user_id": currentUser, "book_id":bookId})
        
        #a review already exists
        if row2.rowcount == 1:
            flash('You already submitted a review for this book', 'warning')
            return redirect("/book/" + isbn)
        
        rating = int(rating)

        #save new review in database
        db.execute("INSERT INTO reviews (user_id, comment, rating, book_id) VALUES \
                    (:user_id, :comment, :rating, :book_id)",
                    {"user_id" : currentUser, "comment": message, "rating": rating, "book_id": bookId})
        db.commit()

        flash("Review submitted successfully.", 'info')
        return redirect("/book/" + isbn)
    else:

        bookInfo = db.execute("SELECT isbn, title, author, year FROM books WHERE isbn=:isbn",
                    {"isbn": isbn}).fetchall()

        key = os.getenv("GOODREADS_KEY")

        query = requests.get("https://www.goodreads.com/book/review_counts.json",
                            params={"key": key , "isbns":isbn})
        response = query.json()
        response = response['books'][0]
        bookInfo.append(response)

        #User Reviews

        #search book_id by isbn
        row = db.execute("SELECT id FROM books WHERE isbn=:isbn",
                        {"isbn": isbn})
        book = row.fetchone()
        book = book[0]

        results = db.execute("SELECT users.username, comment, rating, to_char(date, 'DD Mon YYYY HH:MI:SS') as date \
        FROM users INNER JOIN reviews ON users.id = reviews.user_id \
        WHERE book_id= :book ORDER by date",
        {"book": book})
        reviews = results.fetchall()

    return render_template("book.html", bookInfo=bookInfo, reviews=reviews)
