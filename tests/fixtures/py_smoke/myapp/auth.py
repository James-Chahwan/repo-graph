from myapp.users import User
from myapp import helpers


def do_login():
    u = User()
    u.login("x")
    helpers.hash_password("x")
