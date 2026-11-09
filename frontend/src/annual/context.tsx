import {
  createContext,
  useContext,
  useEffect,
  useRef,
  type ReactNode,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";
import { ExternalLink, FileText, X } from "lucide-react";
import {
  publicUrl,
  pretty,
  type Bundle,
  type CaseSource,
  type Citation,
} from "./model";

export type Params = Record<string, string>;
export const Workspace = createContext<{
  b: Bundle;
  p: Params;
  go: (v: Params, reset?: boolean) => void;
} | null>(null);
export const useDesk = () => {
  const c = useContext(Workspace);
  if (!c) throw Error("Missing report context");
  return c;
};
export type Proof = {
  title: string;
  quote?: string | string[];
  page?: number | null;
  printed?: string | null;
  date?: string | null;
  url?: string | null;
  origin?: string;
  detail?: string;
};
export function annualProof(
  b: Bundle,
  title: string,
  page: number,
  quote: string | string[],
  printed?: string,
): Proof {
  return {
    title,
    page,
    quote,
    printed,
    date: b.meta.published,
    url: b.original,
    origin: "Annual report disclosure",
  };
}
export function cited(b: Bundle, title: string, c: Citation): Proof {
  return {
    ...annualProof(b, title, c.physical_page, c.quote, c.printed_page),
    date: c.published_at,
    url:
      c.source_id === "annual"
        ? b.original
        : publicUrl(b.annual.sources[c.source_id]?.source),
    origin: c.source_id === "annual" ? "Annual report disclosure" : c.source_id,
  };
}
export function caseProof(s: CaseSource, title: string): Proof {
  return {
    title,
    page: s.page,
    quote: s.anchors,
    url: publicUrl(s.url),
    date: s.published,
    origin: pretty(s.kind),
  };
}
export function ProofButton({
  id,
  proof,
  children,
}: {
  id: string;
  proof: Proof;
  children?: ReactNode;
}) {
  const { p, go } = useDesk();
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button
        ref={trigger}
        className="ar-source"
        onClick={() => go({ proof: id })}
      >
        {children || "View source"}
      </button>
      {p.proof === id &&
        createPortal(
          <ProofSheet
            returnFocus={trigger}
            proof={proof}
            close={() => {
              if (history.state?.annualProof) history.back();
              else go({ proof: "" });
            }}
          />,
          document.body,
        )}
    </>
  );
}
function ProofSheet({
  proof,
  close,
  returnFocus,
}: {
  proof: Proof;
  close: () => void;
  returnFocus: RefObject<HTMLButtonElement>;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    d?.showModal();
    return () => {
      d?.close();
      const target = returnFocus.current;
      queueMicrotask(() => target?.focus({ preventScroll: true }));
    };
  }, [returnFocus]);
  const url =
    publicUrl(proof.url) ||
    (/^\/workflows\/annual-report\/library\/run-[0-9a-f]{32}\/original$/.test(
      proof.url || "",
    )
      ? proof.url
      : null);
  return (
    <dialog
      ref={ref}
      className="ar-sheet"
      aria-label="Source evidence"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === ref.current) close();
      }}
    >
      <div>
        <header>
          <span className="ar-kicker">
            <FileText size={15} /> Source evidence
          </span>
          <button aria-label="Close evidence" onClick={close} autoFocus>
            <X size={20} />
          </button>
        </header>
        <h2>{proof.title}</h2>
        <p className="ar-badge">{proof.origin || "Source record"}</p>
        <dl>
          <dt>Published</dt>
          <dd>{proof.date || "Unknown"}</dd>
          {proof.page != null && (
            <>
              <dt>Document location</dt>
              <dd>
                PDF p. {proof.page}
                {proof.printed ? " · Printed p. " + proof.printed : ""}
              </dd>
            </>
          )}
        </dl>
        {proof.detail && <p>{proof.detail}</p>}
        {(Array.isArray(proof.quote) ? proof.quote : [proof.quote])
          .filter(Boolean)
          .map((q, i) => (
            <blockquote key={i}>{q}</blockquote>
          ))}
        {url ? (
          <a
            href={url.split("#")[0] + (proof.page ? "#page=" + proof.page : "")}
            target="_blank"
            rel="noreferrer"
          >
            Open original{proof.page ? " at page " + proof.page : ""}{" "}
            <ExternalLink size={14} />
          </a>
        ) : (
          <p>Original file unavailable. The citation is retained.</p>
        )}
      </div>
    </dialog>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return <p className="ar-empty">{children}</p>;
}
