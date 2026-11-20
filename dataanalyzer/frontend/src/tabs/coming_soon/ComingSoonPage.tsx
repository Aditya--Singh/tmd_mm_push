export default function ComingSoonPage() {
  return (
    <section className="flex min-h-[55vh] items-center justify-center">
      <div className="relative w-full max-w-xl overflow-hidden rounded-2xl border border-slate-100 bg-white px-10 py-14 text-center shadow-sm">
        <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-pnb-maroon to-pnb-gold" />
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-pnb-cream ring-1 ring-pnb-gold/40">
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            className="h-8 w-8 text-pnb-gold"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9z" />
            <path d="M19 15l.8 1.9 1.9.8-1.9.8L19 20.5l-.8-2-1.9-.8 1.9-.8z" />
          </svg>
        </div>
        <p className="mt-6 text-xs font-semibold uppercase tracking-[0.2em] text-pnb-gold">
          In the works
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-pnb-maroon">Coming soon</h1>
        <p className="mx-auto mt-4 max-w-md text-slate-600">
          A new tool to make your day at the branch a little easier is on its way. Check back
          here soon.
        </p>
        <div className="mx-auto mt-8 flex max-w-[8rem] items-center gap-2" aria-hidden="true">
          <span className="h-1 flex-1 rounded-full bg-pnb-maroon" />
          <span className="h-1 flex-1 rounded-full bg-pnb-gold" />
          <span className="h-1 flex-1 rounded-full bg-slate-200" />
        </div>
      </div>
    </section>
  );
}
