// Firestore rules, tested on the local emulator (project "demo-cnv": never the real data).
// Run with: npm test (inside the firebase folder; needs Java for the emulator).
import { readFileSync } from "node:fs";
import { after, before, beforeEach, test } from "node:test";
import { assertFails, assertSucceeds, initializeTestEnvironment } from "@firebase/rules-unit-testing";
import { deleteDoc, deleteField, doc, getDoc, serverTimestamp, setDoc, updateDoc } from "firebase/firestore";

let env;

before(async () => {
    env = await initializeTestEnvironment({
        projectId: "demo-cnv",
        firestore: { rules: readFileSync(new URL("../firestore.rules", import.meta.url), "utf8") },
    });
});
after(() => env.cleanup());

// Admitted: the administrator "capo" and the e-mail of "amico"; "estraneo" is not
const ALLOW_LIST = { admin: "capo", email: ["amico@example.com"] };
beforeEach(async () => {
    await env.clearFirestore();
    await seed("config/ammessi", ALLOW_LIST);
});

/** A signed-in account: its e-mail is "<uid>@example.com", verified unless said otherwise. */
const as = (uid, email = `${uid}@example.com`, verified = true) =>
    env.authenticatedContext(uid, { email, email_verified: verified }).firestore();
const anonymous = () => env.unauthenticatedContext().firestore();
const VOTES = {
    votes: { 12: "V", 40: "S" },
    seen: { 40: { date: "2026-11-08", cinema: "garden" } },
    exported: {},
    diary: {},
    updated: new Date(),
};

/** A document written with the console or by GitHub (they skip the rules). */
async function seed(path, data) {
    await env.withSecurityRulesDisabled((ctx) => setDoc(doc(ctx.firestore(), path), data));
}

test("ognuno legge e scrive i suoi voti", async () => {
    for (const uid of ["capo", "amico"]) {
        const db = as(uid);
        await assertSucceeds(setDoc(doc(db, `utenti/${uid}`), VOTES));
        await assertSucceeds(getDoc(doc(db, `utenti/${uid}`)));
        await assertSucceeds(updateDoc(doc(db, `utenti/${uid}`), { "votes.99": "?" }));
        await assertSucceeds(deleteDoc(doc(db, `utenti/${uid}`)));
    }
});

test("l'app scrive voto per voto, con l'ora del server", async () => {
    const db = as("amico");
    const ref = doc(db, "utenti/amico");
    await assertSucceeds(setDoc(ref, { votes: { 12: "V" }, updated: serverTimestamp() }, { merge: true }));
    await assertSucceeds(setDoc(ref, { votes: { 12: deleteField(), 40: "S" }, seen: { 40: { date: "2026-11-14", cinema: null } }, updated: serverTimestamp() }, { merge: true }));
    const saved = (await getDoc(ref)).data();
    if (JSON.stringify(saved.votes) !== '{"40":"S"}') throw new Error(`voti sbagliati: ${JSON.stringify(saved.votes)}`);
});

test("nessuno vede o cambia i voti di un altro, neanche l'amministratore", async () => {
    await seed("utenti/amico", VOTES);
    await seed("utenti/capo", VOTES);
    await assertFails(getDoc(doc(as("capo"), "utenti/amico")));
    await assertFails(setDoc(doc(as("capo"), "utenti/amico"), VOTES));
    await assertFails(getDoc(doc(as("amico"), "utenti/capo")));
    await assertFails(deleteDoc(doc(as("amico"), "utenti/capo")));
});

test("chi non è nella lista non entra, anche con l'accesso fatto", async () => {
    await assertFails(getDoc(doc(as("estraneo"), "utenti/estraneo")));
    await assertFails(setDoc(doc(as("estraneo"), "utenti/estraneo"), VOTES));
    await assertFails(getDoc(doc(anonymous(), "utenti/amico")));
});

