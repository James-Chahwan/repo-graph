package users

type User struct {
	ID   int
	Name string
}

func (u *User) Login(password string) bool {
	return len(password) > 0
}

func (u *User) Save() {
	u.Login("x")
}
