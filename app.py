from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy 
from flask_login import login_required, login_user, logout_user, UserMixin, current_user, LoginManager
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
import os
import io
import string, random
import qrcode
from dotenv import load_dotenv

app = Flask(__name__, template_folder="templates")
load_dotenv()

Base_dir = os.path.dirname(os.path.realpath(__file__))
#SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
#if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
    #SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"]="sqlite:///"+ os.path.join(Base_dir, "db.sqlite3")
#app.config["SQLALCHEMY_DATABASE_URI"]=os.environ.get("DATABASE_URI")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"]=False
app.config["SECRET_KEY"]=os.environ.get("SECRET_KEY")
app.config["CACHE_TYPE"]="SimpleCache"
app.config["CACHE_DEFAULT_TIMEOUT"]=300

db = SQLAlchemy(app)
cache = Cache(app)
limiter = Limiter(get_remote_address)
migrate = Migrate(app,db)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

qr = qrcode.QRCode(version = 1, 
                   error_correction = qrcode.constants.ERROR_CORRECT_L, 
                   box_size = 5, 
                   border = 4)

def generate_short_url(length=5):
    chars = string.ascii_letters + string.digits
    short_url = "".join(random.choice(chars)for _ in range(length))
    return short_url

class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer(), primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(), nullable=False, unique=True)
    password = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(), default=datetime.utcnow)
    user_links =db.relationship("Link", backref="user", lazy=True)

          
    def __repr__(self):
        return f"<User: {self.username}>"
    
    def save(self):
        db.session.add(self)
        db.session.commit()

    @classmethod
    def get_by_id(cls, id):
        return cls.query.get_or_404(id)


class Link(db.Model, UserMixin):
    __tablename__ = "links"
    id = db.Column(db.Integer, primary_key=True)
    long_url = db.Column(db.String(550), nullable=False)
    short_url = db.Column(db.String(5), unique=True, nullable=False)
    custom_url= db.Column(db.String(40), unique=True, default=None)
    clicks = db.Column(db.Integer, default=0)
    qr_code = db.Column(db.String())
    created_at = db.Column(db.DateTime(), default=datetime.utcnow())
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    def __repr__(self):
        return f'<Link {self.short_url}>'
    
    def save(self):
        db.session.add(self)
        db.session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()
    
def generate_qr_code(url):
    img = qrcode.make(url)
    immg = io.BytesIO()
    img.save(immg, "PNG")
    immg.seek(0)
    return immg

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    if request.method == "POST":
        email=request.form["email"]
        username=request.form["username"]
        password=request.form["password"]
        confirm_password=request.form["confirm_password"]

        mail=User.query.filter_by(email=email.lower()).first()
        user=User.query.filter_by(username=username).first()
        if mail:
            flash("This email already taken.")
        elif len(username) < 3:
            flash("Username must be greater than 2 characters.")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.")

        elif user:
            flash("This username already exists.")

        elif password != confirm_password:
            flash("password and confirm_password does not match. Please try again! ")
        
        else:
            new_user = User(email=email.lower(),username=username, password=generate_password_hash(password))                                                                                                  

            db.session.add(new_user)
            db.session.commit()
            flash("Account created successfully. Please check your mail inbox or spam for verification.")
            return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    if request.method=="POST":
        email=request.form["email"]
        password=request.form["password"]
        user = User.query.filter_by(email=email.lower()).first()
        if user:
            if user and check_password_hash(user.password, password) :
                login_user(user)
                flash("You are now logged in.")
                return redirect(url_for("home"))
            if user and check_password_hash(user.password, password) == False:
                flash("Invalid password or email. Please try again.")
                return redirect(url_for("login"))
            
        else:
            flash("Account not found. Please sign up to continue.")
            return redirect(url_for("signup"))
        
    return render_template("login.html")

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("home"))

@app.route("/", methods=["GET", "POST"])
@limiter.limit("10/minute")
def home():
    if request.method == "POST":
        
        long_url=request.form["long_url"]
        custom_url=request.form["custom_url"] or None
        if custom_url:
            existing_url=Link.query.filter_by(custom_url=custom_url).first()
            if existing_url:
                flash("Custom URL already exists. Please try another one!")
                return redirect(url_for("home"))
            short_url = custom_url
        elif long_url[:4] != "http":
            long_url = "http://" + long_url
        else:
            while True:
                short_url =generate_short_url()
                short_url_exist = Link.query.filter_by(short_url=short_url).first()
                if not short_url_exist:
                    break
            link = Link(long_url=long_url, short_url=short_url, custom_url=custom_url, user_id = current_user.id)
            db.session.add(link)
            db.session.commit()
            return redirect(url_for("dashboard"))
    
    return render_template('index.html')

@app.route("/dashboard")
@login_required
@cache.cached(timeout=50)
def dashboard():
    links = Link.query.filter_by(user_id=current_user.id).order_by(Link.created_at.desc()).all()
    host = request.host_url
    return render_template("dashboard.html", links=links, host=host)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/<short_url>")
@cache.cached(timeout=50)
def redirect_url(short_url):
    link = Link.query.filter_by(short_url=short_url).first()
    if link:
        link.clicks +=1
        db.session.commit()
        return redirect(link.long_url)
    return "URL not found."

@app.route("/analytics/<short_url>")
@login_required
@cache.cached(timeout=50)
def url_analytics(short_url):
    link=Link.query.filter_by(short_url=short_url).first()
    host=request.host_url
    if link:
        return render_template("analytics.html", link=link, host=host)
    return "URL not found."

@app.route("/history")
@login_required
@cache.cached(timeout=50)
def link_history():
    links=Link.query.filter_by(user_id=current_user.id).order_by(Link.created_at.desc()).all()
    host=request.host_url
    return render_template("history.html", links=links, host=host)

@app.route("/qr_code/<short_url>")
def generate_qr_code_url(short_url):
    link = Link.query.filter_by(short_url=short_url).first()
    if link:
        immg = generate_qr_code(request.host_url + link.short_url)
        return immg.getvalue(), 200, {"Content-Type": "image/png"}
    return "URL not found"
               
@app.route("/<short_url>/edit", methods=["GET", "POST"])
@login_required
@limiter.limit("10/minutes")
def edit_url(short_url):
    link = Link.query.filter_by(short_url=short_url).first()
    host= request.host_url
    if link:
        if request.method == "POST":
            custom_url= request.form["custom_url"]
            if custom_url:
                existing_url = Link.query.filter_by(custom_url=custom_url).first()
                if existing_url:
                    flash("Custom URL already exists. Please try another one.")
                    return redirect(url_for("edit_url", id=id))
                link.custom_url = custom_url
                link.short_url = custom_url
            db.session.commit()
            return redirect(url_for("dashboard"))
        return render_template("edit.html", link=link, host=host)
    return "URL not found"
    
@app.route("/<short_url>/delete")
@login_required
def delete(short_url):
    link = Link.query.filter_by(short_url=short_url).first()


    if link:
        db.session.delete(link)
        db.session.commit()
        return redirect(url_for("dashboard"))
    return "URL not found"

with app.app_context():
    db.create_all()
if __name__ == "__main__":
    app.run()