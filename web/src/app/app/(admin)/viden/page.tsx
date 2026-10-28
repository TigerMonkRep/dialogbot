import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { AddItem, AddService, DraftCard, Edit, Hear, ImportFromSite, ItemEditor, More, ProfileEdit, Remove } from "./client";
import { kr, summarize } from "./format";
import type { Item, Profile, SourceImport } from "./types";

type Capability = { key: string; status: "available" | "simulated" | "not_implemented" };

const BOX = "flex flex-col gap-4 px-5 md:px-6 py-5 rounded-2xl bg-paper border-2 border-ink";
const FACT = "flex flex-col gap-2 px-4 py-3.5 rounded-xl border-[1.5px] border-ink";

/** «Det ved den»: everything Dialogbot may say to customers, in four numbered boxes you can edit right here.
 *  Only approved knowledge reaches the assistant; changes by owners/admins go live at once, others go to review. */
export default async function VidenPage({ searchParams }: { searchParams: Promise<{ emne?: string; import?: string }> }) {
  const { emne, import: imp } = await searchParams;
  const ws = await requireWorkspace();
  const canApprove = ws.role === "owner" || ws.role === "admin";
  const canDraft = ws.role !== "reader";
  const [items, active, caps, profile, latest] = await Promise.all([
    backend<{ items: Item[] }>(`/workspaces/${ws.id}/knowledge/items?limit=200`),
    backend<{ knowledge_revision: number; items: unknown[] }>(`/workspaces/${ws.id}/assistant/knowledge`),
    backend<{ items: Capability[] }>("/integrations/capabilities"),
    backend<Profile>(`/workspaces/${ws.id}/profile`),
    backend<{ import: SourceImport | null }>(`/workspaces/${ws.id}/knowledge/imports/latest`),
  ]);
  const all = items.items;
  const of = (...kinds: string[]) => all.filter((i) => kinds.includes(i.kind));
  const live = (i: Item) => i.approved_version;
  const drafts = (...kinds: string[]) => of(...kinds).filter((i) => i.open_draft);
  const hours = of("opening_hours")[0], area = of("coverage_area")[0];
  const services = of("service").filter((i) => live(i) || i.open_draft);
  const offers = of("offer"), facts = of("fact");
  const answers = of("known_answer").filter(live), rules = of("unknown_answer").filter(live);
  const aiStatus = caps.items.find((c) => c.key === "ai.assistant_preview")?.status ?? "not_implemented";
  const importReady = caps.items.find((c) => c.key === "knowledge.source_import")?.status !== "not_implemented";
  const canHear = aiStatus !== "not_implemented" && canDraft && active.items.length > 0;
  const hoursV = hours?.approved_version, areaV = area?.approved_version;
  const note = (n: number) => (n ? `${n} ${n === 1 ? "forslag venter" : "forslag venter"}` : "");

  return (
    <div className="flex flex-col gap-5 min-w-0">
      <div className="flex flex-wrap items-end gap-3 md:gap-6">
        <div className="flex flex-col gap-1.5 flex-[1_1_320px]">
          <span className="eyebrow">Det ved den om jer</span>
          <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Alt, Dialogbot må sige til jeres kunder</h1>
          <p className="text-[15px] leading-relaxed text-ink-soft max-w-[620px]">Står det ikke her, siger den det ikke – så tager den en besked til dig i stedet. Du kan rette alt direkte og teste svaret i assistenten. <b className="text-ink">{active.items.length} godkendte emner · revision {active.knowledge_revision}</b>.</p>
        </div>
        {canDraft && <ImportFromSite wsId={ws.id} defaultUrl={profile.website_url ?? ""} initial={latest.import} aiReady={importReady} openByDefault={imp === "1"} />}
      </div>

      {/* 1 · Om jer */}
      <section className={BOX} aria-labelledby="viden-1">
        <Head n={1} id="viden-1" title="Om jer" sub="Det, den siger først" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className={FACT}><span className="eyebrow">Navn</span><span className="text-[15px] text-ink">{profile.legal_name || ws.name}</span>{canApprove && <ProfileEdit wsId={ws.id} profile={profile} />}</div>
          <div className={FACT}><span className="eyebrow">Hvad I laver</span><span className={`text-[15px] ${profile.description ? "text-ink" : "text-muted"}`}>{profile.description || "Ikke udfyldt endnu"}</span></div>
          <div className={`${FACT} ${hoursV ? "" : "border-dashed"}`}>
            <span className="eyebrow">Åbningstider</span>
            <span className={`text-[15px] ${hoursV ? "text-ink" : "text-muted"}`}>{hoursV ? [summarize("opening_hours", hoursV.content).headline, summarize("opening_hours", hoursV.content).detail].filter(Boolean).join(" · ") : "Ingen godkendte åbningstider"}</span>
            {canDraft && <Edit wsId={ws.id} canApprove={canApprove} kind="opening_hours" item={hours} label={hours ? "Ret" : "Tilføj"} />}
          </div>
          <div className={`${FACT} ${areaV ? "" : "border-dashed"}`}>
            <span className="eyebrow">Hvor I kører</span>
            <span className={`text-[15px] ${areaV ? "text-ink" : "text-muted"}`}>{areaV ? summarize("coverage_area", areaV.content).headline : "Ikke angivet"}</span>
            {canDraft && <Edit wsId={ws.id} canApprove={canApprove} kind="coverage_area" item={area} label={area ? "Ret" : "Tilføj"} />}
          </div>
        </div>
        {drafts("opening_hours", "coverage_area").map((i) => <DraftCard key={i.id} wsId={ws.id} item={i} canApprove={canApprove} canDraft={canDraft} note="Ændring afventer" />)}
        {(facts.length > 0 || canDraft) && (
          <div className="flex flex-col gap-2">
            {facts.filter(live).map((f) => (
              <div key={f.id} className="flex flex-wrap items-center gap-3 py-2 border-t-[1.5px] border-line">
                <span className="flex-1 min-w-[200px] text-[15px] text-ink">{summarize("fact", f.approved_version!.content).headline}</span>
                {canDraft && <Edit wsId={ws.id} canApprove={canApprove} kind="fact" item={f} />}{canDraft && <Remove wsId={ws.id} item={f} canApprove={canApprove} label={summarize("fact", f.approved_version!.content).headline.slice(0, 40)} />}
              </div>
            ))}
            {drafts("fact").map((i) => <DraftCard key={i.id} wsId={ws.id} item={i} canApprove={canApprove} canDraft={canDraft} />)}
            {canDraft && <AddItem wsId={ws.id} canApprove={canApprove} kind="fact" label="Tilføj noget, den skal vide" />}
          </div>
        )}
      </section>

      {/* 2 · Det I sælger */}
      <section className={BOX} aria-labelledby="viden-2">
        <Head n={2} id="viden-2" title="Det I sælger" sub={`Ydelser og priser – det, den må tilbyde${drafts("service", "offer").length ? ` · ${note(drafts("service", "offer").length)}` : ""}`} />
        {canDraft && <AddService wsId={ws.id} canApprove={canApprove} canAsk={aiStatus !== "not_implemented" && canDraft} />}
        {drafts("service").map((i) => <DraftCard key={i.id} wsId={ws.id} item={i} canApprove={canApprove} canDraft={canDraft} />)}
        {services.filter(live).length === 0 && drafts("service").length === 0 && <p className="px-4 py-3.5 rounded-xl border-[1.5px] border-dashed border-ink text-[14px] text-ink-soft">Ingen ydelser endnu – uden dem kan den ikke svare på priser.</p>}
        <ul className="flex flex-col">
          {services.filter(live).map((s) => {
            const v = s.approved_version!;
            const sells = v.content.promote !== false;
            return (
              <li key={s.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3 border-t-[1.5px] border-line">
                <span className="flex-1 min-w-[160px] font-semibold text-[15px] text-ink">{v.title}</span>
                <span className="font-display font-bold text-ink">{kr(v.content.price_net_minor) ?? "–"}</span>
                <span className="flex-[2_1_200px] min-w-[160px] text-[14px] text-ink-soft">{String(v.content.description ?? "")}</span>
                <span className="inline-flex px-3 py-1.5 rounded-full bg-panel border-[1.5px] border-ink text-[12px] font-semibold text-ink">{sells ? "Sælger" : "Kun hvis spurgt"}</span>
                {canHear && <Hear wsId={ws.id} question={`Hvad koster ${v.title}?`} />}
                {canDraft && <Edit wsId={ws.id} canApprove={canApprove} kind="service" item={s} />}
                {canDraft && <Remove wsId={ws.id} item={s} canApprove={canApprove} label={v.title} />}
              </li>
            );
          })}
        </ul>
        {(offers.length > 0 || canDraft) && (
          <div className="flex flex-col gap-2">
            <span className="eyebrow">Tilbud og rabatter</span>
            {drafts("offer").map((i) => <DraftCard key={i.id} wsId={ws.id} item={i} canApprove={canApprove} canDraft={canDraft} />)}
            {offers.filter(live).map((o) => {
              const s = summarize("offer", o.approved_version!.content);
              return (
                <div key={o.id} className="flex flex-wrap items-center gap-3 py-2 border-t-[1.5px] border-line">
                  <span className="flex-1 min-w-[200px] text-[15px] text-ink"><b>{o.approved_version!.title}</b> · {s.headline} · {s.detail}</span>
                  {canDraft && <Edit wsId={ws.id} canApprove={canApprove} kind="offer" item={o} />}{canDraft && <Remove wsId={ws.id} item={o} canApprove={canApprove} label={o.approved_version!.title} />}
                </div>
              );
            })}
            {canDraft && <AddItem wsId={ws.id} canApprove={canApprove} kind="offer" label="Tilføj et tilbud" />}
          </div>
        )}
        <p className="text-[13px] text-muted">«Sælger» betyder, at den selv nævner ydelsen, når det passer. «Kun hvis spurgt» betyder, at den kun svarer på prisen. Priser er ekskl. moms.</p>
      </section>

      {/* 3 · Spørgsmål kunderne stiller */}
      <section className={BOX} aria-labelledby="viden-3" id="spoergsmaal">
        <Head n={3} id="viden-3" title="Spørgsmål kunderne stiller" sub={`${answers.length} svar godkendt`} />
        {drafts("known_answer").map((i) => <DraftCard key={i.id} wsId={ws.id} item={i} canApprove={canApprove} canDraft={canDraft} />)}
        {answers.length === 0 && drafts("known_answer").length === 0 && <p className="px-4 py-3.5 rounded-xl border-[1.5px] border-dashed border-ink text-[14px] text-ink-soft">Ingen faste svar endnu. Tilføj de spørgsmål, kunderne oftest stiller.</p>}
        <AnswerRows wsId={ws.id} canApprove={canApprove} canDraft={canDraft} rows={answers} />
        {canDraft && <AddItem wsId={ws.id} canApprove={canApprove} kind="known_answer" label="Tilføj et svar" initial={emne ? { question: emne } : undefined} openByDefault={!!emne} />}
      </section>

      {/* 4 · Det må den ikke */}
      <section className={`${BOX}`} aria-labelledby="viden-4">
        <Head n={4} id="viden-4" title="Det må den ikke" sub="Her tager den en besked til dig i stedet" dark />
        {drafts("unknown_answer").map((i) => <DraftCard key={i.id} wsId={ws.id} item={i} canApprove={canApprove} canDraft={canDraft} />)}
        <ul className="flex flex-wrap gap-2">
          {rules.map((r) => (
            <li key={r.id} className="inline-flex items-center gap-1 pl-4 pr-1 min-h-[44px] rounded-full border-[1.5px] border-ink text-[14px] font-medium text-ink">
              {summarize("unknown_answer", r.approved_version!.content).headline}
              {canDraft && <Remove wsId={ws.id} item={r} canApprove={canApprove} label={summarize("unknown_answer", r.approved_version!.content).headline.slice(0, 40)} />}
            </li>
          ))}
        </ul>
        {rules.length === 0 && <p className="text-[14px] text-ink-soft">Ingen regler endnu.</p>}
        {canDraft && <AddItem wsId={ws.id} canApprove={canApprove} kind="unknown_answer" label="Tilføj en regel" />}
      </section>
    </div>
  );
}

function Head({ n, id, title, sub, dark = false }: { n: number; id: string; title: string; sub: string; dark?: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className={`inline-flex w-10 h-10 rounded-[10px] items-center justify-center font-display font-extrabold text-[20px] ${dark ? "bg-ink text-paper" : "bg-highlight text-ink"}`} aria-hidden>{n}</span>
      <h2 id={id} className="font-display font-extrabold text-[20px] text-ink">{title}</h2>
      <span className="text-[13px] text-muted">{sub}</span>
    </div>
  );
}

/** The first three approved answers; the rest behind «Se alle». */
function AnswerRows({ wsId, canApprove, canDraft, rows }: { wsId: string; canApprove: boolean; canDraft: boolean; rows: Item[] }) {
  const row = (a: Item) => {
    const s = summarize("known_answer", a.approved_version!.content);
    return (
      <li key={a.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3 border-t-[1.5px] border-line">
        <span className="flex-[1_1_220px] min-w-[180px] font-semibold text-[15px] text-ink">{s.headline}</span>
        <span className="flex-[2_1_260px] min-w-[200px] text-[14px] text-ink-soft">{s.detail}</span>
        {canDraft && <Edit wsId={wsId} canApprove={canApprove} kind="known_answer" item={a} />}
        {canDraft && <Remove wsId={wsId} item={a} canApprove={canApprove} label={s.headline.slice(0, 40)} />}
      </li>
    );
  };
  return (
    <ul className="flex flex-col">
      {rows.slice(0, 3).map(row)}
      <More count={rows.length - 3} label={`Se alle ${rows.length}`}>{rows.slice(3).map(row)}</More>
    </ul>
  );
}