test("un'email non verificata non basta; maiuscole e minuscole non contano", async () => {
    await assertFails(getDoc(doc(as("amico", "amico@example.com", false), "utenti/amico")));
    await assertSucceeds(getDoc(doc(as("amico", "Amico@Example.com"), "utenti/amico")));
});

test("senza la lista degli ammessi non entra nessuno", async () => {
    await env.withSecurityRulesDisabled((ctx) => deleteDoc(doc(ctx.firestore(), "config/ammessi")));
    await assertFails(getDoc(doc(as("capo"), "utenti/capo")));
    await assertFails(setDoc(doc(as("capo"), "config/ammessi"), ALLOW_LIST)); // nobody makes it from the app
});

test("solo l'amministratore legge e cambia la lista, ma non chi è l'amministratore", async () => {
    await assertSucceeds(getDoc(doc(as("capo"), "config/ammessi")));
    await assertSucceeds(updateDoc(doc(as("capo"), "config/ammessi"), { email: ["amico@example.com", "nuovo@example.com"] }));
    await assertFails(updateDoc(doc(as("capo"), "config/ammessi"), { admin: "amico" }));
    await assertFails(updateDoc(doc(as("capo"), "config/ammessi"), { altro: 1 }));
    await assertFails(updateDoc(doc(as("capo"), "config/ammessi"), { email: "tutti" }));
    await assertFails(deleteDoc(doc(as("capo"), "config/ammessi")));
    await assertFails(getDoc(doc(as("amico"), "config/ammessi")));
    await assertFails(updateDoc(doc(as("amico"), "config/ammessi"), { email: ["amico@example.com", "x@example.com"] }));
});

test("i voti devono avere la forma della copia", async () => {
    const db = as("amico");
    await assertFails(setDoc(doc(db, "utenti/amico"), { ...VOTES, altro: 1 }));
    await assertFails(setDoc(doc(db, "utenti/amico"), { ...VOTES, votes: "V" }));
    await assertFails(setDoc(doc(db, "utenti/amico"), { ...VOTES, updated: "ieri" }));
    await assertSucceeds(setDoc(doc(db, "utenti/amico"), { votes: {} }));
});

test("ognuno registra i suoi telefoni e sceglie le notifiche", async () => {
    const db = as("amico");
    const phone = doc(db, "utenti/amico/telefoni/installazione-123");
    await assertSucceeds(setDoc(phone, { token: "fcm-token", updated: serverTimestamp() }));
    await assertSucceeds(getDoc(phone));
    await assertSucceeds(deleteDoc(phone));
    await assertSucceeds(setDoc(doc(db, "utenti/amico"), { notify: "v" }, { merge: true }));
    await assertFails(setDoc(doc(db, "utenti/amico"), { notify: "sempre" }, { merge: true }));
    await assertFails(setDoc(phone, { token: "" }));
    await assertFails(setDoc(phone, { token: "x", altro: 1 }));
    await assertFails(setDoc(doc(db, "utenti/amico/telefoni/a b"), { token: "x" }));
});

test("nessuno vede i telefoni di un altro; chi è fuori dalla lista non ne registra", async () => {
    await seed("utenti/amico/telefoni/installazione-123", { token: "fcm-token" });
    await assertFails(getDoc(doc(as("capo"), "utenti/amico/telefoni/installazione-123")));
    await assertFails(setDoc(doc(as("capo"), "utenti/amico/telefoni/installazione-999"), { token: "mio" }));
    await assertFails(setDoc(doc(as("estraneo"), "utenti/estraneo/telefoni/installazione-123"), { token: "x" }));
});

test("le altre raccolte sono chiuse a tutti", async () => {
    await assertFails(setDoc(doc(as("capo"), "altro/x"), { a: 1 }));
    await assertFails(getDoc(doc(as("capo"), "config/altro")));
    await assertFails(setDoc(doc(as("capo"), "utenti/capo/sotto/x"), { a: 1 }));
    await assertFails(setDoc(doc(as("capo"), "utenti/capo/telefoni/abcdefgh/altro/x"), { a: 1 }));
});
