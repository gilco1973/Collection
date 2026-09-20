import { useTranslation } from "react-i18next";
import { useSetPersona } from "../api/hooks";
import type { Profile } from "../api/types";

const chipBase = "inline-flex h-8 items-center whitespace-nowrap rounded-s border px-3 text-[13px] font-semibold transition active:scale-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50";
const chipOn = `${chipBase} border-emphasis bg-emphasis text-on-emphasis`;
const chipOff = `${chipBase} border-rule-2 bg-surface-2 text-ink hover:bg-surface-3`;

/**
 * Chips for the personas the server offers (`profile.personas`) plus one to have none. Choosing one
 * is a display preference saved to the reader's own profile — it never restricts which pages they can open.
 * `onDone` fires after a successful change, or when the reader skips the choice for now (the last chip reads
 * "Skip for now" while nothing is chosen and the caller can dismiss the picker; "No persona" otherwise).
 */
export default function PersonaPicker({ profile, onDone }: { profile: Profile; onDone?: () => void }) {
  const { t } = useTranslation();
  const set = useSetPersona();
  const none = profile.persona === null;
  const skippable = none && !!onDone;
  const choose = (persona: string | null) => {
    if (persona === profile.persona) return onDone?.();
    set.mutate(persona, { onSuccess: () => onDone?.() });
  };
  return (
    <div role="group" aria-label={t("persona.title")} className="flex flex-wrap items-center gap-2" data-testid="persona-picker">
      {profile.personas.map((id) => (
        <button key={id} type="button" aria-pressed={profile.persona === id} disabled={set.isPending} onClick={() => choose(id)} className={profile.persona === id ? chipOn : chipOff}>
          {t(`persona.labels.${id}`, { defaultValue: id })}
        </button>
      ))}
      <button type="button" aria-pressed={skippable ? undefined : none} disabled={set.isPending} onClick={() => choose(null)} className={none && !skippable ? chipOn : `${chipOff} text-muted`}>
        {skippable ? t("persona.skip") : t("persona.none")}
      </button>
      {set.error && <span role="alert" className="text-[12px] text-crit">{set.error.message}</span>}
    </div>
  );
}
