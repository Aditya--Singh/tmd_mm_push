type Props = { title: string; description: string };

export default function PlaceholderPage({ title, description }: Props) {
  return (
    <section>
      <h1 className="text-2xl font-semibold text-pnb-maroon">{title}</h1>
      <p className="mt-2 max-w-2xl text-slate-600">{description}</p>
      <div className="mt-10 rounded-xl border border-dashed border-slate-300 bg-slate-50/50 px-8 py-16 text-center">
        <span className="inline-block rounded-full bg-pnb-gold/15 px-3 py-1 text-xs font-medium text-pnb-maroon">
          Under construction
        </span>
        <p className="mt-3 text-sm text-slate-500">This tool is being built and will appear here.</p>
      </div>
    </section>
  );
}
