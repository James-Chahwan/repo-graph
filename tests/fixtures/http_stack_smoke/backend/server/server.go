package server

import (
	"example.com/backend/users"
)

// Stand-in router — tree-sitter only cares about call shape, not types.
type Router interface {
	GET(path string, handler any)
	POST(path string, handler any)
	Group(prefix string) Router
}

func SetupRoutes(r Router) {
	api := r.Group("/api")

	// Matches the Angular service's `this.http.get('/api/users')`.
	api.GET("/users", users.List)
	// Matches `this.http.post('/api/users', payload)`.
	api.POST("/users", users.Create)
	// Matches `this.http.get(\`/api/users/${id}\`)` — path-param form.
	api.GET("/users/:id", users.Get)
}
