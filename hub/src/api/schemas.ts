import { z } from "zod";

/**
 * The intake brief, as a schema.
 *
 * One page, six sections, matching §7.11 step 1 of the platform specification.
 * The same schema validates in the browser (per step, as the person moves) and
 * is what the server is expected to validate on file, so the two never drift.
 * Messages are written for the person filling the form, not for a log.
 */
export const channelSchema = z.enum(["operator", "customer", "partner", "batch"]);
export const tierSchema = z.enum(["R", "W1", "W2", "M"]);
export const ceilingSchema = z.enum(["R", "W1", "W2"]);
export const dataClassSchema = z.enum(["internal", "confidential", "restricted"]);
export const modelNeedSchema = z.enum(["none", "utility", "workhorse", "frontier"]);

export const TIER_RANK: Record<z.infer<typeof tierSchema>, number> = { R: 0, W1: 1, W2: 2, M: 3 };

export const useCaseSchema = z.object({
  name: z.string().trim().min(3, "Give the use case a name.").max(80, "Keep the name under 80 characters."),
  problem: z.string().trim().min(20, "Describe what happens today in a few sentences."),
  channel: channelSchema,
  teamId: z.string().min(1, "Choose the team this belongs to."),
});

export const peopleSchema = z.object({
  businessOwner: z.string().trim().min(1, "Name the business owner."),
  productOwner: z.string().trim().min(1, "Name the product owner."),
  domainExpert: z.string().trim().min(1, "Name the domain expert who will label cases (PLT-ONB-11)."),
  labellingHoursPerWeek: z
    .number({ invalid_type_error: "Enter hours per week." })
    .min(1, "At least one hour a week through sandbox.")
    .max(40, "That is more than a working week."),
});

export const toolSchema = z.object({
  name: z.string().min(1),
  tier: tierSchema,
  classes: z.array(dataClassSchema).min(1),
});

export const dataAndToolsSchema = z
  .object({
    systems: z.array(z.object({ id: z.string(), name: z.string() })).min(1, "Name at least one system of record."),
    tools: z.array(toolSchema).min(1, "Add at least one tool.").max(15, "Over the 15-tool session ceiling; remove tools or split the consumer."),
    dataClasses: z.array(dataClassSchema).min(1, "Choose the data classes the consumer reads."),
    tierCeiling: ceilingSchema,
    /** Components of the collection and services of the bank the consumer reuses; named in the brief, reviewed as reuse. */
    reuses: z
      .array(z.object({ id: z.string().min(1), name: z.string().min(1), kind: z.string().min(1) }))
      .max(20)
      .optional(),
  })
  .superRefine((v, ctx) => {
    if (v.dataClasses.includes("restricted")) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["dataClasses"], message: "Restricted data is not available to a first consumer." });
    }
    const over = v.tools.filter((t) => TIER_RANK[t.tier] > TIER_RANK[v.tierCeiling]);
    if (over.length) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["tierCeiling"],
        message: `The tier ceiling must cover every tool: ${over.map((t) => `${t.name} (${t.tier})`).join(", ")}.`,
      });
    }
  });

export const modelSchema = z.object({
  need: modelNeedSchema,
  classificationCeiling: dataClassSchema,
  substitute: z.boolean(),
});

export const outcomeSchema = z
  .object({
    metric: z.string().trim().min(1, "Name one outcome metric (PLT-ONB-10)."),
    unit: z.string().trim().min(1, "Give the metric a unit."),
    baseline: z.number({ invalid_type_error: "Enter today's figure." }).nonnegative("A baseline cannot be negative."),
    target: z.number({ invalid_type_error: "Enter the target." }).nonnegative("A target cannot be negative."),
    measuredOn: z.string().min(1, "When was the baseline measured?"),
  })
  .refine((v) => v.target !== v.baseline, { path: ["target"], message: "The target should differ from the baseline." });

export const reviewSchema = z.object({
  acknowledged: z.literal(true, { errorMap: () => ({ message: "Confirm you have read what happens next." }) }),
});

export const briefContentSchema = z.object({
  useCase: useCaseSchema,
  people: peopleSchema,
  dataAndTools: dataAndToolsSchema,
  model: modelSchema,
  outcome: outcomeSchema,
  review: reviewSchema,
});

export type BriefContent = z.infer<typeof briefContentSchema>;
export type BriefStepKey = keyof BriefContent;

/** Step order on the form and in §7.11. */
export const BRIEF_STEPS: BriefStepKey[] = ["useCase", "people", "dataAndTools", "model", "outcome", "review"];

export const STEP_SCHEMAS: Record<BriefStepKey, z.ZodTypeAny> = {
  useCase: useCaseSchema,
  people: peopleSchema,
  dataAndTools: dataAndToolsSchema,
  model: modelSchema,
  outcome: outcomeSchema,
  review: reviewSchema,
};

/** Field errors keyed by dotted path, the shape the API also returns for 422. */
export type FieldErrors = Record<string, string[]>;

export function issuesToFieldErrors(issues: z.ZodIssue[], prefix = ""): FieldErrors {
  const out: FieldErrors = {};
  for (const i of issues) {
    const key = [prefix, ...i.path].filter((p) => p !== "").join(".");
    (out[key] ??= []).push(i.message);
  }
  return out;
}

export function validateStep(step: BriefStepKey, value: unknown): FieldErrors {
  const r = STEP_SCHEMAS[step].safeParse(value);
  return r.success ? {} : issuesToFieldErrors(r.error.issues, step);
}
