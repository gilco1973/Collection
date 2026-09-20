import { Link, useNavigate } from "react-router-dom";
import type { ConsumerSummary } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { assistantRoute, consumerRoute } from "../../routes";
import { Glyph } from "../../ui/icons";
import { useCreateRequest } from "../requests/useCreateRequest";

/**
 * One listing card, as the Discover artboard draws it. The action in the foot
 * follows `access`, which the platform resolved for this person: open, ask,
 * view, or read the contract. Nothing unreachable is advertised (PLT-UI-17).
 */
export function ListingCard({ c, requested }: { c: ConsumerSummary; requested?: boolean }) {
  const navigate = useNavigate();
  const { can } = useAuth();
  const create = useCreateRequest();
  const to = c.kind === "assistant" && c.access === "open" ? assistantRoute(c.id) : consumerRoute(c);
  const pending = requested || (create.isSuccess && create.variables?.consumerId === c.id);

  let action: React.ReactNode;
  switch (c.access) {
    case "open":
      action = (
        <button type="button" className="btn p s" onClick={() => navigate(to)}>
          Open
        </button>
      );
      break;
    case "request":
      action = can("consumer.request_access", { consumerId: c.id }) ? (
        <button
          type="button"
          className={`btn  s${pending ? " dis" : ""}`}
          disabled={pending || create.isPending}
          onClick={() => create.mutate({ kind: c.requestKind ?? "access", consumerId: c.id })}
        >
          {pending ? "Requested" : "Request access"}
        </button>
      ) : (
        <button type="button" className="btn  s" onClick={() => navigate(to)}>
          View
        </button>
      );
      break;
    case "contract":
      action = (
        <button type="button" className="btn  s" onClick={() => navigate(to)}>
          Read contract
        </button>
      );
      break;
    default:
      action = (
        <button type="button" className="btn  s" onClick={() => navigate(to)}>
          View
        </button>
      );
  }

  return (
    <div className="lc">
      <div className="row">
        <span className={`ic ${c.icon}`}>
          <Glyph name={c.glyph} size={18} />
        </span>
        <span className="sp"></span>
      </div>
      <h3>
        <Link to={to} style={{ color: "inherit" }}>
          {c.name}
        </Link>
      </h3>
      <p>{c.description}</p>
      <div className="meta">
        {c.meta.map((m) => (
          <span key={m.text} className={`chip ${m.kind ?? ""}`}>
            {m.text}
          </span>
        ))}
      </div>
      <div className="foot">
        <span>{c.footNote}</span>
        <span className="sp"></span>
        {action}
      </div>
    </div>
  );
}
