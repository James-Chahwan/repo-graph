from .helpers import hash_password


class User:
    def login(self, password):
        return hash_password(password)

    def save(self):
        self.login("x")
