import * as helpers from "./helpers";
import { User } from "./user";

export function doLogin(): string {
    const who: User | null = null;
    void who;
    return helpers.hashPassword("x");
}
