package auth

import (
	"example.com/myapp/helpers"
	"example.com/myapp/users"
)

func DoLogin() string {
	u := users.User{ID: 1, Name: "alice"}
	_ = u
	return helpers.HashPassword("x")
}
