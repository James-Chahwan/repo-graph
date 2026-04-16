package server

import (
	"example.com/myapp/auth"
	"example.com/myapp/users"
)

// Stand-in router type — the parser only inspects the call shape, not the
// types, so we don't need a real gin import for the smoke test.
type Router interface {
	GET(path string, handler any)
	POST(path string, handler any)
	Group(prefix string) Router
}

func SetupRoutes(r Router) {
	// Bare handler — same package as the registration site.
	r.GET("/health", health)

	// Cross-package selector handler — must resolve via auth import binding.
	r.POST("/login", auth.DoLogin)

	// Group prefix chain — `/api/users` joins prefix with the route path.
	api := r.Group("/api")
	api.GET("/users", users.List)
}

func health(_ any) {}
