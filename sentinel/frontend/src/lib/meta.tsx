import { useEffect, useState } from "react";

export interface Meta {
  app_name: string;
  org_name: string;
  org_short: string;
  org_unit: string;
  auth_enabled: boolean;
  email_enabled: boolean;
}

const FALLBACK: Meta = {
  app_name: "PNB Regulatory Sentinel",
  org_name: "Punjab National Bank",
  org_short: "PNB",
  org_unit: "Data Analytics and Strategic Innovation Division",
  auth_enabled: false,
  email_enabled: false,
};

let cache: Meta | null = null;
let pending: Promise<Meta> | null = null;

/** Organisation branding from the server's .env (ORG_NAME, ORG_SHORT, ORG_UNIT). */
export function useMeta(): Meta {
  const [meta, setMeta] = useState<Meta>(cache ?? FALLBACK);
  useEffect(() => {
    if (cache) return;
    pending ??= fetch("/api/meta").then((r) => (r.ok ? r.json() : FALLBACK)).catch(() => FALLBACK);
    pending.then((m: Meta) => {
      cache = m;
      setMeta(m);
      document.title = m.app_name;
    });
  }, []);
  return meta;
}
