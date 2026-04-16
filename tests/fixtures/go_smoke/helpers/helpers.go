package helpers

func HashPassword(p string) string {
	return inner(p) + "salt"
}
