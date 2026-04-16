function inner(p: string): string {
    return p;
}

export function hashPassword(p: string): string {
    return inner(p) + "salt";
}
