import { expect, test } from "@playwright/test";
import { safeNext } from "../src/lib/safe-next";
import { privatNext } from "../src/lib/privat-next";

/* Open redirect via ?next= (QA verifier, 11/11): the URL parser drops tab/CR/LF and treats "\" as "/", so
 * "/\t/evil.example" became "//evil.example". Pure function tests – no stack needed. */
test.describe("enheder · safeNext", () => {
  const evil = ["//evil.example", "/\\evil.example", "/\t/evil.example", "/\n/evil.example", "/\r/evil.example",
    "/%09/evil.example", " /evil", "/\\/evil.example", "/ /evil.example", "https://evil.example", "javascript:alert(1)",
    "/%2e%2e/app", "/privat/%2E%2E/app", "/%5cevil.example", "/%2f/evil.example"];
  for (const n of evil) test(`afviser ${JSON.stringify(n)}`, () => {
    expect(safeNext(n, "/fallback")).toBe("/fallback");
    expect(privatNext(n)).toBeNull();
  });
  // a decoded control character as the browser would hand it over from ?next=%09
  test("afviser dekodede kontroltegn", () => expect(safeNext(decodeURIComponent("/%09/evil.example"), "/f")).toBe("/f"));
  for (const ok of ["/app", "/privat/dag", "/privat/konto?plan=plus&interval=month", "/g/ABCDEFGH", "/app/opkald#top"])
    test(`beholder ${ok}`, () => expect(safeNext(ok, "/f")).toBe(ok));
});
