// Fails when any locale is missing (or has extra) keys relative to en.json, leaves a value empty,
// drops an interpolation variable, or has an incomplete plural family (`key_one` / `key_other`).
// Every locale must carry each CLDR plural category its Intl.PluralRules returns on this Node
// (`he` one/two/other, `fr` one/many/other, ...); extra categories English lacks are allowed.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
const dir = new URL("../src/i18n/locales/", import.meta.url).pathname;
const CATEGORIES = ["zero", "one", "two", "few", "many", "other"];
const PLURAL = new RegExp(`_(${CATEGORIES.join("|")})$`);
const flatten = (o, p = "") => Object.entries(o).flatMap(([k, v]) => (typeof v === "object" ? flatten(v, `${p}${k}.`) : [[`${p}${k}`, v]]));
const load = (file) => Object.fromEntries(flatten(JSON.parse(readFileSync(join(dir, file), "utf8"))));
const en = load("en.json");
const pluralBases = new Set(Object.keys(en).filter((k) => PLURAL.test(k)).map((k) => k.replace(PLURAL, "")));
let failed = false;
const report = (file, problems) => {
  const lines = Object.entries(problems).filter(([, v]) => v.length);
  if (lines.length) { failed = true; console.error(`${file}: ${lines.map(([k, v]) => `${k}=${v.join(",")}`).join(" ")}`); }
};
report("en.json", { bareWithPlural: [...pluralBases].filter((b) => b in en), pluralIncomplete: [...pluralBases].filter((b) => !(`${b}_one` in en) || !(`${b}_other` in en)) });
for (const file of readdirSync(dir).filter((f) => f.endsWith(".json") && f !== "en.json")) {
  const flat = load(file);
  const lng = file.replace(".json", "");
  const cldr = new Intl.PluralRules(lng).resolvedOptions().pluralCategories;
  const isExtraCategory = (k) => PLURAL.test(k) && pluralBases.has(k.replace(PLURAL, "")) && !(k in en);
  report(file, {
    missing: Object.keys(en).filter((k) => !(k in flat) || !String(flat[k]).trim()),
    extra: Object.keys(flat).filter((k) => !(k in en) && !isExtraCategory(k)),
    vars: Object.keys(en).filter((k) => k in flat && (String(en[k]).match(/{{\w+}}/g) ?? []).some((v) => !String(flat[k]).includes(v))),
    bareWithPlural: [...pluralBases].filter((b) => b in flat),
    cldrMissing: [...pluralBases].flatMap((b) => cldr.filter((c) => !(`${b}_${c}` in flat)).map((c) => `${b}_${c}`)),
  });
}
if (!failed) console.log(`i18n ok: ${readdirSync(dir).length} locales, ${Object.keys(en).length} keys each (${pluralBases.size} plural families)`);
process.exit(failed ? 1 : 0);
