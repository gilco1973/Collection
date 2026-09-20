import { useState } from "react";
import { Link } from "react-router-dom";
import type { ShelfAttestation, ShelfEntry, ShelfRole } from "../../api/types";
import { ROUTES } from "../../routes";
import { CheckRow, Field, Seg, TextInput } from "../../ui/fields";
import { OkCircle } from "../../ui/icons";
import { ROLE_LABEL, openRolesFor, signoffView } from "./stages";
import { useSign } from "./useShelf";

const ATTESTATIONS: Array<{ key: keyof ShelfAttestation; label: string; note: (e: ShelfEntry) => string }> = [
  { key: "testsGreen", label: "I ran the tests and they are green", note: (e) => e.test || "a checklist in SKILL.md" },
  { key: "exampleRun", label: "I ran the live example", note: (e) => e.exampleRun || "the filled example document" },
  { key: "walkthroughRead", label: "I read the walkthrough end to end", note: () => "WALKTHROUGH.md" },
  { key: "rulesRead", label: "I read the rules it enforces and its known limits", note: () => "README.md" },
];

const EMPTY: ShelfAttestation = { testsGreen: false, exampleRun: false, walkthroughRead: false, rulesRead: false };

/**
 * The sign-off form for one component. Shown only to a person who may sign a
 * role that is still open; everyone else sees who signs instead. Every box is
 * an attestation the server also requires, so the form cannot be skipped by
 * calling the API directly.
 */
export function SignoffForm({ entry, compact }: { entry: ShelfEntry; compact?: boolean }) {
  const open = openRolesFor(entry);
  const [role, setRole] = useState<ShelfRole>(open[0] ?? "owner");
  const [attest, setAttest] = useState<ShelfAttestation>(EMPTY);
  const [usedIn, setUsedIn] = useState("");
  const [note, setNote] = useState("");
  const sign = useSign();
  const active: ShelfRole = open.includes(role) ? role : (open[0] ?? role);
  const needsUsedIn = active === "owner" && entry.usedIn.length === 0;
  const complete = ATTESTATIONS.every((a) => attest[a.key]) && (!needsUsedIn || usedIn.trim().length > 0);

  if (open.length === 0) {
    const recordedByYou = entry.youMaySign.some((r) => signoffView(entry, r).kind === "recorded");
    return (
      <div className="muted" style={{ fontSize: 12.5 }}>
        {entry.status !== "ready"
          ? `A sign-off needs a ready component; this one is ${entry.status}.`
          : recordedByYou
            ? "Your sign-off is recorded here; export the queue and apply it so the commit makes it a record."
            : entry.signed
              ? "Signed at this version by both. A version bump asks both to sign again."
              : `Who signs: the owner (${entry.owner}) by name, and an AI security engineer by the ai.security role.`}{" "}
        <Link to={ROUTES.shelfSignoffs}>Open the queue</Link>
      </div>
    );
  }

  return (
    <form
      className="col"
      style={{ gap: compact ? 10 : 14 }}
      onSubmit={(e) => {
        e.preventDefault();
        if (!complete || sign.isPending) return;
        sign.mutate(
          { component: entry.name, role: active, attest, usedIn: needsUsedIn ? usedIn.trim() : undefined, note: note.trim() || undefined },
          { onSuccess: () => setAttest(EMPTY) },
        );
      }}
    >
      {open.length > 1 && (
        <Field label="Sign as">
          <Seg label="Sign as" value={active} onChange={setRole} options={open.map((r) => ({ value: r, label: ROLE_LABEL[r] }))} />
        </Field>
      )}
      <div className="col" style={{ gap: 8 }}>
        <b style={{ fontSize: 13 }}>
          {ROLE_LABEL[active]} sign-off on {entry.title} {entry.version}
        </b>
        {ATTESTATIONS.map((a) => (
          <CheckRow key={a.key} checked={attest[a.key]} onChange={(v) => setAttest({ ...attest, [a.key]: v })} label={a.label} note={a.note(entry)} />
        ))}
      </div>
      {needsUsedIn && (
        <Field
          label="Used once for real: which project"
          id={`usedin-${entry.name}`}
          help="The owner signs after one real use. Name the project; it is recorded in the manifest."
        >
          <TextInput id={`usedin-${entry.name}`} value={usedIn} onChange={setUsedIn} placeholder="project name" maxLength={80} />
        </Field>
      )}
      <Field
        label="Note (optional)"
        id={`note-${entry.name}`}
        help={
          active === "ai_security"
            ? "What you looked at hardest, and anything the owner should fix in the next version."
            : "Where it ran and what you changed to make it fit."
        }
      >
        <TextInput id={`note-${entry.name}`} value={note} onChange={setNote} multiline maxLength={600} />
      </Field>
      <div className="row">
        <button type="submit" className={`btn p${complete && !sign.isPending ? "" : " dis"}`} disabled={!complete || sign.isPending}>
          <OkCircle />
          {sign.isPending ? "Recording…" : `Sign as ${ROLE_LABEL[active].toLowerCase()}`}
        </button>
        <span className="muted" style={{ fontSize: 12 }}>
          recorded as {entry.version}; the commit that follows is the signature
        </span>
      </div>
    </form>
  );
}

/** The card on a component's listing page: version, both sign-offs, and the form when this person may sign. */
export function SignoffPanel({ entry }: { entry: ShelfEntry }) {
  return (
    <div className="card" id="signoff">
      <div className="ch">
        <h3>Sign-off</h3>
        <span className="sp"></span>
        <span className="chip mono">v{entry.version}</span>
        <span className={`chip ${entry.signed ? "ok" : "warn"}`}>{entry.signed ? "signed" : entry.state}</span>
      </div>
      <div className="cb" style={{ gap: 12 }}>
        <SignoffRows entry={entry} />
        <SignoffForm entry={entry} compact />
      </div>
    </div>
  );
}

export function SignoffRows({ entry }: { entry: ShelfEntry }) {
  return (
    <div className="kv">
      {(["owner", "ai_security"] as ShelfRole[]).map((role) => {
        const v = signoffView(entry, role);
        return (
          <span key={role} style={{ display: "contents" }}>
            <b>{ROLE_LABEL[role]}</b>
            <div className="v row" style={{ gap: 8 }}>
              <span className={`chip ${v.chip}`}>{v.kind}</span>
              <span style={{ fontSize: 12.5 }}>{v.text}</span>
            </div>
          </span>
        );
      })}
      <b>Stage</b>
      <div className="v" style={{ fontSize: 12.5 }}>
        {entry.stage.label} · next: {entry.stage.next}
      </div>
    </div>
  );
}
