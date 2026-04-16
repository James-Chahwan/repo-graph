// Angular-style service — stand-in HttpClient type so the parser doesn't need
// a real @angular/common/http dep in the fixture. The v0.4.4 extractor is
// framework-agnostic: it matches on `this.<field>.<method>(...)` syntax, so
// any class field used with HTTP-verb method names triggers it.
class HttpClient {
    get(_url: string, _opts?: unknown): unknown { return null; }
    post(_url: string, _body?: unknown, _opts?: unknown): unknown { return null; }
}

export class UserService {
    private http: HttpClient = new HttpClient();

    listUsers() {
        // Should match backend `api.GET("/users", users.List)` — string literal, Strong.
        return this.http.get('/api/users');
    }

    createUser(payload: unknown) {
        // Should match backend `api.POST("/users", users.Create)`.
        return this.http.post('/api/users', payload);
    }

    getUser(id: number) {
        // Should match backend `api.GET("/users/:id", users.Get)` via path normalisation.
        // Template with substitution → Medium confidence on the endpoint node.
        return this.http.get(`/api/users/${id}`);
    }
}
