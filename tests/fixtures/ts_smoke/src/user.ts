import { hashPassword } from "./helpers";

export class User {
    id: number;
    name: string;

    constructor(id: number, name: string) {
        this.id = id;
        this.name = name;
    }

    login(password: string): string {
        return hashPassword(password);
    }

    save(): string {
        return this.login("x");
    }
}
